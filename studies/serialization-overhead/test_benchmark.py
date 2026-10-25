"""Correctness tests use synthetic data and fake clocks, never host timings."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark as b


class FixtureTests(unittest.TestCase):
    def test_exact_sizes_values_and_round_trips(self):
        cases = b.build_cases()
        self.assertEqual(list(cases), ['activation_decode', 'activation_prefill_16',
                                      'activation_prefill_64', 'audit_reply'])
        for name, floats, payload, wire in [
            ('activation_decode', 576, 2304, 2368),
            ('activation_prefill_16', 9216, 36864, 36928),
            ('activation_prefill_64', 36864, 147456, 147520),
            ('audit_reply', 49152, 196612, 196676),
        ]:
            with self.subTest(name=name):
                c = cases[name]
                self.assertEqual(len(c.tensor) // 4, floats)
                self.assertEqual(len(c.frame.payload), payload)
                self.assertEqual(len(c.wire), wire)
                self.assertEqual(c.tensor[:12], b'\x00\x00\x80\xbf\x00\x00\x7e\xbf\x00\x00\x7c\xbf')
                for operation, function in b.operations(c).items():
                    b.check_result(c, operation, function())

    def test_wrong_operation_result_cannot_pass_untimed_validation(self):
        c = b.build_cases()['activation_decode']
        for name in b.OPERATIONS:
            with self.subTest(operation=name):
                with self.assertRaises(ValueError):
                    b.check_result(c, name, object())

    def test_payload_copy_is_fresh_not_bytes_identity(self):
        c = b.build_cases()['activation_decode']
        copied = b.operations(c)['payload_copy']()
        self.assertEqual(copied, c.frame.payload)
        self.assertIsNot(copied, c.frame.payload)


class AccountingTests(unittest.TestCase):
    def test_batch_keeps_wall_and_cpu_distinct_and_last_value(self):
        calls = []
        def operation():
            calls.append(len(calls))
            return calls[-1]
        wall = iter([100, 700])
        cpu = iter([200, 500])
        measured, last = b.measure_batch(operation, 3, lambda: next(wall), lambda: next(cpu))
        self.assertEqual(measured, {'iterations': 3, 'wall_ns': 600, 'cpu_ns': 300,
                                    'wall_ns_per_op': 200.0, 'cpu_ns_per_op': 100.0})
        self.assertEqual(last, 2)
        self.assertEqual(calls, [0, 1, 2])

    def test_bad_iteration_counts_fail_before_operation(self):
        for n in [0, -1, True, 1.5, 10001]:
            with self.subTest(n=n), self.assertRaises(ValueError):
                b.measure_batch(lambda: self.fail('must not execute'), n)

    def test_zero_or_reversing_timers_rejected(self):
        for values in [(1, 1), (2, 1)]:
            clock = iter(values)
            with self.assertRaises(ValueError):
                b.measure_batch(lambda: None, 1, lambda: next(clock), lambda: 1)

    def test_schedule_is_reproducible_complete_and_not_fixed_order(self):
        schedule = b.make_schedule()
        self.assertEqual(schedule, b.make_schedule())
        self.assertEqual(len(schedule), 216)
        cells = {(c, o) for c in b.CASE_NAMES for o in b.OPERATIONS}
        blocks = []
        for block in range(9):
            rows = [r for r in schedule if r['block'] == block]
            self.assertEqual(len(rows), 24)
            self.assertEqual({(r['case'], r['operation']) for r in rows}, cells)
            self.assertEqual([r['order'] for r in rows], list(range(24)))
            blocks.append([(r['case'], r['operation']) for r in rows])
        self.assertNotEqual(blocks[0], blocks[1])

    def test_summary_uses_batches_not_pooled_iterations(self):
        rows = [{'case': 'x', 'operation': 'y', 'wall_ns_per_op': n,
                 'cpu_ns_per_op': n / 2} for n in [1, 2, 3, 4, 5, 6, 7, 8, 90]]
        s = b.summarize(rows)[0]
        self.assertEqual(s['batches'], 9)
        self.assertEqual(s['wall_ns_per_op'], {'median': 5, 'min': 1, 'max': 90, 'iqr': 4.0})
        self.assertEqual(s['cpu_ns_per_op']['median'], 2.5)


class IntegrityTests(unittest.TestCase):
    def test_exclusive_output_never_replaces_old_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'run.json'
            b.write_exclusive(target, {'status': 'complete'})
            with self.assertRaises(FileExistsError):
                b.write_exclusive(target, {'status': 'replacement'})
            self.assertEqual(json.loads(target.read_text()), {'status': 'complete'})

    def test_nonfinite_json_output_is_rejected_before_creating_file(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'run.json'
            with self.assertRaises(ValueError):
                b.write_exclusive(target, {'bad': float('nan')})
            self.assertFalse(target.exists())

    def test_freeze_rejects_missing_malformed_or_changed_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'test.txt'
            source.write_text('frozen')
            expected = {'test.txt': b.sha256(source.read_bytes())}
            b.check_hashes(root, expected)
            source.write_text('changed')
            with self.assertRaises(ValueError):
                b.check_hashes(root, expected)
            source.unlink()
            with self.assertRaises(ValueError):
                b.check_hashes(root, expected)


class RunnerTests(unittest.TestCase):
    def test_fixture_setup_failure_retains_explicit_terminal_failure(self):
        events = []
        with patch.object(b, 'load_freeze', return_value=({'sources': {}}, 'a' * 64)), \
             patch.object(b, 'build_cases', side_effect=ValueError('synthetic fixture failure')):
            result = b.run('run-001', events.append, lambda: self.fail('must not time'),
                           lambda: self.fail('must not time'), lambda: 0)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure_type'], 'ValueError')
        self.assertEqual(result['failure_phase'], 'setup')
        self.assertEqual(result['rows'], [])
        self.assertEqual(events[-1]['status'], 'failed')
        self.assertEqual(events[-1]['failure_type'], 'ValueError')

    def test_fake_clock_run_retains_complete_grid_and_terminal_journal(self):
        events = []
        wall = iter(range(0, 100000, 1000))
        cpu = iter(range(0, 100000, 500))
        # The smaller test grid exercises runner accounting, not empirical collection.
        with patch.object(b, 'CONFIG', {'blocks': 2, 'iterations': 1, 'warmup': 1, 'seed': 20261025}), \
             patch.object(b, 'load_freeze', return_value=({'sources': {}}, 'a' * 64)):
            result = b.run('run-001', events.append, lambda: next(wall), lambda: next(cpu), lambda: 0)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['elapsed_monotonic_seconds'], 0.0)
        self.assertEqual(len(result['rows']), 48)
        self.assertEqual(len(result['summaries']), 24)
        self.assertEqual([row['wall_ns'] for row in result['rows']], [1000] * 48)
        self.assertEqual([row['cpu_ns'] for row in result['rows']], [500] * 48)
        self.assertEqual(events[-1]['status'], 'complete')
        self.assertEqual(events[-1]['rows'], 48)
        self.assertEqual([event['row'] for event in events if event['event'] == 'row'], result['rows'])

    def test_timer_failure_retains_prior_row_and_does_not_retry(self):
        events = []
        wall = iter([0, 1000, 2000, 2000])
        cpu = iter([0, 500, 1000, 1500])
        with patch.object(b, 'CONFIG', {'blocks': 2, 'iterations': 1, 'warmup': 1, 'seed': 20261025}), \
             patch.object(b, 'load_freeze', return_value=({'sources': {}}, 'a' * 64)):
            result = b.run('run-001', events.append, lambda: next(wall), lambda: next(cpu), lambda: 0)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure_type'], 'ValueError')
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(events[-1]['status'], 'failed')
        self.assertEqual(events[-1]['rows'], 1)

    def test_time_budget_failure_is_recorded_not_complete(self):
        budget = iter([0, 180, 180])
        with patch.object(b, 'load_freeze', return_value=({'sources': {}}, 'a' * 64)):
            result = b.run('run-001', wall_clock=lambda: self.fail('must not time'),
                           cpu_clock=lambda: self.fail('must not time'), budget_clock=lambda: next(budget))
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure_type'], 'TimeoutError')
        self.assertEqual(result['rows'], [])

    def test_output_budget_rejection_leaves_no_partial_result(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(b, 'MAX_OUTPUT_BYTES', 8):
            target = Path(temp) / 'result.json'
            with self.assertRaises(ValueError):
                b.write_exclusive(target, {'too_large': True})
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
