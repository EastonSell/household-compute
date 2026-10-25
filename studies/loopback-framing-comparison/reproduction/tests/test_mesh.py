import json
import math
import subprocess
import sys
import unittest

from mesh.model import simulate
from mesh.benchmark import benchmark


class PlacementTests(unittest.TestCase):
    def scenario(self):
        return {
            'devices': [
                {'id': 'a', 'consent': True, 'memory_bytes': 1000, 'ops_per_second': 100},
                {'id': 'b', 'consent': True, 'memory_bytes': 1000, 'ops_per_second': 200},
            ],
            'links': [{'source': 'a', 'target': 'b', 'bytes_per_second': 100, 'latency_ms': 5}],
            'stages': [
                {'id': 's1', 'operations': 100, 'weights_bytes': 200, 'workspace_bytes': 100, 'output_bytes': 50},
                {'id': 's2', 'operations': 200, 'weights_bytes': 200, 'workspace_bytes': 100, 'output_bytes': 10},
            ],
        }

    def test_compute_and_transfer_units(self):
        result = simulate(self.scenario(), ['a', 'b'])
        self.assertEqual(result['kind'], 'analytical_estimate')
        self.assertAlmostEqual(result['compute_seconds'], 2)
        self.assertAlmostEqual(result['transfer_seconds'], .505)
        self.assertAlmostEqual(result['total_seconds'], 2.505)

    def test_colocated_stages_have_no_transfer(self):
        result = simulate(self.scenario(), ['b', 'b'])
        self.assertEqual(result['transfer_seconds'], 0)
        self.assertEqual(result['total_seconds'], 1.5)

    def test_consent_is_required_not_truthy(self):
        for consent in [False, 'true', 1, None]:
            scenario = self.scenario()
            scenario['devices'][0]['consent'] = consent
            with self.assertRaisesRegex(ValueError, 'consent'):
                simulate(scenario, ['a', 'b'])

    def test_resident_weights_are_summed(self):
        scenario = self.scenario()
        scenario['devices'][0]['memory_bytes'] = 499
        with self.assertRaisesRegex(ValueError, 'memory'):
            simulate(scenario, ['a', 'a'])

    def test_activation_memory_is_included(self):
        scenario = self.scenario()
        scenario['devices'][0]['memory_bytes'] = 500
        with self.assertRaisesRegex(ValueError, 'memory'):
            simulate(scenario, ['a', 'a'])

    def test_link_is_directed(self):
        with self.assertRaisesRegex(ValueError, 'link'):
            simulate(self.scenario(), ['b', 'a'])

    def test_invalid_numbers_rejected(self):
        for number in [0, -1, math.inf, math.nan, True]:
            scenario = self.scenario()
            scenario['devices'][0]['ops_per_second'] = number
            with self.assertRaises(ValueError):
                simulate(scenario, ['a', 'b'])

    def test_duplicate_ids_rejected(self):
        scenario = self.scenario()
        scenario['devices'][1]['id'] = 'a'
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            simulate(scenario, ['a', 'a'])

    def test_wrong_placement_length_rejected(self):
        with self.assertRaisesRegex(ValueError, 'placement'):
            simulate(self.scenario(), ['a'])

    def test_missing_consent_fails_closed(self):
        scenario = self.scenario()
        del scenario['devices'][0]['consent']
        with self.assertRaisesRegex(ValueError, 'consent'):
            simulate(scenario, ['a', 'b'])


class BenchmarkTests(unittest.TestCase):
    def test_real_benchmark_is_separate_from_simulation(self):
        result = benchmark(size=8, iterations=3, repeats=2)
        self.assertEqual(result['kind'], 'local_cpu_measurement')
        self.assertEqual(len(result['samples_seconds']), 2)
        self.assertTrue(all(x > 0 for x in result['samples_seconds']))
        self.assertTrue(math.isfinite(result['checksum']))
        self.assertEqual(result['operations_per_sample'], 2 * 8 * 8 * 3)
        self.assertGreater(result['median_ops_per_second'], 0)

    def test_invalid_benchmark_size(self):
        for size in [0, -1, True, 2.5]:
            with self.assertRaises(ValueError):
                benchmark(size=size)


class CliTests(unittest.TestCase):
    def test_simulate_cli_separates_rejections(self):
        run = subprocess.run([sys.executable, '-m', 'mesh', 'simulate', 'examples/illustrative.json'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        data = json.loads(run.stdout)
        self.assertEqual(data['kind'], 'analytical_comparison')
        self.assertEqual(len(data['feasible']), 2)
        self.assertEqual(len(data['rejected']), 2)
        self.assertEqual(data['feasible'][0]['name'], 'laptop_only')

    def test_benchmark_cli(self):
        run = subprocess.run([sys.executable, '-m', 'mesh', 'benchmark', '--size', '8', '--iterations', '2', '--repeats', '2'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['kind'], 'local_cpu_measurement')


if __name__ == '__main__':
    unittest.main()
