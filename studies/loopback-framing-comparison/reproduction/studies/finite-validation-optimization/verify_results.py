"""Independent evidence verifier: imports neither benchmark nor codec code."""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
import struct

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 4 * 1024 * 1024
BASELINE_COMMIT = 'ce945115f7fcf8f4da559cc5026d8a0157b5fa7d'
CODEC_SHA256 = '3fcb2b2dffd7d95e56d4887ce02a63482ff612b4a7c0313e9fbcb715a419b5aa'
SOURCE_FILES = {'PROTOCOL.md', 'benchmark.py', 'verify_results.py',
                'test_benchmark.py', 'test_verify_results.py', 'candidate_codec.py',
                'test_candidate_codec.py', 'BASELINE_PRE_DATA.json',
                '../tcp-framing-codec/mesh_codec.py', '../tcp-framing-codec/test_mesh_codec.py'}
CONFIG = {'blocks': 10, 'iterations': 50, 'warmup': 5, 'seed': 20261025,
          'allocation_blocks': 4, 'allocation_iterations': 1, 'tracemalloc_frames': 1}
CASES = ('activation_decode', 'activation_prefill_16', 'activation_prefill_64', 'audit_reply')
OPS = ('finite_scan', 'frame_pack', 'frame_decode')
VARIANTS = ('baseline', 'candidate')
SCOPE = 'single-host paired finite-validation optimization; no sockets, mesh, model, inference, device, RSS, or total-allocation claim'
PLAN_FIELDS = {'block', 'pair', 'order', 'case', 'operation', 'variant', 'position', 'pair_order'}
SUMMARY_FIELDS = {'summaries', 'paired_summaries', 'allocation_summaries', 'allocation_paired_summaries'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def read_json(path):
    require(path.stat().st_size <= MAX_BYTES, 'file exceeds size cap')
    return parse_json(path.read_text(encoding='utf-8'))


def equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(equal(actual[k], expected[k]) for k in expected)
    if type(expected) is list:
        return len(actual) == len(expected) and all(equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def utc(value):
    require(type(value) is str, 'timestamp string required')
    parsed = datetime.fromisoformat(value)
    require(parsed.utcoffset() == timedelta(0), 'UTC-aware timestamp required')
    return parsed


def digest(value, size=64):
    return type(value) is str and len(value) == size and all(c in '0123456789abcdef' for c in value)


def expected_inputs():
    output = {}
    for name, count, length, prior, audit in [
        ('activation_decode', 576, 1, 1, False),
        ('activation_prefill_16', 9216, 16, 0, False),
        ('activation_prefill_64', 36864, 64, 0, False),
        ('audit_reply', 49152, 1, 1, True),
    ]:
        tensor = b''.join(struct.pack('<f', ((i % 257) - 128) / 128) for i in range(count))
        payload = b'\x00\x00\x00\x07' + tensor if audit else tensor
        header = (b'CMTP' + bytes([1, 9 if audit else 7, 1 if audit else 0, 2 if audit else 1]) +
                  bytes(range(16)) + struct.pack('>6I', 0, 1, prior, length, len(payload), 0) + bytes(16))
        output[name] = {'payload_bytes': len(payload), 'frame_bytes': len(header) + len(payload),
                        'payload_sha256': hashlib.sha256(payload).hexdigest(),
                        'frame_sha256': hashlib.sha256(header + payload).hexdigest()}
    return output


def expected_schedule(allocation=False):
    rng = random.Random(20261026 if allocation else 20261025)
    base = [(case, operation) for case in CASES for operation in OPS]
    output = []
    for block in range(4 if allocation else 10):
        ordered = base.copy()
        rng.shuffle(ordered)
        for pair, cell in enumerate(ordered):
            case, operation = cell
            baseline_first = (block + base.index(cell)) % 2 == 0
            variants = ['baseline', 'candidate'] if baseline_first else ['candidate', 'baseline']
            for position, variant in enumerate(variants):
                output.append({'block': block, 'pair': pair, 'order': pair * 2 + position,
                               'case': case, 'operation': operation, 'variant': variant,
                               'position': position, 'pair_order': 'AB' if baseline_first else 'BA'})
    return output


def describe(observations):
    values = sorted(float(n) for n in observations)
    require(len(values) >= 2 and all(math.isfinite(n) for n in values), 'summary observations')
    count = len(values)
    middle = count // 2
    median = values[middle] if count % 2 else (values[middle - 1] + values[middle]) / 2
    def quartile(q):
        index, remainder = divmod(q * (count - 1), 4)
        return (values[index] * (4 - remainder) + values[index + 1] * remainder) / 4
    return {'median': median, 'min': values[0], 'max': values[-1], 'iqr': quartile(3) - quartile(1)}


def expected_summaries(rows, allocation=False):
    metrics = ['retained_bytes', 'peak_increment_bytes'] if allocation else ['wall_ns_per_op', 'cpu_ns_per_op']
    count = 4 if allocation else 10
    summaries, pairs = [], []
    for case in sorted(CASES):
        for operation in sorted(OPS):
            group = [r for r in rows if r['case'] == case and r['operation'] == operation]
            for variant in VARIANTS:
                selected = [r for r in group if r['variant'] == variant]
                require(len(selected) == count, 'summary cell count')
                entry = {'case': case, 'operation': operation, 'variant': variant, 'samples': count}
                for metric in metrics:
                    entry[metric] = describe(r[metric] for r in selected)
                summaries.append(entry)
            paired = {'case': case, 'operation': operation, 'pairs': count}
            deltas = {key: [] for key in (['retained_delta_bytes', 'peak_delta_bytes'] if allocation else
                                         ['wall_ratio', 'cpu_ratio', 'wall_delta_ns', 'cpu_delta_ns'])}
            for block in range(count):
                a = [r for r in group if r['block'] == block and r['variant'] == 'baseline']
                c = [r for r in group if r['block'] == block and r['variant'] == 'candidate']
                require(len(a) == len(c) == 1, 'pair identity')
                a, c = a[0], c[0]
                if allocation:
                    deltas['retained_delta_bytes'].append(c['retained_bytes'] - a['retained_bytes'])
                    deltas['peak_delta_bytes'].append(c['peak_increment_bytes'] - a['peak_increment_bytes'])
                else:
                    for prefix in ['wall', 'cpu']:
                        key = prefix + '_ns_per_op'
                        deltas[prefix + '_ratio'].append(c[key] / a[key])
                        deltas[prefix + '_delta_ns'].append(c[key] - a[key])
            paired.update({name: describe(values) for name, values in deltas.items()})
            pairs.append(paired)
    return summaries, pairs


def validate_environment(env):
    fields = {'python', 'implementation', 'system', 'release', 'machine', 'logical_cpus',
              'cpu_model', 'cgroup_cpu_max', 'timers', 'gc_enabled', 'gc_threshold',
              'byteorder', 'native_float_format', 'candidate_native_fp32_le'}
    require(type(env) is dict and set(env) == fields, 'environment fields')
    for name in ['python', 'implementation', 'system', 'release', 'machine', 'native_float_format']:
        require(type(env[name]) is str and 0 < len(env[name]) <= 512, 'environment string')
    for name in ['cpu_model', 'cgroup_cpu_max']:
        require(env[name] is None or (type(env[name]) is str and len(env[name]) <= 512), 'optional environment string')
    require(env['logical_cpus'] is None or (type(env['logical_cpus']) is int and env['logical_cpus'] > 0), 'CPU count')
    require(type(env['gc_enabled']) is bool, 'GC state')
    require(type(env['gc_threshold']) is list and len(env['gc_threshold']) == 3 and
            all(type(n) is int and n >= 0 for n in env['gc_threshold']), 'GC thresholds')
    require(env['byteorder'] in ('little', 'big'), 'byteorder')
    native = env['byteorder'] == 'little' and env['native_float_format'] == 'IEEE, little-endian'
    require(type(env['candidate_native_fp32_le']) is bool and env['candidate_native_fp32_le'] == native,
            'native optimization path disagrees with host format')
    require(type(env['timers']) is dict and set(env['timers']) == {'perf_counter', 'process_time', 'monotonic'}, 'timers')
    for timer in env['timers'].values():
        require(type(timer) is dict and set(timer) ==
                {'implementation', 'resolution_seconds', 'monotonic', 'adjustable'}, 'timer fields')
        require(type(timer['implementation']) is str and 0 < len(timer['implementation']) <= 512, 'timer implementation')
        n = timer['resolution_seconds']
        require(type(n) in (int, float) and math.isfinite(n) and n > 0, 'timer resolution')
        require(timer['monotonic'] is True and timer['adjustable'] is False, 'timer properties')


def validate_record(record, sources, freeze_sha256):
    fields = {'schema', 'status', 'run_id', 'scope', 'started_at_utc', 'finished_at_utc', 'config',
              'environment', 'freeze_sha256', 'sources', 'inputs', 'latency_schedule', 'allocation_schedule',
              'rows', 'allocation_rows', 'elapsed_monotonic_seconds', 'process_instance'} | SUMMARY_FIELDS
    require(type(record) is dict and set(record) == fields, 'result fields')
    require(type(record['schema']) is int and record['schema'] == 1, 'schema')
    require(record['status'] == 'complete' and record['run_id'] in ('run-001', 'run-002'), 'identity/status')
    require(record['scope'] == SCOPE, 'scope')
    require(digest(record['process_instance'], 32), 'process instance')
    elapsed_utc = (utc(record['finished_at_utc']) - utc(record['started_at_utc'])).total_seconds()
    require(elapsed_utc >= 0, 'timestamp order')
    elapsed = record['elapsed_monotonic_seconds']
    require(type(elapsed) is float and math.isfinite(elapsed) and 0 < elapsed < 180, 'monotonic interval/budget')
    require(equal(record['config'], CONFIG), 'fixed config')
    require(type(sources) is dict and set(sources) == SOURCE_FILES and all(digest(d) for d in sources.values()), 'source inventory')
    require(equal(record['sources'], sources) and digest(freeze_sha256) and record['freeze_sha256'] == freeze_sha256, 'freeze mismatch')
    require(equal(record['inputs'], expected_inputs()), 'input bytes/hashes')
    validate_environment(record['environment'])
    for allocation in [False, True]:
        schedule = expected_schedule(allocation)
        require(equal(record['allocation_schedule' if allocation else 'latency_schedule'], schedule), 'schedule mismatch')
        rows = record['allocation_rows' if allocation else 'rows']
        require(type(rows) is list and len(rows) == len(schedule), 'row count')
        additions = ({'iterations', 'before_bytes', 'current_bytes', 'peak_bytes', 'retained_bytes', 'peak_increment_bytes'}
                     if allocation else {'iterations', 'wall_ns', 'cpu_ns', 'wall_ns_per_op', 'cpu_ns_per_op'})
        for row, planned in zip(rows, schedule):
            require(type(row) is dict and set(row) == PLAN_FIELDS | additions, 'row fields')
            require(equal({k: row[k] for k in PLAN_FIELDS}, planned), 'row identity/order')
            require(type(row['iterations']) is int and row['iterations'] == (1 if allocation else 50), 'iterations')
            if allocation:
                for metric in ['before_bytes', 'current_bytes', 'peak_bytes', 'peak_increment_bytes']:
                    require(type(row[metric]) is int and 0 <= row[metric] <= 2**53, 'allocation byte counter')
                require(type(row['retained_bytes']) is int, 'retained byte type')
                require(row['peak_bytes'] >= row['current_bytes'], 'allocation peak below current')
                require(row['retained_bytes'] == row['current_bytes'] - row['before_bytes'], 'retained byte delta')
                require(row['peak_increment_bytes'] == max(0, row['peak_bytes'] - row['before_bytes']), 'peak byte increment')
            else:
                for metric in ['wall_ns', 'cpu_ns']:
                    require(type(row[metric]) is int and 0 < row[metric] < 180_000_000_000, 'batch timer interval/budget')
                    derived = row[metric + '_per_op']
                    require(type(derived) is float and math.isfinite(derived) and derived == row[metric] / 50, 'per-operation timing')
        summary, paired = expected_summaries(rows, allocation)
        require(equal(record['allocation_summaries' if allocation else 'summaries'], summary), 'summary mismatch')
        require(equal(record['allocation_paired_summaries' if allocation else 'paired_summaries'], paired), 'paired summary mismatch')
    total_ns = sum(row['wall_ns'] for row in record['rows'])
    require(total_ns <= elapsed * 1e9, 'batch total exceeds monotonic interval')
    require(total_ns <= (elapsed_utc + 0.001) * 1e9, 'batch total exceeds UTC interval plus 1 ms')
    return {'run_id': record['run_id'], 'rows': 240, 'allocation_rows': 96, 'paired_cells': 12}


def validate_journal(events, record):
    require(type(events) is list and len(events) == 338, 'journal event count')
    omitted = SUMMARY_FIELDS | {'rows', 'allocation_rows', 'finished_at_utc', 'elapsed_monotonic_seconds'}
    metadata = {k: value for k, value in record.items() if k not in omitted}
    metadata['status'] = 'running'
    require(equal(events[0], {'event': 'start', 'metadata': metadata}), 'journal metadata')
    for event, row in zip(events[1:241], record['rows']):
        require(equal(event, {'event': 'row', 'row': row}), 'latency journal mismatch')
    for event, row in zip(events[241:337], record['allocation_rows']):
        require(equal(event, {'event': 'allocation_row', 'row': row}), 'allocation journal mismatch')
    require(equal(events[-1], {'event': 'finish', 'status': 'complete', 'rows': 240, 'allocation_rows': 96,
                              'finished_at_utc': record['finished_at_utc'],
                              'elapsed_monotonic_seconds': record['elapsed_monotonic_seconds']}), 'journal terminal event')


def validate_baseline_inventory():
    inventory = read_json(ROOT / 'BASELINE_PRE_DATA.json')
    fields = {'schema', 'published_baseline_commit', 'local_base_commit', 'scope', 'checked_at_utc', 'files'}
    require(type(inventory) is dict and set(inventory) == fields, 'baseline inventory fields')
    require(type(inventory['schema']) is int and inventory['schema'] == 1 and
            inventory['published_baseline_commit'] == BASELINE_COMMIT, 'baseline identity')
    require(digest(inventory['local_base_commit'], 40), 'local baseline commit')
    require(type(inventory['scope']) is str and 0 < len(inventory['scope']) <= 512, 'baseline scope')
    utc(inventory['checked_at_utc'])
    require(type(inventory['files']) is list and len(inventory['files']) == 62, 'baseline file inventory')
    seen = set()
    for item in inventory['files']:
        require(type(item) is dict and set(item) == {'path', 'sha256', 'git_blob_sha1'}, 'baseline file fields')
        name = item['path']
        require(type(name) is str and name and not Path(name).is_absolute() and '..' not in Path(name).parts
                and str(Path(name)) == name and name not in seen, 'baseline file path')
        seen.add(name)
        require(digest(item['sha256']) and digest(item['git_blob_sha1'], 40), 'baseline digests')
        content = (ROOT.parent.parent / name).read_bytes()
        require(hashlib.sha256(content).hexdigest() == item['sha256'], 'baseline sha256 changed: ' + name)
        blob = b'blob ' + str(len(content)).encode('ascii') + b'\0' + content
        require(hashlib.sha1(blob).hexdigest() == item['git_blob_sha1'], 'baseline git blob changed: ' + name)


def load_verified(directory):
    freeze_path = ROOT / 'PRE_DATA_SHA256.json'
    freeze = read_json(freeze_path)
    require(type(freeze) is dict and set(freeze) == {'schema', 'baseline_commit', 'frozen_at_utc', 'sources'}, 'freeze fields')
    require(type(freeze['schema']) is int and freeze['schema'] == 1 and freeze['baseline_commit'] == BASELINE_COMMIT, 'freeze identity')
    require(type(freeze['sources']) is dict and set(freeze['sources']) == SOURCE_FILES, 'freeze source inventory')
    require(freeze['sources']['../tcp-framing-codec/mesh_codec.py'] == CODEC_SHA256, 'baseline codec identity')
    for name, expected in freeze['sources'].items():
        require(digest(expected), 'source digest')
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, 'source changed: ' + name)
    validate_baseline_inventory()
    result = read_json(directory / 'result.json')
    outcome = validate_record(result, freeze['sources'], hashlib.sha256(freeze_path.read_bytes()).hexdigest())
    require(utc(result['started_at_utc']) >= utc(freeze['frozen_at_utc']), 'run precedes freeze')
    journal_path = directory / 'journal.jsonl'
    require(journal_path.stat().st_size <= MAX_BYTES, 'journal exceeds size cap')
    events = [parse_json(line) for line in journal_path.read_text(encoding='utf-8').splitlines()]
    validate_journal(events, result)
    return result, outcome


def verify(directory):
    return load_verified(Path(directory))[1]


def validate_run_set(records):
    require(type(records) is list and len(records) == 2, 'exactly two planned runs required')
    first, second = records
    require([r['run_id'] for r in records] == ['run-001', 'run-002'], 'planned run order/identity')
    require(first['process_instance'] != second['process_instance'], 'fresh process instance required')
    require(utc(second['started_at_utc']) >= utc(first['finished_at_utc']), 'runs must be sequential')
    require(equal(first['environment'], second['environment']), 'run environments differ')
    require(equal(first['sources'], second['sources']) and first['freeze_sha256'] == second['freeze_sha256'], 'run freezes differ')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories', nargs=2, type=Path, help='run-001 then run-002')
    args = parser.parse_args()
    verified = [load_verified(directory) for directory in args.directories]
    validate_run_set([record for record, _ in verified])
    print(json.dumps({'status': 'verified', 'runs': [outcome for _, outcome in verified]}, indent=2))


if __name__ == '__main__':
    main()
