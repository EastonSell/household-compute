"""Recompute the fixed evidence contract without running benchmark or codec code."""
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
SOURCE_FILES = {'PROTOCOL.md', 'benchmark.py', 'verify_results.py',
                'test_benchmark.py', 'test_verify_results.py',
                'BASELINE_UPSTREAM.json', 'BASELINE_PRE_DATA.json',
                '../tcp-framing-codec/mesh_codec.py'}
CODEC_SHA256 = '3fcb2b2dffd7d95e56d4887ce02a63482ff612b4a7c0313e9fbcb715a419b5aa'
CONFIG = {'blocks': 9, 'iterations': 50, 'warmup': 5, 'seed': 20261025}
CASES = ('activation_decode', 'activation_prefill_16', 'activation_prefill_64', 'audit_reply')
OPS = ('noop', 'payload_copy', 'header_pack', 'finite_scan', 'frame_pack', 'frame_decode')
SCOPE = 'single-host single-process framing controls; no sockets, mesh, model, inference, or device claim'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_json(raw):
    def pairs(items):
        output = {}
        for key, value in items:
            require(key not in output, 'duplicate JSON key')
            output[key] = value
        return output
    def invalid_constant(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)


def read_json(path):
    require(path.stat().st_size <= MAX_BYTES, 'file exceeds size cap')
    return parse_json(path.read_text(encoding='utf-8'))


