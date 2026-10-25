"""Frozen, single-process framing-cost controls. No networking or model code."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import gc
import hashlib
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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'tcp-framing-codec'))
from mesh_codec import Decoder, Frame, Header, Kind, Mode  # noqa: E402

UPSTREAM = '9e3215eebf92a3a4ae3f74275494cc754a45c06b'
CASE_NAMES = ('activation_decode', 'activation_prefill_16',
              'activation_prefill_64', 'audit_reply')
OPERATIONS = ('noop', 'payload_copy', 'header_pack', 'finite_scan',
              'frame_pack', 'frame_decode')
CONFIG = {'blocks': 9, 'iterations': 50, 'warmup': 5, 'seed': 20261025}
MAX_SECONDS = 180
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
SOURCE_FILES = ('PROTOCOL.md', 'benchmark.py', 'verify_results.py',
                'test_benchmark.py', 'test_verify_results.py',
                'BASELINE_UPSTREAM.json', 'BASELINE_PRE_DATA.json',
                '../tcp-framing-codec/mesh_codec.py')
SCOPE = 'single-host single-process framing controls; no sockets, mesh, model, inference, or device claim'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Case:
    frame: Frame
    tensor: bytes
    wire: bytes
    header_bytes: bytes


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
        header = Header(Kind.AUDIT if audit else Kind.ACTIVATION_RESULT,
                        1 if audit else 0, Mode.AUDIT if audit else Mode.TOKEN,
                        bytes(range(16)), 0, 1, prior, length, len(payload))
        frame = Frame(header, payload)
        wire = frame.pack()
        case = Case(frame, tensor, wire, header.pack())
        check_result(case, 'frame_decode', Decoder().consume(wire))
        cases[name] = case
    return cases


def operations(case):
    return {
        'noop': lambda: None,
        'payload_copy': lambda: memoryview(case.frame.payload).tobytes(),
        'header_pack': case.frame.header.pack,
        'finite_scan': lambda: all(math.isfinite(x[0])
                                   for x in struct.iter_unpack('<f', case.tensor)),
        'frame_pack': case.frame.pack,
        'frame_decode': lambda: Decoder().consume(case.wire),
    }


def check_result(case, operation, result):
    valid = False
    if operation == 'noop':
        valid = result is None
    elif operation == 'payload_copy':
        valid = type(result) is bytes and result == case.frame.payload and result is not case.frame.payload
    elif operation == 'header_pack':
        valid = type(result) is bytes and result == case.header_bytes
    elif operation == 'finite_scan':
        valid = result is True
    elif operation == 'frame_pack':
        valid = type(result) is bytes and result == case.wire
    elif operation == 'frame_decode':
        valid = (type(result) is tuple and len(result) == 2 and
                 type(result[0]) is int and result[0] == len(case.wire) and
                 type(result[1]) is Frame and result[1] == case.frame)
    if not valid:
        raise ValueError('operation correctness gate failed: ' + operation)


def make_schedule():
    rng = random.Random(CONFIG['seed'])
    cells = [(case, operation) for case in CASE_NAMES for operation in OPERATIONS]
    schedule = []
    for block in range(CONFIG['blocks']):
        ordered = cells.copy()
        rng.shuffle(ordered)
        schedule.extend({'block': block, 'order': order, 'case': case, 'operation': operation}
                        for order, (case, operation) in enumerate(ordered))
    return schedule


def measure_batch(operation, iterations, wall_clock=time.perf_counter_ns,
                  cpu_clock=time.process_time_ns):
    if type(iterations) is not int or not 1 <= iterations <= 10000:
        raise ValueError('iterations must be an integer in 1..10000')
    wall_start = wall_clock()
    cpu_start = cpu_clock()
    last = None
    for _ in range(iterations):
        last = operation()
    cpu_ns = cpu_clock() - cpu_start
    wall_ns = wall_clock() - wall_start
    if type(wall_ns) is not int or type(cpu_ns) is not int or wall_ns <= 0 or cpu_ns <= 0:
        raise ValueError('nonpositive or noninteger timer interval')
    return {'iterations': iterations, 'wall_ns': wall_ns, 'cpu_ns': cpu_ns,
            'wall_ns_per_op': wall_ns / iterations,
            'cpu_ns_per_op': cpu_ns / iterations}, last


def summarize(rows):
    result = []
    for case, operation in sorted({(r['case'], r['operation']) for r in rows}):
        group = [r for r in rows if (r['case'], r['operation']) == (case, operation)]
        summary = {'case': case, 'operation': operation, 'batches': len(group)}
        for metric in ('wall_ns_per_op', 'cpu_ns_per_op'):
            values = [r[metric] for r in group]
            if len(values) < 2:
                raise ValueError('at least two batch observations required')
            q1, _, q3 = statistics.quantiles(values, n=4, method='inclusive')
            summary[metric] = {'median': statistics.median(values), 'min': min(values),
                               'max': max(values), 'iqr': q3 - q1}
        result.append(summary)
    return result


def check_hashes(root, expected):
    for name, digest in expected.items():
        try:
            actual = sha256((root / name).read_bytes())
        except OSError as exc:
            raise ValueError('frozen source unavailable: ' + name) from exc
        if actual != digest:
            raise ValueError('frozen source changed: ' + name)


def load_freeze():
    raw = (ROOT / 'PRE_DATA_SHA256.json').read_bytes()
    freeze = json.loads(raw)
    if (set(freeze) != {'schema', 'upstream_commit', 'frozen_at_utc', 'sources'} or
        freeze['schema'] != 1 or freeze['upstream_commit'] != UPSTREAM or
        set(freeze['sources']) != set(SOURCE_FILES)):
        raise ValueError('invalid freeze manifest')
    for digest in freeze['sources'].values():
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('invalid source digest')
    check_hashes(ROOT, freeze['sources'])
    return freeze, sha256(raw)


def write_exclusive(path, data):
    encoded = json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n'
    if len(encoded.encode('utf-8')) > MAX_OUTPUT_BYTES:
        raise ValueError('output size cap exceeded')
    with Path(path).open('x', encoding='utf-8') as output:
        output.write(encoded)


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
            'timers': clocks, 'gc_enabled': gc.isenabled(), 'gc_threshold': list(gc.get_threshold())}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run(run_id, emit=lambda event: None, wall_clock=time.perf_counter_ns,
        cpu_clock=time.process_time_ns, budget_clock=time.monotonic):
    if run_id not in ('run-001', 'run-002'):
        raise ValueError('run id must be run-001 or run-002')
    monotonic_start = budget_clock()
    deadline = monotonic_start + MAX_SECONDS
    result = {'schema': 1, 'status': 'running', 'run_id': run_id, 'scope': SCOPE,
              'started_at_utc': utc_now(), 'config': dict(CONFIG), 'rows': []}
    phase = 'setup'
    def check_budget():
        if budget_clock() >= deadline:
            raise TimeoutError('cooperative run time budget exceeded')
    try:
        freeze, freeze_sha = load_freeze()
        cases = build_cases()
        functions = {name: operations(case) for name, case in cases.items()}
        result.update(environment=environment(), freeze_sha256=freeze_sha, sources=freeze['sources'],
                      inputs={name: {'payload_bytes': len(case.frame.payload), 'frame_bytes': len(case.wire),
                                     'payload_sha256': sha256(case.frame.payload), 'frame_sha256': sha256(case.wire)}
                              for name, case in cases.items()}, schedule=make_schedule())
        emit({'event': 'start', 'metadata': {key: value for key, value in result.items() if key != 'rows'}})
        phase = 'warmup'
        for name, case in cases.items():
            for operation in OPERATIONS:
                check_budget()
                for _ in range(CONFIG['warmup']):
                    check_result(case, operation, functions[name][operation]())
                check_budget()
        phase = 'measurement'
        for entry in result['schedule']:
            check_budget()
            name, operation = entry['case'], entry['operation']
            function = functions[name][operation]
            check_result(cases[name], operation, function())
            measured, last = measure_batch(function, CONFIG['iterations'], wall_clock, cpu_clock)
            check_result(cases[name], operation, last)
            row = dict(entry, **measured)
            result['rows'].append(row)
            emit({'event': 'row', 'row': row})
            check_budget()
        phase = 'finalization'
        check_hashes(ROOT, freeze['sources'])
        result['summaries'] = summarize(result['rows'])
        check_budget()
        result['status'] = 'complete'
    except Exception as exc:
        result['status'] = 'failed'
        result['failure_type'] = type(exc).__name__
        result['failure_phase'] = phase
    result['finished_at_utc'] = utc_now()
    result['elapsed_monotonic_seconds'] = float(budget_clock() - monotonic_start)
    if result['status'] == 'complete' and result['elapsed_monotonic_seconds'] >= MAX_SECONDS:
        result.update(status='failed', failure_type='TimeoutError', failure_phase='finalization')
    terminal = {'event': 'finish', 'status': result['status'], 'rows': len(result['rows']),
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
    load_freeze()  # Refuse changed/missing frozen inputs before collection/output creation.
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / 'journal.jsonl').open('x', encoding='utf-8') as journal:
        def emit(event):
            encoded = json.dumps(event, sort_keys=True, allow_nan=False) + '\n'
            # Reserve terminal-record space so ordinary budget failure is retained.
            reserve = 0 if event['event'] == 'finish' else 4096
            if journal.tell() + len(encoded.encode('utf-8')) + reserve > MAX_OUTPUT_BYTES:
                raise ValueError('journal size cap exceeded')
            journal.write(encoded)
            journal.flush()  # Outside timing; ordinary failure/interruption retains preceding rows.
        result = run(args.run_id, emit)
    write_exclusive(args.output / 'result.json', result)
    print(json.dumps({'status': result['status'], 'run_id': args.run_id, 'rows': len(result['rows'])}))
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
