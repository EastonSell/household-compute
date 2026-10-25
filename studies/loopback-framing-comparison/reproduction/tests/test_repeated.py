import multiprocessing
import threading
import unittest

from mesh.repeated import run_suite, summarize
from mesh.session import WorkerSession


class SessionTests(unittest.TestCase):
    def test_reuses_exact_worker_processes(self):
        with WorkerSession(opt_in=True) as session:
            pids = tuple(process.pid for process in session.processes)
            first = session.forward(width=8)
            second = session.forward(width=32)
            self.assertEqual(pids, tuple(process.pid for process in session.processes))
            self.assertEqual(first['status'], 'ok')
            self.assertEqual(second['status'], 'ok')
            self.assertEqual(len(first['output']), 8)
            self.assertEqual(len(second['output']), 32)
        self.assertTrue(session.cleanup['workers_cleaned_up'])
        self.assertEqual(session.cleanup['worker_exitcodes'], [0, 0])

    def test_timeout_invalidates_session_and_cleans_up(self):
        with WorkerSession(opt_in=True) as session:
            failed = session.forward(width=8, latency_ms=1000, timeout_seconds=.01)
            self.assertEqual(failed['status'], 'timeout')
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                session.forward(width=8)
        self.assertTrue(session.cleanup['workers_cleaned_up'])


class RepeatedTests(unittest.TestCase):
    def test_statistics_are_descriptive(self):
        stats = summarize([1, 2, 3, 4, 20])
        self.assertEqual(stats['count'], 5)
        self.assertEqual(stats['median'], 3)
        self.assertEqual(stats['minimum'], 1)
        self.assertEqual(stats['maximum'], 20)
        self.assertEqual(stats['mean'], 6)

    def test_suite_separates_warmup_and_retains_paired_samples(self):
        before = {p.pid for p in multiprocessing.active_children()}
        result = run_suite(opt_in=True, widths=[8, 16], links=[{'latency_ms': 0, 'bytes_per_second': None}], repeats=3, warmup=1)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['worker_processes_started'], 2)
        self.assertEqual(len(result['cases']), 2)
        for case in result['cases']:
            self.assertEqual(len(case['samples']), 3)
            self.assertEqual(case['warmup_runs_excluded'], 1)
            self.assertEqual(case['reference_seconds']['count'], 3)
            self.assertEqual([sample['order'] for sample in case['samples']], ['reference_first', 'split_first', 'reference_first'])
            self.assertTrue(all(sample['max_abs_error'] == 0 for sample in case['samples']))
            self.assertTrue(all(sample['split_seconds'] > 0 for sample in case['samples']))
        self.assertTrue(result['cleanup']['workers_cleaned_up'])
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    def test_cancelled_startup_cleans_workers(self):
        event = threading.Event()
        event.set()
        before = {p.pid for p in multiprocessing.active_children()}
        result = run_suite(opt_in=True, widths=[8], repeats=1, cancel_event=event)
        self.assertEqual(result['status'], 'cancelled')
        self.assertTrue(result['cleanup']['workers_cleaned_up'])
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    def test_requires_opt_in_and_bounded_repeats(self):
        for options in [{'opt_in': False}, {'opt_in': True, 'repeats': 0}, {'opt_in': True, 'repeats': 101}, {'opt_in': True, 'widths': []}]:
            with self.assertRaises(ValueError):
                run_suite(**options)


if __name__ == '__main__':
    unittest.main()
