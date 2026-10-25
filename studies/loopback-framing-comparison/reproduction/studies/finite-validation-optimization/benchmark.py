"""Frozen paired finite-validation benchmark. No sockets or model execution."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import gc
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import struct
import sys
import time
import tracemalloc
import uuid

ROOT = Path(__file__).resolve().parent
BASELINE_COMMIT = 'ce945115f7fcf8f4da559cc5026d8a0157b5fa7d'
CODEC_SHA256 = '3fcb2b2dffd7d95e56d4887ce02a63482ff612b4a7c0313e9fbcb715a419b5aa'
SOURCE_FILES = ('PROTOCOL.md', 'benchmark.py', 'verify_results.py',
                'test_benchmark.py', 'test_verify_results.py', 'candidate_codec.py',
                'test_candidate_codec.py', 'BASELINE_PRE_DATA.json',
                '../tcp-framing-codec/mesh_codec.py', '../tcp-framing-codec/test_mesh_codec.py')
CASE_NAMES = ('activation_decode', 'activation_prefill_16', 'activation_prefill_64', 'audit_reply')
OPERATIONS = ('finite_scan', 'frame_pack', 'frame_decode')
VARIANTS = ('baseline', 'candidate')
CONFIG = {'blocks': 10, 'iterations': 50, 'warmup': 5, 'seed': 20261025,
          'allocation_blocks': 4, 'allocation_iterations': 1, 'tracemalloc_frames': 1}
MAX_SECONDS = 180
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
SCOPE = 'single-host paired finite-validation optimization; no sockets, mesh, model, inference, device, RSS, or total-allocation claim'
PROCESS_INSTANCE = uuid.uuid4().hex


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BASELINE = load_module('_finite_validation_baseline_codec', ROOT.parent / 'tcp-framing-codec/mesh_codec.py')
CANDIDATE = load_module('_finite_validation_candidate_codec', ROOT / 'candidate_codec.py')
CODECS = {'baseline': BASELINE, 'candidate': CANDIDATE}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def baseline_scan(tensor):
    # Original codec predicate, with the same one-helper-call wrapper as candidate.
    return all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', tensor))


@dataclass(frozen=True)
class Case:
    tensor: bytes
    payload: bytes
    wire: bytes
    frames: dict


def build_cases():
    cases = {}
    for name, length, prior, audit in [
        ('activation_decode', 1, 1, False),
        ('activation_prefill_16', 16, 0, False),
        ('activation_prefill_64', 64, 0, False),
        ('audit_reply', 1, 1, True),
    ]:
        count = 49152 if audit else 576 * length
        tensor = struct.pack('<' + 'f' * count,
                             *(((i % 257) - 128) / 128 for i in range(count)))
        payload = struct.pack('>I', 7) + tensor if audit else tensor
        frames = {}
        for variant, codec in CODECS.items():
            header = codec.Header(codec.Kind.AUDIT if audit else codec.Kind.ACTIVATION_RESULT,
                                  1 if audit else 0, codec.Mode.AUDIT if audit else codec.Mode.TOKEN,
                                  bytes(range(16)), 0, 1, prior, length, len(payload))
            frames[variant] = codec.Frame(header, payload)
        wire = frames['baseline'].pack()
        case = Case(tensor, payload, wire, frames)
        for variant, codec in CODECS.items():
            check_result(case, variant, 'frame_pack', frames[variant].pack())
            check_result(case, variant, 'frame_decode', codec.Decoder().consume(wire))
        cases[name] = case
    return cases


def operations(case, variant):
    codec = CODECS[variant]
    scan = baseline_scan if variant == 'baseline' else codec.finite_scan
    return {'finite_scan': lambda: scan(case.tensor),
            'frame_pack': case.frames[variant].pack,
            'frame_decode': lambda: codec.Decoder().consume(case.wire)}


def check_result(case, variant, operation, result):
    valid = False
    if operation == 'finite_scan':
        valid = result is True
    elif operation == 'frame_pack':
        valid = type(result) is bytes and result == case.wire
    elif operation == 'frame_decode':
        valid = (type(result) is tuple and len(result) == 2 and
                 type(result[0]) is int and result[0] == len(case.wire) and
                 type(result[1]) is CODECS[variant].Frame and result[1] == case.frames[variant])
    if not valid:
        raise ValueError('operation correctness gate failed: ' + variant + '/' + operation)


def make_schedule(phase):
    if phase not in ('latency', 'allocation'):
        raise ValueError('unknown phase')
    blocks = CONFIG['blocks'] if phase == 'latency' else CONFIG['allocation_blocks']
    if type(blocks) is not int or blocks < 2 or blocks % 2:
        raise ValueError('balanced schedule requires an even block count')
    rng = random.Random(CONFIG['seed'] + (phase == 'allocation'))
    cells = [(case, operation, index)
             for index, (case, operation) in enumerate((c, o) for c in CASE_NAMES for o in OPERATIONS)]
    schedule = []
    for block in range(blocks):
        ordered = cells.copy()
        rng.shuffle(ordered)
        for pair, (case, operation, index) in enumerate(ordered):
            variants = VARIANTS if (block + index) % 2 == 0 else VARIANTS[::-1]
            pair_order = 'AB' if variants[0] == 'baseline' else 'BA'
            for position, variant in enumerate(variants):
                schedule.append({'block': block, 'pair': pair, 'order': pair * 2 + position,
                                 'case': case, 'operation': operation, 'variant': variant,
                                 'position': position, 'pair_order': pair_order})
    return schedule


def measure_batch(operation, iterations, wall_clock=time.perf_counter_ns,
                  cpu_clock=time.process_time_ns):
    if type(iterations) is not int or not 1 <= iterations <= 10000:
        raise ValueError('iterations must be an integer in 1..10000')
    if tracemalloc.is_tracing():
        raise ValueError('allocation tracing must be off during latency')
    wall_start = wall_clock()
    cpu_start = cpu_clock()
    last = None
    for _ in range(iterations):
        last = operation()
    cpu_end = cpu_clock()
    wall_end = wall_clock()
    if any(type(n) is not int for n in (wall_start, cpu_start, cpu_end, wall_end)):
        raise ValueError('noninteger timer reading')
    wall_ns, cpu_ns = wall_end - wall_start, cpu_end - cpu_start
    if wall_ns <= 0 or cpu_ns <= 0:
        raise ValueError('nonpositive timer interval')
    if wall_ns >= MAX_SECONDS * 1_000_000_000 or cpu_ns >= MAX_SECONDS * 1_000_000_000:
        raise ValueError('batch timer interval exceeds run budget')
    return {'iterations': iterations, 'wall_ns': wall_ns, 'cpu_ns': cpu_ns,
            'wall_ns_per_op': wall_ns / iterations,
            'cpu_ns_per_op': cpu_ns / iterations}, last


def measure_allocation(operation, tracer=tracemalloc):
    """One call, fresh tracer session; counters are live/peak bytes, not churn."""
    if tracer.is_tracing():
        raise ValueError('preexisting allocation tracer session')
    tracer.start(CONFIG['tracemalloc_frames'])
    try:
        before, initial_peak = tracer.get_traced_memory()
        tracer.reset_peak()
        last = operation()
        current, peak = tracer.get_traced_memory()
    finally:
        tracer.stop()
    if any(type(n) is not int or n < 0 for n in (before, initial_peak, current, peak)) or peak < current:
        raise ValueError('invalid allocation counters')
    return {'iterations': 1, 'before_bytes': before, 'current_bytes': current,
            'peak_bytes': peak, 'retained_bytes': current - before,
            'peak_increment_bytes': max(0, peak - before)}, last


def describe(values):
    values = [float(n) for n in values]
    if len(values) < 2 or not all(math.isfinite(n) for n in values):
        raise ValueError('at least two finite observations required')
    q1, _, q3 = statistics.quantiles(values, n=4, method='inclusive')
    return {'median': float(statistics.median(values)), 'min': min(values), 'max': max(values),
            'iqr': float(q3 - q1)}


def summarize(rows, metrics, paired_metrics):
    summaries, paired = [], []
    cells = sorted({(row['case'], row['operation']) for row in rows})
    for case, operation in cells:
        group = [r for r in rows if (r['case'], r['operation']) == (case, operation)]
        for variant in VARIANTS:
            observations = [r for r in group if r['variant'] == variant]
            entry = {'case': case, 'operation': operation, 'variant': variant, 'samples': len(observations)}
            entry.update({metric: describe(r[metric] for r in observations) for metric in metrics})
            summaries.append(entry)
        pairs = {}
        for row in group:
            if row['variant'] in pairs.setdefault(row['block'], {}):
                raise ValueError('duplicate variant in pair')
            pairs[row['block']][row['variant']] = row
        if any(set(pair) != set(VARIANTS) for pair in pairs.values()):
            raise ValueError('incomplete pair')
        entry = {'case': case, 'operation': operation, 'pairs': len(pairs)}
        for name, metric, mode in paired_metrics:
            values = []
            for pair in pairs.values():
                a, c = pair['baseline'][metric], pair['candidate'][metric]
                values.append(c / a if mode == 'ratio' else c - a)
            entry[name] = describe(values)
        paired.append(entry)
    return summaries, paired


def summarize_latency(rows):
    return summarize(rows, ('wall_ns_per_op', 'cpu_ns_per_op'),
                     [('wall_ratio', 'wall_ns_per_op', 'ratio'),
                      ('cpu_ratio', 'cpu_ns_per_op', 'ratio'),
                      ('wall_delta_ns', 'wall_ns_per_op', 'delta'),
                      ('cpu_delta_ns', 'cpu_ns_per_op', 'delta')])


def summarize_allocations(rows):
    return summarize(rows, ('retained_bytes', 'peak_increment_bytes'),
                     [('retained_delta_bytes', 'retained_bytes', 'delta'),
                      ('peak_delta_bytes', 'peak_increment_bytes', 'delta')])


def check_hashes(root, expected):
    for name, digest in expected.items():
        try:
            actual = sha256((root / name).read_bytes())
        except OSError as exc:
            raise ValueError('frozen source unavailable: ' + name) from exc
        if actual != digest:
            raise ValueError('frozen source changed: ' + name)


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('duplicate JSON key')
            value[key] = item
        return value
    def bad_constant(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def check_baseline_inventory(root=None):
    root = ROOT if root is None else Path(root)
    path = root / 'BASELINE_PRE_DATA.json'
    if path.stat().st_size > MAX_OUTPUT_BYTES:
        raise ValueError('baseline inventory size cap exceeded')
    inventory = strict_json(path.read_bytes())
    fields = {'schema', 'published_baseline_commit', 'local_base_commit', 'scope', 'checked_at_utc', 'files'}
    if (type(inventory) is not dict or set(inventory) != fields or
        type(inventory['schema']) is not int or inventory['schema'] != 1 or
        inventory['published_baseline_commit'] != BASELINE_COMMIT or
        type(inventory['files']) is not list or len(inventory['files']) != 62):
        raise ValueError('invalid baseline inventory')
    names = set()
    for entry in inventory['files']:
        if type(entry) is not dict or set(entry) != {'path', 'sha256', 'git_blob_sha1'}:
            raise ValueError('invalid baseline file entry')
        name = entry['path']
        if (type(name) is not str or not name or Path(name).is_absolute() or
            '..' in Path(name).parts or str(Path(name)) != name or name in names):
            raise ValueError('invalid or duplicate baseline path')
        names.add(name)
        for key, size in [('sha256', 64), ('git_blob_sha1', 40)]:
            digest = entry[key]
            if type(digest) is not str or len(digest) != size or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('invalid baseline digest')
        data = (root.parent.parent / name).read_bytes()
        blob = b'blob ' + str(len(data)).encode('ascii') + b'\0' + data
        if sha256(data) != entry['sha256'] or hashlib.sha1(blob).hexdigest() != entry['git_blob_sha1']:
            raise ValueError('preserved baseline changed: ' + name)


def load_freeze():
    path = ROOT / 'PRE_DATA_SHA256.json'
    if path.stat().st_size > MAX_OUTPUT_BYTES:
        raise ValueError('freeze size cap exceeded')
    raw = path.read_bytes()
    freeze = strict_json(raw)
    if (type(freeze) is not dict or set(freeze) != {'schema', 'baseline_commit', 'frozen_at_utc', 'sources'} or
        type(freeze['schema']) is not int or freeze['schema'] != 1 or
        freeze['baseline_commit'] != BASELINE_COMMIT or type(freeze['sources']) is not dict or
        set(freeze['sources']) != set(SOURCE_FILES)):
        raise ValueError('invalid freeze manifest')
    if type(freeze['frozen_at_utc']) is not str:
        raise ValueError('invalid freeze timestamp')
    frozen = datetime.fromisoformat(freeze['frozen_at_utc'])
    if frozen.utcoffset() != timedelta(0) or frozen > datetime.now(timezone.utc):
        raise ValueError('freeze must be UTC and precede collection')
    for digest in freeze['sources'].values():
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('invalid source digest')
    if freeze['sources']['../tcp-framing-codec/mesh_codec.py'] != CODEC_SHA256:
        raise ValueError('baseline codec changed')
    check_hashes(ROOT, freeze['sources'])
    check_baseline_inventory()
    return freeze, sha256(raw)


def write_exclusive(path, data):
    encoded = json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n'
    if len(encoded.encode('utf-8')) > MAX_OUTPUT_BYTES:
        raise ValueError('output size cap exceeded')
    with Path(path).open('x', encoding='utf-8') as output:
        output.write(encoded)


class Journal:
    def __init__(self, stream, limit=MAX_OUTPUT_BYTES):
        self.stream, self.limit, self.size = stream, limit, 0

    def emit(self, event):
        encoded = json.dumps(event, sort_keys=True, allow_nan=False) + '\n'
        size = len(encoded.encode('utf-8'))
        reserve = 0 if event['event'] == 'finish' else 4096
        if self.size + size + reserve > self.limit:
            raise ValueError('journal size cap exceeded')
        self.stream.write(encoded)
        self.stream.flush()
        self.size += size


def environment():
    clocks = {}
    for name in ('perf_counter', 'process_time', 'monotonic'):
        info = time.get_clock_info(name)
        clocks[name] = {'implementation': info.implementation, 'resolution_seconds': info.resolution,
                        'monotonic': info.monotonic, 'adjustable': info.adjustable}
    cpu_model = None
    cpu_quota = None
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name'):
                cpu_model = line.split(':', 1)[1].strip()
                break
    except OSError:
        pass
    try:
        cpu_quota = Path('/sys/fs/cgroup/cpu.max').read_text().strip()
    except OSError:
        pass
    return {'python': platform.python_version(), 'implementation': platform.python_implementation(),
            'system': platform.system(), 'release': platform.release(), 'machine': platform.machine(),
            'logical_cpus': os.cpu_count(), 'cpu_model': cpu_model, 'cgroup_cpu_max': cpu_quota,
            'timers': clocks, 'gc_enabled': gc.isenabled(), 'gc_threshold': list(gc.get_threshold()),
            'byteorder': sys.byteorder, 'native_float_format': getattr(float, '__getformat__', lambda _: 'unknown')('float'),
            'candidate_native_fp32_le': CANDIDATE._NATIVE_FP32_LE}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run(run_id, emit=lambda event: None, wall_clock=time.perf_counter_ns,
        cpu_clock=time.process_time_ns, budget_clock=time.monotonic,
        allocation_sampler=measure_allocation):
    if run_id not in ('run-001', 'run-002'):
        raise ValueError('run id must be run-001 or run-002')
    monotonic_start = budget_clock()
    previous = monotonic_start
    result = {'schema': 1, 'status': 'running', 'run_id': run_id, 'scope': SCOPE,
              'started_at_utc': utc_now(), 'config': dict(CONFIG), 'process_instance': PROCESS_INSTANCE,
              'rows': [], 'allocation_rows': []}
    phase = 'setup'
    def check_budget():
        nonlocal previous
        now = budget_clock()
        if (type(now) not in (int, float) or type(previous) not in (int, float) or
            not math.isfinite(now) or not math.isfinite(previous) or now < previous):
            raise ValueError('invalid or reversing monotonic clock')
        previous = now
        if now - monotonic_start >= MAX_SECONDS:
            raise TimeoutError('cooperative run time budget exceeded')
        return now
    try:
        if tracemalloc.is_tracing():
            raise ValueError('allocation tracing must be off at run start')
        freeze, freeze_sha = load_freeze()
        check_budget()
        cases = build_cases()
        functions = {(name, variant): operations(case, variant)
                     for name, case in cases.items() for variant in VARIANTS}
        result.update(environment=environment(), freeze_sha256=freeze_sha, sources=freeze['sources'],
                      inputs={name: {'payload_bytes': len(case.payload), 'frame_bytes': len(case.wire),
                                     'payload_sha256': sha256(case.payload), 'frame_sha256': sha256(case.wire)}
                              for name, case in cases.items()},
                      latency_schedule=make_schedule('latency'), allocation_schedule=make_schedule('allocation'))
        emit({'event': 'start', 'metadata': {k: v for k, v in result.items() if k not in ('rows', 'allocation_rows')}})
        phase = 'warmup'
        for name, case in cases.items():
            for operation in OPERATIONS:
                for variant in VARIANTS:
                    check_budget()
                    for _ in range(CONFIG['warmup']):
                        check_result(case, variant, operation, functions[name, variant][operation]())
                    check_budget()
        for phase, schedule_name, row_name, event_name in [
            ('latency', 'latency_schedule', 'rows', 'row'),
            ('allocation', 'allocation_schedule', 'allocation_rows', 'allocation_row'),
        ]:
            for entry in result[schedule_name]:
                check_budget()
                name, variant, operation = entry['case'], entry['variant'], entry['operation']
                function = functions[name, variant][operation]
                check_result(cases[name], variant, operation, function())
                if phase == 'latency':
                    measured, last = measure_batch(function, CONFIG['iterations'], wall_clock, cpu_clock)
                else:
                    measured, last = allocation_sampler(function)
                check_result(cases[name], variant, operation, last)
                del last
                row = dict(entry, **measured)
                result[row_name].append(row)
                emit({'event': event_name, 'row': row})
                check_budget()
        phase = 'finalization'
        check_hashes(ROOT, freeze['sources'])
        check_baseline_inventory()
        result['summaries'], result['paired_summaries'] = summarize_latency(result['rows'])
        result['allocation_summaries'], result['allocation_paired_summaries'] = summarize_allocations(result['allocation_rows'])
        check_budget()
        result['status'] = 'complete'
    except Exception as exc:
        result.update(status='failed', failure_type=type(exc).__name__, failure_phase=phase)
    result['finished_at_utc'] = utc_now()
    try:
        elapsed = float(check_budget() - monotonic_start)
        if elapsed <= 0:
            raise ValueError('nonpositive monotonic run interval')
        result['elapsed_monotonic_seconds'] = elapsed
        if result['status'] == 'complete':
            utc_elapsed = (datetime.fromisoformat(result['finished_at_utc']) -
                           datetime.fromisoformat(result['started_at_utc'])).total_seconds()
            wall_total = sum(row['wall_ns'] for row in result['rows'])
            if wall_total > elapsed * 1e9 or utc_elapsed < 0 or wall_total > (utc_elapsed + 0.001) * 1e9:
                raise ValueError('timing total exceeds enclosing run interval')
    except Exception as exc:
        result['elapsed_monotonic_seconds'] = None
        if result['status'] == 'complete':
            result.update(status='failed', failure_type=type(exc).__name__, failure_phase='finalization')
    terminal = {'event': 'finish', 'status': result['status'], 'rows': len(result['rows']),
                'allocation_rows': len(result['allocation_rows']),
                'finished_at_utc': result['finished_at_utc'],
                'elapsed_monotonic_seconds': result['elapsed_monotonic_seconds']}
    if result['status'] == 'failed':
        terminal.update(failure_type=result['failure_type'], failure_phase=result['failure_phase'])
    emit(terminal)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True, choices=('run-001', 'run-002'))
    parser.add_argument('--output', required=True, type=Path, help='new directory, never overwritten')
    args = parser.parse_args()
    load_freeze()  # Do not create output or collect data when the freeze is absent/invalid.
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / 'journal.jsonl').open('x', encoding='utf-8') as stream:
        result = run(args.run_id, Journal(stream).emit)
    write_exclusive(args.output / 'result.json', result)
    print(json.dumps({'status': result['status'], 'run_id': args.run_id,
                      'rows': len(result['rows']), 'allocation_rows': len(result['allocation_rows'])}))
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
