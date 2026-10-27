"""Offline CLI contracts; no timing or model experiments."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/compare_scenario.py'
EXAMPLE = ROOT / 'examples/illustrative.json'


class ComparisonTests(unittest.TestCase):
    def run_cli(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scenario.json'
            path.write_bytes(content)
            return subprocess.run([sys.executable, '-B', str(SCRIPT), str(path)],
                                  cwd=directory, capture_output=True, text=True)

    def check_bad(self, value, message):
        run = self.run_cli(json.dumps(value).encode())
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertEqual(run.stdout, '')
        self.assertNotIn('Traceback', run.stderr)
        self.assertIn(message, run.stderr)

    def test_preserves_existing_example_and_records_exact_input(self):
        content = EXAMPLE.read_bytes()
        run = self.run_cli(content)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        saved = json.loads((ROOT / 'results/illustrative_simulation.json').read_text())
        for field in ('kind', 'feasible', 'rejected'):
            self.assertEqual(result[field], saved[field])
        self.assertEqual(result['scenario_sha256'], hashlib.sha256(content).hexdigest())
        self.assertEqual(result['evidence_kind'], 'assumption_conditional_not_measurement')

    def test_invalid_container_shapes(self):
        self.check_bad([], 'scenario must be an object')
        for field in ('devices', 'stages', 'placements', 'links'):
            value = json.loads(EXAMPLE.read_text())
            value[field] = {}
            self.check_bad(value, field)
            value[field] = [None]
            self.check_bad(value, field + '[0]')

    def test_missing_and_invalid_numbers_include_field_path(self):
        for field in ('memory_bytes', 'ops_per_second'):
            for bad in (None, True, -1, 0, '100', 10**400):
                value = json.loads(EXAMPLE.read_text())
                value['devices'][3][field] = bad  # even an unused device
                self.check_bad(value, 'devices[3].' + field)
        value = json.loads(EXAMPLE.read_text())
        del value['stages'][0]['operations']
        self.check_bad(value, 'stages[0].operations')

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        valid = EXAMPLE.read_text()
        cases = [
            (valid.replace('"id": "laptop", "consent": true',
                           '"id": "laptop", "consent": false, "consent": true'),
             "duplicate JSON key: 'consent'"),
            (valid.replace('{', '{"ignored_metadata": NaN,', 1),
             'non-finite JSON constant: NaN'),
            (valid.replace('{', '{"ignored_metadata": Infinity,', 1),
             'non-finite JSON constant: Infinity'),
            (valid.replace('{', '{"ignored_metadata": -Infinity,', 1),
             'non-finite JSON constant: -Infinity'),
        ]
        for data, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                run = self.run_cli(data.encode())
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, '')
                self.assertNotIn('Traceback', run.stderr)
                self.assertIn(diagnostic, run.stderr)

    def test_duplicate_ids_names_and_links(self):
        for field in ('devices', 'stages', 'placements', 'links'):
            value = json.loads(EXAMPLE.read_text())
            value[field].append(copy.deepcopy(value[field][0]))
            self.check_bad(value, 'duplicate')

    def test_bad_placement_is_input_error_not_feasibility_result(self):
        for assignment in ('laptop', ['laptop'], ['missing', 'laptop'], [[], 'laptop']):
            value = json.loads(EXAMPLE.read_text())
            value['placements'][0]['devices'] = assignment
            self.check_bad(value, 'placements[0].devices')

    def test_consent_and_memory_and_missing_links_are_feasibility_rejections(self):
        value = json.loads(EXAMPLE.read_text())
        value['links'] = []
        run = self.run_cli(json.dumps(value).encode())
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(len(result['feasible']), 1)
        self.assertEqual(len(result['rejected']), 3)

    def test_empty_required_lists_rejected(self):
        for field in ('devices', 'stages', 'placements'):
            value = json.loads(EXAMPLE.read_text())
            value[field] = []
            self.check_bad(value, field)

    def test_malformed_text_is_concise(self):
        for content in (b'\xff', b'{', b'null'):
            run = self.run_cli(content)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(run.stdout, '')
            self.assertNotIn('Traceback', run.stderr)

    def test_consent_must_be_boolean_but_absence_denies(self):
        value = json.loads(EXAMPLE.read_text())
        value['devices'][0]['consent'] = 'true'
        self.check_bad(value, 'devices[0].consent')
        del value['devices'][0]['consent']
        run = self.run_cli(json.dumps(value).encode())
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(json.loads(run.stdout)['feasible'])

    def test_unknown_link_endpoint_rejected(self):
        value = json.loads(EXAMPLE.read_text())
        value['links'][0]['source'] = 'absent'
        self.check_bad(value, 'links[0].source')

    def test_arithmetic_overflow_does_not_emit_partial_json(self):
        value = json.loads(EXAMPLE.read_text())
        value['devices'][0]['ops_per_second'] = 1e-320
        self.check_bad(value, 'non-finite')


if __name__ == '__main__':
    unittest.main()
