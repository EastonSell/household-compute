"""Deterministic engineering tests: fake clocks and allocation samples only."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if (ROOT / 'benchmark.py').exists():
    spec = importlib.util.spec_from_file_location('finite_validation_benchmark', ROOT / 'benchmark.py')
    b = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = b
    spec.loader.exec_module(b)
else:
    b = None


class FakeTracer:
    def __init__(self, readings=((100, 100), (180, 500))):
        self.readings = iter(readings)
        self.active = False
        self.events = []
    def is_tracing(self):
        return self.active
    def start(self, frames):
        self.events.append(('start', frames))
        self.active = True
    def get_traced_memory(self):
        self.events.append('read')
        return next(self.readings)
    def reset_peak(self):
        self.events.append('reset')
    def stop(self):
        self.events.append('stop')
        self.active = False


def fake_allocator(operation):
    result = operation()
    return {'iterations': 1, 'before_bytes': 100, 'current_bytes': 180,
            'peak_bytes': 500, 'retained_bytes': 80, 'peak_increment_bytes': 400}, result


def counter(step=1000):
    value = -step
    def tick():
        nonlocal value
        value += step
        return value
    return tick


class Ready(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(b, 'paired benchmark has not been implemented')


class FixtureTests(Ready):
    def test_identical_payloads_and_wires_for_independent_codec_modules(self):
        cases = b.build_cases()
        self.assertEqual(list(cases), ['activation_decode', 'activation_prefill_16',
                                      'activation_prefill_64', 'audit_reply'])
        self.assertIsNot(b.BASELINE, b.CANDIDATE)
        self.assertIsNot(b.BASELINE.Frame, b.CANDIDATE.Frame)
        self.assertFalse(hasattr(b.BASELINE, 'finite_scan'))
        for name, count, size, wire in [
            ('activation_decode', 576, 2304, 2368),
            ('activation_prefill_16', 9216, 36864, 36928),
            ('activation_prefill_64', 36864, 147456, 147520),
            ('audit_reply', 49152, 196612, 196676),
        ]:
            with self.subTest(name=name):
                case = cases[name]
                self.assertEqual(len(case.tensor), count * 4)
                self.assertEqual(len(case.payload), size)
                self.assertEqual(len(case.wire), wire)
                self.assertEqual(case.tensor[:12], b'\x00\x00\x80\xbf\x00\x00\x7e\xbf\x00\x00\x7c\xbf')
                for variant in ('baseline', 'candidate'):
                    self.assertIs(case.frames[variant].payload, case.payload)
                    for operation, function in b.operations(case, variant).items():
                        b.check_result(case, variant, operation, function())

    def test_wrong_result_and_cross_variant_frame_are_rejected(self):
        case = b.build_cases()['activation_decode']
        for variant in ('baseline', 'candidate'):
            for operation in ('finite_scan', 'frame_pack', 'frame_decode'):
                with self.subTest(variant=variant, operation=operation), self.assertRaises(ValueError):
                    b.check_result(case, variant, operation, object())
        with self.assertRaises(ValueError):
            b.check_result(case, 'candidate', 'frame_decode',
                           (len(case.wire), case.frames['baseline']))


class AccountingTests(Ready):
    def test_adjacent_pairs_are_complete_reproducible_and_balanced(self):
        for phase, blocks in [('latency', 10), ('allocation', 4)]:
            schedule = b.make_schedule(phase)
            self.assertEqual(schedule, b.make_schedule(phase))
            self.assertEqual(len(schedule), blocks * 24)
            orders = {}
            for index in range(0, len(schedule), 2):
                first, second = schedule[index:index + 2]
                for field in ('block', 'pair', 'case', 'operation', 'pair_order'):
                    self.assertEqual(first[field], second[field])
                self.assertEqual([first['position'], second['position']], [0, 1])
                self.assertEqual([first['order'], second['order']],
                                 [first['pair'] * 2, first['pair'] * 2 + 1])
                self.assertEqual({first['variant'], second['variant']}, {'baseline', 'candidate'})
                key = (first['case'], first['operation'])
                orders.setdefault(key, []).append(first['pair_order'])
            self.assertEqual(len(orders), 12)
            for sequences in orders.values():
                self.assertEqual(sequences.count('AB'), blocks // 2)
                self.assertEqual(sequences.count('BA'), blocks // 2)
            for block in range(blocks):
                rows = [r for r in schedule if r['block'] == block]
                self.assertEqual([r['order'] for r in rows], list(range(24)))
        with self.assertRaises(ValueError):
            b.make_schedule('unknown')

    def test_batch_preserves_last_result_and_distinct_timers(self):
        values = iter(['first', 'middle', 'last'])
        wall, cpu = iter([100, 700]), iter([200, 500])
        measured, last = b.measure_batch(lambda: next(values), 3,
                                        lambda: next(wall), lambda: next(cpu))
        self.assertEqual(last, 'last')
        self.assertEqual(measured, {'iterations': 3, 'wall_ns': 600, 'cpu_ns': 300,
                                    'wall_ns_per_op': 200.0, 'cpu_ns_per_op': 100.0})

    def test_batch_refuses_invalid_iterations_and_active_tracing(self):
        for n in [0, -1, True, 1.5, 10001]:
            with self.subTest(n=n), self.assertRaises(ValueError):
                b.measure_batch(lambda: self.fail('must not execute'), n)
        with patch.object(b.tracemalloc, 'is_tracing', return_value=True), self.assertRaises(ValueError):
            b.measure_batch(lambda: self.fail('must not time traced work'), 1)

    def test_nonpositive_timers_are_not_retried(self):
        for readings in [(1, 1), (2, 1), (0, True)]:
            wall = iter(readings)
            with self.subTest(readings=readings), self.assertRaises(ValueError):
                b.measure_batch(lambda: None, 1, lambda: next(wall), counter(100))

    def test_each_batch_timer_must_be_strictly_below_the_run_budget(self):
        for wall_ns, cpu_ns in [(180_000_000_000, 500), (180_000_000_001, 500),
                               (1000, 180_000_000_000), (1000, 180_000_000_001)]:
            wall, cpu = iter([0, wall_ns]), iter([0, cpu_ns])
            with self.subTest(wall_ns=wall_ns, cpu_ns=cpu_ns), self.assertRaises(ValueError):
                b.measure_batch(lambda: True, 1, lambda: next(wall), lambda: next(cpu))
        wall, cpu = iter([0, 179_999_999_999]), iter([0, 179_999_999_999])
        measured, _ = b.measure_batch(lambda: True, 1, lambda: next(wall), lambda: next(cpu))
        self.assertEqual(measured['wall_ns'], 179_999_999_999)
        self.assertEqual(measured['cpu_ns'], 179_999_999_999)

    def test_allocation_peak_and_retained_are_deltas_not_churn(self):
        tracer = FakeTracer()
        result = object()
        measured, last = b.measure_allocation(lambda: result, tracer)
        self.assertIs(last, result)
        self.assertEqual(measured, {'iterations': 1, 'before_bytes': 100, 'current_bytes': 180,
                                   'peak_bytes': 500, 'retained_bytes': 80, 'peak_increment_bytes': 400})
        self.assertEqual(tracer.events, [('start', 1), 'read', 'reset', 'read', 'stop'])
        self.assertFalse(tracer.active)

    def test_allocation_signed_retention_and_zero_peak_are_retained(self):
        measured, _ = b.measure_allocation(lambda: True, FakeTracer(((100, 100), (80, 90))))
        self.assertEqual(measured['retained_bytes'], -20)
        self.assertEqual(measured['peak_increment_bytes'], 0)

    def test_allocation_stops_on_operation_error_without_stopping_preexisting_trace(self):
        tracer = FakeTracer()
        def broken():
            raise RuntimeError('synthetic')
        with self.assertRaises(RuntimeError):
            b.measure_allocation(broken, tracer)
        self.assertEqual(tracer.events[-1], 'stop')
        self.assertFalse(tracer.active)
        tracer.active = True
        tracer.events.clear()
        with self.assertRaises(ValueError):
            b.measure_allocation(lambda: self.fail('must not execute'), tracer)
        self.assertTrue(tracer.active)
        self.assertEqual(tracer.events, [])

    def test_allocation_rejects_invalid_raw_counters(self):
        for readings in [((True, 100), (180, 500)), ((100, 100), (501, 500)),
                         ((100, 100), (-1, 500))]:
            tracer = FakeTracer(readings)
            with self.subTest(readings=readings), self.assertRaises(ValueError):
                b.measure_allocation(lambda: True, tracer)
            self.assertFalse(tracer.active)

    def test_summary_uses_paired_observations_not_ratio_of_medians(self):
        rows = []
        for block, a, c in [(0, 1.0, 4.0), (1, 10.0, 20.0), (2, 100.0, 100.0), (3, 1000.0, 500.0)]:
            for variant, n in [('baseline', a), ('candidate', c)]:
                rows.append({'case': 'x', 'operation': 'y', 'block': block, 'variant': variant,
                             'wall_ns_per_op': n, 'cpu_ns_per_op': n / 2})
        summaries, paired = b.summarize_latency(rows)
        self.assertEqual(summaries[0]['samples'], 4)
        self.assertEqual(summaries[0]['wall_ns_per_op'],
                         {'median': 55.0, 'min': 1.0, 'max': 1000.0, 'iqr': 317.25})
        self.assertEqual(paired[0]['wall_ratio'],
                         {'median': 1.5, 'min': 0.5, 'max': 4.0, 'iqr': 1.625})
        self.assertEqual(paired[0]['pairs'], 4)
        self.assertEqual(paired[0]['wall_delta_ns']['median'], 1.5)


class IntegrityTests(Ready):
    def test_exclusive_output_never_replaces_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'result.json'
            b.write_exclusive(path, {'kept': True})
            with self.assertRaises(FileExistsError):
                b.write_exclusive(path, {'kept': False})
            self.assertEqual(json.loads(path.read_text()), {'kept': True})

    def test_oversize_and_nonfinite_output_create_no_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'result.json'
            for value in [float('nan'), float('inf')]:
                with self.assertRaises(ValueError):
                    b.write_exclusive(path, {'bad': value})
                self.assertFalse(path.exists())
            with patch.object(b, 'MAX_OUTPUT_BYTES', 8), self.assertRaises(ValueError):
                b.write_exclusive(path, {'too_large': True})
            self.assertFalse(path.exists())

    def test_hash_gate_rejects_changed_and_missing_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source.py'
            source.write_bytes(b'frozen')
            hashes = {'source.py': b.sha256(b'frozen')}
            b.check_hashes(root, hashes)
            source.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                b.check_hashes(root, hashes)
            source.unlink()
            with self.assertRaises(ValueError):
                b.check_hashes(root, hashes)

    def test_baseline_inventory_checks_every_preserved_file_and_git_blob(self):
        self.assertTrue(hasattr(b, 'check_baseline_inventory'), 'baseline preservation gate missing')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'studies' / 'new'
            root.mkdir(parents=True)
            files = []
            for index in range(62):
                name = 'file-%02d.txt' % index
                content = ('preserved-%d' % index).encode()
                (root.parent.parent / name).write_bytes(content)
                blob = b'blob ' + str(len(content)).encode() + b'\0' + content
                files.append({'path': name, 'sha256': b.sha256(content),
                              'git_blob_sha1': b.hashlib.sha1(blob).hexdigest()})
            inventory = {'schema': 1, 'published_baseline_commit': b.BASELINE_COMMIT,
                         'local_base_commit': 'e5430bd062c3a9e074ef712579e62dbf11aa1249',
                         'scope': 'synthetic inventory', 'checked_at_utc': '2026-10-25T00:00:00+00:00',
                         'files': files}
            (root / 'BASELINE_PRE_DATA.json').write_text(json.dumps(inventory))
            b.check_baseline_inventory(root)
            (root.parent.parent / 'file-61.txt').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                b.check_baseline_inventory(root)
            files[0]['path'] = '../outside'
            (root / 'BASELINE_PRE_DATA.json').write_text(json.dumps(inventory))
            with self.assertRaises(ValueError):
                b.check_baseline_inventory(root)

    def test_journal_reserves_failure_space_and_keeps_prior_events(self):
        stream = io.StringIO()
        journal = b.Journal(stream, limit=4200)
        journal.emit({'event': 'start', 'metadata': {}})
        with self.assertRaises(ValueError):
            journal.emit({'event': 'row', 'row': {'too_large': 'x' * 200}})
        journal.emit({'event': 'finish', 'status': 'failed'})
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([e['event'] for e in events], ['start', 'finish'])


class RunnerTests(Ready):
    def run_fake(self, **overrides):
        options = {'wall_clock': counter(1000), 'cpu_clock': counter(500),
                   'budget_clock': counter(0.001), 'allocation_sampler': fake_allocator}
        options.update(overrides)
        config = dict(b.CONFIG, blocks=2, iterations=1, warmup=1, allocation_blocks=2)
        with patch.object(b, 'CONFIG', config), \
             patch.object(b, 'load_freeze', return_value=({'sources': {}}, 'a' * 64)), \
             patch.object(b, 'utc_now', side_effect=['2026-10-25T07:00:00+00:00',
                                                   '2026-10-25T07:00:01+00:00']):
            return b.run('run-001', **options)

    def test_complete_fake_run_retains_latency_then_allocation_grid(self):
        events = []
        with patch.object(b.tracemalloc, 'start', side_effect=AssertionError('no empirical allocation')):
            record = self.run_fake(emit=events.append)
        self.assertEqual(record['status'], 'complete')
        self.assertEqual(len(record['rows']), 48)
        self.assertEqual(len(record['allocation_rows']), 48)
        self.assertEqual(len(record['summaries']), 24)
        self.assertEqual(len(record['paired_summaries']), 12)
        self.assertEqual(len(record['allocation_summaries']), 24)
        self.assertEqual(len(record['allocation_paired_summaries']), 12)
        self.assertEqual([r['wall_ns'] for r in record['rows']], [1000] * 48)
        self.assertEqual([e['event'] for e in events], ['start'] + ['row'] * 48 + ['allocation_row'] * 48 + ['finish'])
        self.assertEqual(events[-1]['allocation_rows'], 48)
        self.assertGreater(record['elapsed_monotonic_seconds'], 0)

    def test_setup_and_timer_failures_are_retained_without_retry(self):
        with patch.object(b, 'build_cases', side_effect=ValueError('synthetic')):
            record = self.run_fake(wall_clock=lambda: self.fail('must not time'))
        self.assertEqual(record['failure_phase'], 'setup')
        self.assertEqual(record['rows'], [])
        wall = iter([0, 1000, 2000, 2000])
        record = self.run_fake(wall_clock=lambda: next(wall))
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['failure_phase'], 'latency')
        self.assertEqual(len(record['rows']), 1)
        self.assertEqual(record['allocation_rows'], [])

    def test_allocation_failure_retains_latency_and_prior_allocation_row(self):
        calls = 0
        def failing_allocator(operation):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('synthetic allocation error')
            return fake_allocator(operation)
        record = self.run_fake(allocation_sampler=failing_allocator)
        self.assertEqual(record['failure_phase'], 'allocation')
        self.assertEqual(record['failure_type'], 'RuntimeError')
        self.assertEqual(len(record['rows']), 48)
        self.assertEqual(len(record['allocation_rows']), 1)

    def test_budget_regression_zero_duration_and_expiration_are_failures(self):
        for clock in [lambda: 0.0, counter(-0.01), counter(180.0)]:
            record = self.run_fake(budget_clock=clock)
            self.assertEqual(record['status'], 'failed')

    def test_invalid_run_id_never_starts_collection(self):
        with self.assertRaises(ValueError):
            b.run('run-003', wall_clock=lambda: self.fail('must not time'))


if __name__ == '__main__':
    unittest.main()
