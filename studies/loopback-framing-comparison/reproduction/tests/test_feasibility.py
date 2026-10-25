import importlib.util
from pathlib import Path
import tempfile
import unittest
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('feasibility', ROOT / 'calculations' / 'feasibility.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)

class FeasibilityTests(unittest.TestCase):
    def test_ideal_weight_units(self):
        self.assertEqual(f.weight_bytes(70_000_000_000, 4), 35_000_000_000)
        self.assertEqual(f.weight_bytes(70_000_000_000, 4.5), 39_375_000_000)
        self.assertEqual(f.weight_bytes(1, 4), Fraction(1, 2))

    def test_exact_ceiling(self):
        self.assertEqual(f.households(24 * f.GIB, 12 * f.GIB), 2)
        self.assertEqual(f.households(24 * f.GIB + 1, 12 * f.GIB), 3)

    def test_kv_architecture_and_scaling(self):
        self.assertEqual(f.kv_bytes(80, 8, 128, 8192, 1, 2), Fraction(5, 2) * f.GIB)
        self.assertEqual(f.kv_bytes(32, 8, 128, 8192, 1, 2), f.GIB)
        self.assertEqual(f.kv_bytes(126, 8, 128, 8192, 1, 2), Fraction(63, 16) * f.GIB)
        self.assertEqual(f.kv_bytes(80, 8, 128, 8192, 4, 2), 10 * f.GIB)

    def test_pipeline_hops_and_units(self):
        self.assertEqual(f.comm_seconds(1, 8192, 2, 20, 20), 0)
        self.assertAlmostEqual(f.comm_seconds(16, 8192, 2, 20, 20), .398304)
        self.assertAlmostEqual(f.comm_seconds(4, 8192, 2, 20, 20), .0796608)
        self.assertGreater(f.comm_seconds(16, 8192, 2, 20, 20), f.comm_seconds(4, 8192, 2, 20, 20))

    def test_bounded_adversarial_pipeline(self):
        self.assertAlmostEqual(f.serial_seconds([20, 20, 20, 20]), .08)
        self.assertAlmostEqual(f.serial_seconds([20, 20, 20, 100]), .16)
        self.assertEqual(f.pipeline_rate_ceiling([20, 20, 20, 100]), 10)

    def test_availability_is_conditional(self):
        self.assertAlmostEqual(f.chain_availability(.9, 4), .6561)
        self.assertAlmostEqual(f.chain_availability(.9, 4, 2), .99 ** 4)
        self.assertEqual(f.chain_availability(1, 64), 1)
        self.assertEqual(f.chain_availability(0, 4), 0)

    def test_invalid_inputs(self):
        for bad in [-1, 0, float('nan'), float('inf'), True]:
            with self.assertRaises(ValueError): f.weight_bytes(bad, 4)
        for args in [(0, 8192, 2, 20, 20), (4, 8192, 2, 0, 20), (4, 8192, 2, 20, -1)]:
            with self.assertRaises(ValueError): f.comm_seconds(*args)
        with self.assertRaises(ValueError): f.chain_availability(1.1, 4)
        with self.assertRaises(ValueError): f.households(1, 0)

    def test_table_coverage_and_legacy_consistency(self):
        rows = f.tables()
        self.assertEqual(len(rows['weight_floors']), 12)
        self.assertEqual(len(rows['memory_sensitivity']), 27)
        self.assertEqual(len(rows['communication']), 12)
        match = [r for r in rows['memory_sensitivity'] if r['parameters_billion'] == 70 and r['weight_bits'] == 4 and r['household_gib'] == 12][0]
        self.assertEqual((match['weight_only_households'], match['illustrative_envelope_households']), (3, 4))
        match = [r for r in rows['memory_sensitivity'] if r['parameters_billion'] == 405 and r['weight_bits'] == 4 and r['household_gib'] == 12][0]
        self.assertEqual((match['weight_only_households'], match['illustrative_envelope_households']), (16, 20))

    def test_reproduction_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            f.write_outputs(root)
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            f.write_outputs(root)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertIn('results/feasibility_tables.json', before)
            self.assertIn('figures/feasibility_memory.svg', before)
            self.assertIn('figures/feasibility_communication.svg', before)

if __name__ == '__main__': unittest.main()
