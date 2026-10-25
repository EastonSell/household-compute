"""Adversarial verifier tests. All observations are fabricated, never measured."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if (ROOT / 'verify_results.py').exists():
    spec = importlib.util.spec_from_file_location('finite_validation_verifier', ROOT / 'verify_results.py')
    v = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = v
    spec.loader.exec_module(v)
else:
    v = None

CASES = ['activation_decode', 'activation_prefill_16', 'activation_prefill_64', 'audit_reply']
OPS = ['finite_scan', 'frame_pack', 'frame_decode']
SOURCE_FILES = ['PROTOCOL.md', 'benchmark.py', 'verify_results.py', 'test_benchmark.py',
                'test_verify_results.py', 'candidate_codec.py', 'test_candidate_codec.py',
                'BASELINE_PRE_DATA.json', '../tcp-framing-codec/mesh_codec.py',
                '../tcp-framing-codec/test_mesh_codec.py']


def synthetic_schedule(blocks, seed):
    rng = random.Random(seed)
    plan = []
    for block in range(blocks):
        cells = [(case, op) for case in CASES for op in OPS]
        rng.shuffle(cells)
        for pair, (case, op) in enumerate(cells):
            index = CASES.index(case) * 3 + OPS.index(op)
            variants = ['baseline', 'candidate'] if (block + index) % 2 == 0 else ['candidate', 'baseline']
            for position, variant in enumerate(variants):
                plan.append({'block': block, 'pair': pair, 'order': 2 * pair + position,
                             'case': case, 'operation': op, 'variant': variant,
                             'position': position, 'pair_order': 'AB' if variants[0] == 'baseline' else 'BA'})
    return plan


def constant_stats(value):
    return {'median': float(value), 'min': float(value), 'max': float(value), 'iqr': 0.0}


def synthetic_result():
    inputs = {}
    for name, count, length, prior, audit in [
        ('activation_decode', 576, 1, 1, False), ('activation_prefill_16', 9216, 16, 0, False),
        ('activation_prefill_64', 36864, 64, 0, False), ('audit_reply', 49152, 1, 1, True),
    ]:
        tensor = struct.pack('<' + 'f' * count, *[((i % 257) - 128) / 128 for i in range(count)])
        body = struct.pack('>I', 7) + tensor if audit else tensor
        wire = struct.pack('>4sBBBB16s6I16s', b'CMTP', 1, 9 if audit else 7,
                           1 if audit else 0, 2 if audit else 1, bytes(range(16)),
                           0, 1, prior, length, len(body), 0, bytes(16)) + body
        inputs[name] = {'payload_bytes': len(body), 'frame_bytes': len(wire),
                        'payload_sha256': hashlib.sha256(body).hexdigest(),
                        'frame_sha256': hashlib.sha256(wire).hexdigest()}
    latency = synthetic_schedule(10, 20261025)
    allocation = synthetic_schedule(4, 20261026)
    rows, allocation_rows = [], []
    for entry in latency:
        wall = 1000 if entry['variant'] == 'baseline' else 500
        rows.append(dict(entry, iterations=50, wall_ns=wall, cpu_ns=wall // 2,
                         wall_ns_per_op=wall / 50, cpu_ns_per_op=wall / 100))
    for entry in allocation:
        retained = 80 if entry['variant'] == 'baseline' else 40
        allocation_rows.append(dict(entry, iterations=1, before_bytes=100, current_bytes=100 + retained,
                                    peak_bytes=100 + retained * 5, retained_bytes=retained,
                                    peak_increment_bytes=retained * 5))
    summaries, paired, allocations, allocation_paired = [], [], [], []
    for case in sorted(CASES):
        for op in sorted(OPS):
            for variant in ['baseline', 'candidate']:
                n = 20 if variant == 'baseline' else 10
                summaries.append({'case': case, 'operation': op, 'variant': variant, 'samples': 10,
                                  'wall_ns_per_op': constant_stats(n), 'cpu_ns_per_op': constant_stats(n / 2)})
                r = 80 if variant == 'baseline' else 40
                allocations.append({'case': case, 'operation': op, 'variant': variant, 'samples': 4,
                                    'retained_bytes': constant_stats(r), 'peak_increment_bytes': constant_stats(r * 5)})
            paired.append({'case': case, 'operation': op, 'pairs': 10, 'wall_ratio': constant_stats(0.5),
                           'cpu_ratio': constant_stats(0.5), 'wall_delta_ns': constant_stats(-10),
                           'cpu_delta_ns': constant_stats(-5)})
            allocation_paired.append({'case': case, 'operation': op, 'pairs': 4,
                                      'retained_delta_bytes': constant_stats(-40), 'peak_delta_bytes': constant_stats(-200)})
    timer = {'implementation': 'synthetic', 'resolution_seconds': 1e-9, 'monotonic': True, 'adjustable': False}
    environment = {'python': '3.12.0', 'implementation': 'CPython', 'system': 'Linux', 'release': 'synthetic',
                   'machine': 'x86_64', 'logical_cpus': 2, 'cpu_model': None, 'cgroup_cpu_max': None,
                   'timers': {name: dict(timer) for name in ['perf_counter', 'process_time', 'monotonic']},
                   'gc_enabled': True, 'gc_threshold': [700, 10, 10], 'byteorder': 'little',
                   'native_float_format': 'IEEE, little-endian', 'candidate_native_fp32_le': True}
    return {'schema': 1, 'status': 'complete', 'run_id': 'run-001',
            'scope': 'single-host paired finite-validation optimization; no sockets, mesh, model, inference, device, RSS, or total-allocation claim',
            'started_at_utc': '2026-10-25T07:00:00+00:00', 'finished_at_utc': '2026-10-25T07:00:01+00:00',
            'elapsed_monotonic_seconds': 1.0, 'process_instance': '1' * 32,
            'config': {'blocks': 10, 'iterations': 50, 'warmup': 5, 'seed': 20261025,
                       'allocation_blocks': 4, 'allocation_iterations': 1, 'tracemalloc_frames': 1},
            'environment': environment, 'freeze_sha256': 'a' * 64,
            'sources': {name: 'b' * 64 for name in SOURCE_FILES}, 'inputs': inputs,
            'latency_schedule': latency, 'allocation_schedule': allocation,
            'rows': rows, 'allocation_rows': allocation_rows, 'summaries': summaries,
            'paired_summaries': paired, 'allocation_summaries': allocations,
            'allocation_paired_summaries': allocation_paired}


def synthetic_journal(record):
    omitted = {'rows', 'allocation_rows', 'summaries', 'paired_summaries', 'allocation_summaries',
               'allocation_paired_summaries', 'finished_at_utc', 'elapsed_monotonic_seconds'}
    metadata = {key: value for key, value in record.items() if key not in omitted}
    metadata['status'] = 'running'
    return ([{'event': 'start', 'metadata': metadata}] +
            [{'event': 'row', 'row': row} for row in record['rows']] +
            [{'event': 'allocation_row', 'row': row} for row in record['allocation_rows']] +
            [{'event': 'finish', 'status': 'complete', 'rows': 240, 'allocation_rows': 96,
              'finished_at_utc': record['finished_at_utc'],
              'elapsed_monotonic_seconds': record['elapsed_monotonic_seconds']}])


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(v, 'independent verifier has not been implemented')
        self.original = synthetic_result()

    def validate(self, record):
        return v.validate_record(record, self.original['sources'], self.original['freeze_sha256'])

    def test_synthetic_complete_grid_and_journal_verify(self):
        self.assertEqual(self.validate(self.original),
                         {'run_id': 'run-001', 'rows': 240, 'allocation_rows': 96, 'paired_cells': 12})
        v.validate_journal(synthetic_journal(self.original), self.original)

    def test_both_phase_grids_reject_missing_duplicate_extra_or_reordered_rows(self):
        for field in ['rows', 'allocation_rows']:
            rows = self.original[field]
            for changed in [rows[:-1], rows + [rows[0]], rows[1:] + rows[:1],
                            [rows[0]] + rows[:-1]]:
                record = copy.deepcopy(self.original)
                record[field] = changed
                with self.subTest(field=field, count=len(changed)), self.assertRaises(ValueError):
                    self.validate(record)

    def test_pair_metadata_cannot_relabel_ab_as_ba(self):
        for field, value in [('variant', 'candidate'), ('position', True), ('pair_order', 'BA'),
                             ('order', False), ('block', False), ('pair', 1)]:
            for phase in ['rows', 'allocation_rows']:
                record = copy.deepcopy(self.original)
                record[phase][0][field] = value if value != record[phase][0][field] else 'invalid'
                with self.subTest(field=field, phase=phase), self.assertRaises(ValueError):
                    self.validate(record)

    def test_rejects_timing_aliases_nonfinite_and_wrong_per_operation_values(self):
        for field, value in [('iterations', True), ('wall_ns', True), ('wall_ns', 0), ('wall_ns', -1),
                             ('cpu_ns', 0), ('wall_ns_per_op', 20), ('wall_ns_per_op', float('nan')),
                             ('cpu_ns_per_op', float('inf')), ('wall_ns_per_op', 123.0)]:
            record = copy.deepcopy(self.original)
            record['rows'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.validate(record)

    def test_rejects_allocation_aliases_inconsistent_counters_or_wrong_deltas(self):
        for field, value in [('iterations', True), ('iterations', 2), ('before_bytes', True),
                             ('current_bytes', -1), ('peak_bytes', 1), ('retained_bytes', 123),
                             ('peak_increment_bytes', 123), ('peak_bytes', float('inf'))]:
            record = copy.deepcopy(self.original)
            record['allocation_rows'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.validate(record)

    def test_rejects_modified_metadata_summaries_hashes_or_config(self):
        mutations = [lambda r: r.update(schema=True), lambda r: r.update(status='failed'),
                     lambda r: r.update(run_id='run-003'), lambda r: r.update(scope='mesh throughput'),
                     lambda r: r.update(process_instance='not-uuid'), lambda r: r.update(extra=True),
                     lambda r: r['config'].update(iterations=51),
                     lambda r: r['config'].update(allocation_blocks=True),
                     lambda r: r['sources'].update({'candidate_codec.py': '0' * 64}),
                     lambda r: r.update(freeze_sha256='0' * 64),
                     lambda r: r['inputs']['audit_reply'].update(payload_bytes=1),
                     lambda r: r['environment'].update(candidate_native_fp32_le=False),
                     lambda r: r['environment'].update(hostname='unplanned'),
                     lambda r: r['summaries'][0]['wall_ns_per_op'].update(median=1.0),
                     lambda r: r['paired_summaries'][0]['wall_ratio'].update(median=2.0),
                     lambda r: r['allocation_summaries'][0]['retained_bytes'].update(min=True),
                     lambda r: r['allocation_paired_summaries'][0]['peak_delta_bytes'].update(max=0.0)]
        for mutate in mutations:
            record = copy.deepcopy(self.original)
            mutate(record)
            with self.assertRaises(ValueError):
                self.validate(record)

    def test_rejects_inconsistent_or_unbounded_run_duration(self):
        for value in [True, 0.0, -1.0, float('nan'), float('inf'), 180.0, 1e-10]:
            record = copy.deepcopy(self.original)
            record['elapsed_monotonic_seconds'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(record)
        record = copy.deepcopy(self.original)
        record['finished_at_utc'] = '2026-10-25T06:59:59+00:00'
        with self.assertRaises(ValueError):
            self.validate(record)
        record = copy.deepcopy(self.original)
        record['rows'][0].update(wall_ns=181_000_000_000, wall_ns_per_op=181_000_000_000 / 50)
        with self.assertRaises(ValueError):
            self.validate(record)

    def test_each_timer_budget_rejects_equality_before_summary_recomputation(self):
        for metric in ['wall_ns', 'cpu_ns']:
            for duration in [180_000_000_000, 180_000_000_001]:
                record = copy.deepcopy(self.original)
                record['rows'][0][metric] = duration
                record['rows'][0][metric + '_per_op'] = duration / 50
                with self.subTest(metric=metric, duration=duration), \
                     self.assertRaisesRegex(ValueError, 'batch timer interval/budget'):
                    self.validate(record)

    def test_strict_json_duplicate_keys_nonfinite_constants_and_caps(self):
        for raw in ['{"a": 1, "a": 2}', '{"a": NaN}', '{"a": Infinity}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                v.parse_json(raw)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'large.json'
            path.write_text(' ' * (4 * 1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                v.read_json(path)

    def test_journal_rejects_partial_extra_mutated_or_phase_reordered_events(self):
        events = synthetic_journal(self.original)
        for changed in [events[:-1], events + [events[-1]], events[1:],
                        events[:1] + events[241:337] + events[1:241] + events[-1:]]:
            with self.assertRaises(ValueError):
                v.validate_journal(changed, self.original)
        changed = copy.deepcopy(events)
        changed[241]['row']['retained_bytes'] += 1
        with self.assertRaises(ValueError):
            v.validate_journal(changed, self.original)

    def test_run_set_requires_two_sequential_distinct_process_instances(self):
        first = self.original
        second = copy.deepcopy(first)
        second.update(run_id='run-002', process_instance='2' * 32,
                      started_at_utc='2026-10-25T07:00:02+00:00', finished_at_utc='2026-10-25T07:00:03+00:00')
        v.validate_run_set([first, second])
        for records in [[first], [second, first], [first, first], [first, second, second]]:
            with self.assertRaises(ValueError):
                v.validate_run_set(records)
        for change in [dict(process_instance='1' * 32), dict(started_at_utc='2026-10-25T07:00:00+00:00')]:
            altered = copy.deepcopy(second)
            altered.update(change)
            with self.assertRaises(ValueError):
                v.validate_run_set([first, altered])

    def test_full_fake_runner_passes_independent_verifier_with_nonuniform_samples(self):
        spec = importlib.util.spec_from_file_location('paired_integration_runner', ROOT / 'benchmark.py')
        runner = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = runner
        spec.loader.exec_module(runner)
        sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}
        def clock(base):
            total, calls = 0, 0
            def tick():
                nonlocal total, calls
                calls += 1
                total += base + calls % 19
                return total
            return tick
        budget = iter(i / 1000 for i in range(2000))
        allocations = 0
        def sampler(operation):
            nonlocal allocations
            allocations += 1
            current = 100 + (allocations % 9 - 4)
            peak = max(100, current) + allocations % 7
            return {'iterations': 1, 'before_bytes': 100, 'current_bytes': current,
                    'peak_bytes': peak, 'retained_bytes': current - 100,
                    'peak_increment_bytes': peak - 100}, operation()
        def fixed_operations(case, variant):
            # Runner accounting, not codec performance: immutable correct test returns.
            return {'finite_scan': lambda: True, 'frame_pack': lambda: case.wire,
                    'frame_decode': lambda: (len(case.wire), case.frames[variant])}
        events = []
        with patch.object(runner, 'load_freeze', return_value=({'sources': sources}, 'a' * 64)), \
             patch.object(runner, 'operations', side_effect=fixed_operations), \
             patch.object(runner.tracemalloc, 'start', side_effect=AssertionError('no empirical tracing')), \
             patch.object(runner, 'utc_now', side_effect=['2026-10-25T07:00:00+00:00',
                                                        '2026-10-25T07:00:01+00:00']):
            record = runner.run('run-001', events.append, clock(1000), clock(500),
                                lambda: next(budget), sampler)
        self.assertEqual(record['status'], 'complete')
        v.validate_record(record, sources, 'a' * 64)
        v.validate_journal(events, record)

    def test_on_disk_freeze_journal_and_all_baseline_files_are_checked(self):
        inventory = json.loads((ROOT / 'BASELINE_PRE_DATA.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            study = repo / 'studies' / 'finite-validation-optimization'
            study.mkdir(parents=True)
            for entry in inventory['files']:
                target = repo / entry['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT.parent.parent / entry['path']).read_bytes())
            for name in SOURCE_FILES:
                target = study / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            sources = {name: hashlib.sha256((study / name).read_bytes()).hexdigest() for name in SOURCE_FILES}
            freeze = {'schema': 1, 'baseline_commit': 'ce945115f7fcf8f4da559cc5026d8a0157b5fa7d',
                      'frozen_at_utc': '2026-10-25T06:00:00+00:00', 'sources': sources}
            freeze_path = study / 'PRE_DATA_SHA256.json'
            freeze_path.write_text(json.dumps(freeze))
            record = copy.deepcopy(self.original)
            record.update(sources=sources, freeze_sha256=hashlib.sha256(freeze_path.read_bytes()).hexdigest())
            output = repo / 'synthetic-only'
            output.mkdir()
            (output / 'result.json').write_text(json.dumps(record))
            (output / 'journal.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in synthetic_journal(record)))
            spec = importlib.util.spec_from_file_location('paired_freeze_runner', ROOT / 'benchmark.py')
            runner = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = runner
            spec.loader.exec_module(runner)
            with patch.object(v, 'ROOT', study), patch.object(runner, 'ROOT', study):
                self.assertEqual(v.verify(output)['allocation_rows'], 96)
                self.assertEqual(runner.load_freeze()[0], freeze)
                malformed = dict(freeze, schema=True)
                freeze_path.write_text(json.dumps(malformed))
                with self.assertRaises(ValueError):
                    runner.load_freeze()
                freeze_path.write_text(json.dumps(freeze))
                (repo / 'README.md').write_text('unrelated baseline mutation')
                with self.assertRaises(ValueError):
                    v.verify(output)
                with self.assertRaises(ValueError):
                    runner.load_freeze()
                (repo / 'README.md').write_bytes((ROOT.parent.parent / 'README.md').read_bytes())
                (study / 'candidate_codec.py').write_text('changed candidate')
                with self.assertRaises(ValueError):
                    v.verify(output)

    def test_independent_inclusive_quartiles_include_fractional_positions(self):
        self.assertEqual(v.describe([1000.0, 1.0, 100.0, 10.0]),
                         {'median': 55.0, 'min': 1.0, 'max': 1000.0, 'iqr': 317.25})
        self.assertEqual(v.describe([4.0, 2.0, 1.0, 0.5]),
                         {'median': 1.5, 'min': 0.5, 'max': 4.0, 'iqr': 1.625})


if __name__ == '__main__':
    unittest.main()
