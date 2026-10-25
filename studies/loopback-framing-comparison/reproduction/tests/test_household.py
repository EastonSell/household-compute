import math
import unittest

from mesh.household import memory_estimate, kv_cache_bytes, communication_floor


class HouseholdTests(unittest.TestCase):
    def test_memory_floor_uses_binary_gib_and_ceiling(self):
        result = memory_estimate(parameters=70_000_000_000, weight_bits=4, household_available_gib=12)
        self.assertEqual(result['weight_bytes'], 35_000_000_000)
        self.assertEqual(result['weight_only_households'], 3)
        self.assertEqual(result['adjusted_households'], 3)
        self.assertEqual(result['consent_premise'], 'all_participating_devices_fully_informed_and_consented')
        self.assertFalse(result['establishes_inference_feasibility'])

    def test_adjusted_model_separates_assumed_overhead(self):
        result = memory_estimate(parameters=8_000_000_000, weight_bits=4, household_available_gib=4,
                                 weight_overhead_fraction=.2, kv_bytes=2**30, runtime_reserve_bytes=2**30)
        self.assertEqual(result['weight_only_households'], 1)
        self.assertEqual(result['adjusted_households'], 2)
        self.assertEqual(result['adjusted_model_bytes'], 4_800_000_000 + 2**31)

    def test_kv_accounts_for_keys_values_heads_layers_context_and_batch(self):
        self.assertEqual(kv_cache_bytes(layers=32, kv_heads=8, head_dim=128, context_tokens=8192, element_bits=16), 2**30)
        self.assertEqual(kv_cache_bytes(layers=32, kv_heads=8, head_dim=128, context_tokens=8192, element_bits=16, batch=2), 2**31)

    def test_serial_pipeline_communication_floor_units(self):
        result = communication_floor(households=4, hidden_size=8192, activation_bits=16, payload_mbps=10, one_way_ms=20, context_tokens=8192)
        self.assertAlmostEqual(result['decode_communication_seconds'], 3 * (.020 + 16384 / 1_250_000))
        self.assertAlmostEqual(result['decode_tokens_per_second_ceiling_from_communication_only'], 1 / result['decode_communication_seconds'])
        self.assertGreater(result['prefill_communication_seconds'], result['decode_communication_seconds'])
        self.assertEqual(result['interhousehold_boundaries'], 3)
        self.assertEqual(result['compute_time_included'], False)

    def test_one_household_has_no_interhousehold_boundary_not_infinite_speed(self):
        result = communication_floor(households=1, hidden_size=4096, activation_bits=16, payload_mbps=10, one_way_ms=20)
        self.assertEqual(result['decode_communication_seconds'], 0)
        self.assertIsNone(result['decode_tokens_per_second_ceiling_from_communication_only'])

    def test_invalid_numeric_inputs(self):
        for memory in [0, -1, True, math.inf, math.nan]:
            with self.assertRaises(ValueError):
                memory_estimate(parameters=8_000_000_000, weight_bits=4, household_available_gib=memory)
        for household_count in [0, -1, True, 1.5]:
            with self.assertRaises(ValueError):
                communication_floor(households=household_count, hidden_size=4096, activation_bits=16, payload_mbps=10, one_way_ms=20)
        with self.assertRaises(ValueError):
            kv_cache_bytes(layers=32, kv_heads=8, head_dim=128, context_tokens=0, element_bits=16)


class SourcedScenarioTests(unittest.TestCase):
    def test_sourced_grid_reproduces_known_capacity_rows(self):
        import json
        from mesh.household_report import ROOT, build_rows
        assumptions = json.loads((ROOT/'data/household/scaling_assumptions.json').read_text())
        rows=build_rows(assumptions)
        self.assertEqual(len(rows),27)
        selected=[row for row in rows if row['parameters_billion_rounded']==405 and row['household_available_gib_assumed']==12 and row['nominal_weight_bits']==4][0]
        self.assertEqual(selected['weight_only_household_lower_bound'],16)
        self.assertEqual(selected['illustrative_envelope_households'],20)
        self.assertFalse(selected['measured'])
        self.assertTrue(selected['assumed'])
        self.assertEqual(selected['inference_feasibility'],'not established')
        self.assertTrue(selected['sourceURL'].startswith('https://'))


    def test_baskets_are_explicit_allocations_and_unknown_devices_stay_unknown(self):
        import json
        from mesh.household_report import ROOT
        baskets=json.loads((ROOT/'data/household/household_baskets.json').read_text())
        for name in ['low','middle','high']:
            basket=baskets[name]
            self.assertEqual(sum(d['count']*d['assumed_usable_gib_each'] for d in basket['devices']),basket['available_gib'])
        atlas=json.loads((ROOT/'data/household/device_evidence.json').read_text())['devices']
        self.assertEqual(len(atlas),14)
        for device in atlas:
            self.assertIsNone(device['usable_ram_gb'])
            self.assertIsNone(device['measured_llm_tokens_per_second'])
        fridge=next(d for d in atlas if d['category']=='Smart refrigerator')
        self.assertIsNone(fridge['ram_min'])

    def test_report_table_matches_calculator_not_manual_rounding(self):
        import json
        from mesh.household_report import ROOT, build_rows
        rows=build_rows(json.loads((ROOT/'data/household/scaling_assumptions.json').read_text()))
        prose=(ROOT/'HOUSEHOLD_ATLAS.md').read_text()
        for model in [8,70,405]:
            selected=[r for r in rows if r['parameters_billion_rounded']==model and r['household_available_gib_assumed']==12]
            cells=[f"{r['weight_only_household_lower_bound']} / {r['illustrative_envelope_households']}" for r in selected]
            self.assertIn(f"| {model}B | "+' | '.join(cells)+' |',prose)


if __name__ == '__main__':
    unittest.main()