def equal(actual, expected):
    """Typed equality, so bool cannot impersonate an integer or statistic."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return (actual.keys() == expected.keys() and
                all(equal(actual[k], expected[k]) for k in expected))
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def utc(value):
    require(type(value) is str, 'timestamp must be a string')
    parsed = datetime.fromisoformat(value)
    require(parsed.utcoffset() == timedelta(0), 'timestamp must be UTC-aware')
    return parsed


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


def expected_schedule():
    rng = random.Random(20261025)
    cells = [(c, o) for c in CASES for o in OPS]
    result = []
    for block in range(9):
        ordered = list(cells)
        rng.shuffle(ordered)
        for order, (case, operation) in enumerate(ordered):
            result.append({'block': block, 'order': order, 'case': case, 'operation': operation})
    return result


def expected_summaries(rows):
    result = []
    for case in sorted(CASES):
        for operation in sorted(OPS):
            group = [r for r in rows if r['case'] == case and r['operation'] == operation]
            require(len(group) == 9, 'incomplete summary cell')
            entry = {'case': case, 'operation': operation, 'batches': 9}
            for metric in ('wall_ns_per_op', 'cpu_ns_per_op'):
                values = sorted(row[metric] for row in group)
                # For n=9, inclusive quartiles are exactly observations 3 and 7.
                entry[metric] = {'median': values[4], 'min': values[0], 'max': values[8],
                                 'iqr': values[6] - values[2]}
            result.append(entry)
    return result


def validate_environment(env):
    required = {'python', 'implementation', 'system', 'release', 'machine', 'logical_cpus',
                'cpu_model', 'cgroup_cpu_max', 'timers', 'gc_enabled', 'gc_threshold'}
    require(type(env) is dict and set(env) == required, 'environment fields')
    for name in ('python', 'implementation', 'system', 'release', 'machine'):
        require(type(env[name]) is str and 0 < len(env[name]) <= 512, 'environment string')
    for name in ('cpu_model', 'cgroup_cpu_max'):
        require(env[name] is None or (type(env[name]) is str and len(env[name]) <= 512), 'optional environment string')
    require(env['logical_cpus'] is None or
            (type(env['logical_cpus']) is int and env['logical_cpus'] > 0), 'logical CPU count')
    require(type(env['gc_enabled']) is bool, 'GC state')
    require(type(env['gc_threshold']) is list and len(env['gc_threshold']) == 3 and
            all(type(n) is int and n >= 0 for n in env['gc_threshold']), 'GC thresholds')
    require(type(env['timers']) is dict and set(env['timers']) ==
            {'perf_counter', 'process_time', 'monotonic'}, 'timers')
    for timer in env['timers'].values():
        require(type(timer) is dict and set(timer) ==
                {'implementation', 'resolution_seconds', 'monotonic', 'adjustable'}, 'timer fields')
        require(type(timer['implementation']) is str and bool(timer['implementation']), 'timer implementation')
        resolution = timer['resolution_seconds']
        require(type(resolution) in (int, float) and math.isfinite(resolution) and resolution > 0, 'timer resolution')
        require(timer['monotonic'] is True and timer['adjustable'] is False, 'timer properties')


def validate_record(record, sources, freeze_sha256):
    fields = {'schema', 'status', 'run_id', 'scope', 'started_at_utc', 'finished_at_utc', 'config',
              'environment', 'freeze_sha256', 'sources', 'inputs', 'schedule', 'rows', 'summaries',
              'elapsed_monotonic_seconds'}
    require(type(record) is dict and set(record) == fields, 'result fields')
    require(type(record['schema']) is int and record['schema'] == 1, 'result schema')
    require(record['status'] == 'complete' and record['run_id'] in ('run-001', 'run-002'), 'run identity/status')
    require(record['scope'] == SCOPE, 'scope changed')
    elapsed_seconds = (utc(record['finished_at_utc']) - utc(record['started_at_utc'])).total_seconds()
    require(elapsed_seconds >= 0, 'timestamp order')
    monotonic_seconds = record['elapsed_monotonic_seconds']
    require(type(monotonic_seconds) is float and math.isfinite(monotonic_seconds) and
            0 < monotonic_seconds < 180, 'monotonic run interval/budget')
    require(equal(record['config'], CONFIG), 'config changed')
    require(equal(record['sources'], sources) and record['freeze_sha256'] == freeze_sha256, 'freeze mismatch')
    require(equal(record['inputs'], expected_inputs()), 'input bytes/hashes differ')
    validate_environment(record['environment'])
    schedule = expected_schedule()
    require(equal(record['schedule'], schedule), 'schedule mismatch')
    require(type(record['rows']) is list and len(record['rows']) == 216, 'row count')
    row_fields = {'block', 'order', 'case', 'operation', 'iterations', 'wall_ns', 'cpu_ns',
                  'wall_ns_per_op', 'cpu_ns_per_op'}
    for row, planned in zip(record['rows'], schedule):
        require(type(row) is dict and set(row) == row_fields, 'row fields')
        require(equal({k: row[k] for k in planned}, planned), 'row order/identity')
        require(type(row['iterations']) is int and row['iterations'] == 50, 'iteration count')
        for metric in ('wall_ns', 'cpu_ns'):
            require(type(row[metric]) is int and row[metric] > 0, 'timer interval')
            require(row[metric] <= 180_000_000_000, 'batch exceeds run budget')
            per_op = row[metric + '_per_op']
            require(type(per_op) is float and math.isfinite(per_op) and per_op == row[metric] / 50,
                    'per-operation timing mismatch')
    require(sum(row['wall_ns'] for row in record['rows']) <= (elapsed_seconds + 0.001) * 1e9,
            'batch wall total exceeds UTC run interval plus 1 ms tolerance')
    require(sum(row['wall_ns'] for row in record['rows']) <= monotonic_seconds * 1e9,
            'batch wall total exceeds monotonic run interval')
    require(equal(record['summaries'], expected_summaries(record['rows'])), 'summary mismatch')
    return {'run_id': record['run_id'], 'rows': 216, 'cells': 24}


def validate_journal(events, result):
    require(type(events) is list and len(events) == 218, 'journal event count')
    metadata = {k: value for k, value in result.items()
                if k not in ('rows', 'summaries', 'finished_at_utc', 'elapsed_monotonic_seconds')}
    metadata['status'] = 'running'
    require(equal(events[0], {'event': 'start', 'metadata': metadata}), 'journal metadata mismatch')
    for event, row in zip(events[1:-1], result['rows']):
        require(equal(event, {'event': 'row', 'row': row}), 'journal row mismatch')
    require(equal(events[-1], {'event': 'finish', 'status': 'complete', 'rows': 216,
                              'finished_at_utc': result['finished_at_utc'],
                              'elapsed_monotonic_seconds': result['elapsed_monotonic_seconds']}), 'journal finish mismatch')


def verify(directory):
    freeze_path = ROOT / 'PRE_DATA_SHA256.json'
    freeze = read_json(freeze_path)
    require(type(freeze) is dict and set(freeze) ==
            {'schema', 'upstream_commit', 'frozen_at_utc', 'sources'}, 'freeze fields')
    require(type(freeze['schema']) is int and freeze['schema'] == 1 and
            freeze['upstream_commit'] == '9e3215eebf92a3a4ae3f74275494cc754a45c06b', 'freeze identity')
    require(type(freeze['sources']) is dict and set(freeze['sources']) == SOURCE_FILES, 'freeze source inventory')
    require(freeze['sources']['../tcp-framing-codec/mesh_codec.py'] == CODEC_SHA256, 'upstream codec changed')
    for name, expected in freeze['sources'].items():
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, 'source changed: ' + name)
    result = read_json(directory / 'result.json')
    outcome = validate_record(result, freeze['sources'], hashlib.sha256(freeze_path.read_bytes()).hexdigest())
    require(utc(result['started_at_utc']) >= utc(freeze['frozen_at_utc']), 'run precedes source freeze')
    journal_path = directory / 'journal.jsonl'
    require(journal_path.stat().st_size <= MAX_BYTES, 'journal exceeds size cap')
    events = [parse_json(line) for line in journal_path.read_text(encoding='utf-8').splitlines()]
    validate_journal(events, result)
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories', nargs='+', type=Path)
    args = parser.parse_args()
    outcomes = [verify(directory) for directory in args.directories]
    require(len({item['run_id'] for item in outcomes}) == len(outcomes), 'duplicate run ids')
    print(json.dumps({'status': 'verified', 'runs': outcomes}, indent=2))


if __name__ == '__main__':
    main()
