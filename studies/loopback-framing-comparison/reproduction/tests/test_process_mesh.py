"""Real private-pipe subprocess tests; no sockets or physical devices."""
import json
import multiprocessing
import subprocess
import sys
import threading
import unittest

from mesh.process_mesh import run_experiment


class ProcessMeshTests(unittest.TestCase):
    def run_mesh(self, **options):
        before = {process.pid for process in multiprocessing.active_children()}
        result = run_experiment(opt_in=True, width=8, **options)
        self.assertEqual({process.pid for process in multiprocessing.active_children()}, before)
        self.assertTrue(result['workers_cleaned_up'])
        self.assertEqual(len(result['worker_exitcodes']), 2)
        self.assertTrue(all(code is not None for code in result['worker_exitcodes']))
        return result

    def test_real_partitioned_forward_matches_reference(self):
        result = self.run_mesh()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['kind'], 'local_process_experiment')
        self.assertEqual(result['max_abs_error'], 0)
        self.assertEqual(result['worker_exitcodes'], [0, 0])
        self.assertFalse(any(result['worker_forced_termination']))
        self.assertEqual(len(result['worker_compute_seconds']), 2)
        self.assertTrue(all(value > 0 for value in result['worker_compute_seconds']))
        self.assertGreater(result['reference_seconds'], 0)
        self.assertEqual(result['emulated_wait_requested_seconds'], 0)

    def test_explicit_consent_required(self):
        for consent in (False, None, 1, 'true'):
            with self.assertRaisesRegex(ValueError, 'opt-in'):
                run_experiment(opt_in=consent, width=8)

    def test_bandwidth_and_latency_wait_match_transferred_payload(self):
        result = self.run_mesh(latency_ms=5, bytes_per_second=10000)
        self.assertEqual(result['status'], 'ok')
        self.assertAlmostEqual(result['emulated_wait_requested_seconds'], .005 + result['interstage_payload_bytes'] / 10000)
        self.assertGreaterEqual(result['emulated_wait_observed_seconds'], result['emulated_wait_requested_seconds'])
        self.assertGreaterEqual(result['inference_wall_seconds'], result['emulated_wait_observed_seconds'])
        self.assertEqual(result['max_abs_error'], 0)

    def test_disconnected_worker_is_reported_and_cleaned(self):
        result = self.run_mesh(fault='disconnect')
        self.assertEqual(result['status'], 'disconnected')

    def test_stalled_worker_times_out_and_is_cleaned(self):
        result = self.run_mesh(fault='stall', timeout_seconds=.1)
        self.assertEqual(result['status'], 'timeout')
        self.assertTrue(result['worker_forced_termination'][0])

    def test_cancellation_interrupts_emulated_wait(self):
        event = threading.Event()
        timer = threading.Timer(.5, event.set)
        timer.start()
        try:
            result = self.run_mesh(latency_ms=5000, cancel_event=event)
        finally:
            timer.cancel()
            timer.join()
        self.assertEqual(result['status'], 'cancelled')
        self.assertLess(result['inference_wall_seconds'], 2)

    def test_timeout_interrupts_emulated_wait(self):
        result = self.run_mesh(latency_ms=5000, timeout_seconds=.1)
        self.assertEqual(result['status'], 'timeout')
        self.assertLess(result['inference_wall_seconds'], 2)

    def test_invalid_parameters_are_rejected(self):
        for options in ({'width': 0}, {'width': True}, {'width': 257}, {'latency_ms': -1}, {'bytes_per_second': 0}, {'timeout_seconds': float('nan')}, {'fault': 'unknown'}):
            with self.assertRaises(ValueError):
                run_experiment(opt_in=True, **options)


class ProcessCliTests(unittest.TestCase):
    def test_cli_requires_opt_in(self):
        run = subprocess.run([sys.executable, '-m', 'mesh.process_cli'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn('opt-in', run.stderr)

    def test_cli_success(self):
        run = subprocess.run([sys.executable, '-m', 'mesh.process_cli', '--opt-in', '--width', '8'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'], 'ok')

    def test_cli_rejects_overflowing_delay_before_spawn(self):
        run = subprocess.run([sys.executable, '-m', 'mesh.process_cli', '--opt-in', '--width', '8', '--bytes-per-second', '5e-324', '--timeout-seconds', '.01'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn('derived emulated delay', run.stderr)
        self.assertNotIn('Traceback', run.stderr)
        self.assertEqual(run.stdout, '')

    def test_cli_fault_nonzero_and_cleanup(self):
        run = subprocess.run([sys.executable, '-m', 'mesh.process_cli', '--opt-in', '--fault', 'disconnect'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['status'], 'disconnected')
        self.assertTrue(result['workers_cleaned_up'])


if __name__ == '__main__':
    unittest.main()
