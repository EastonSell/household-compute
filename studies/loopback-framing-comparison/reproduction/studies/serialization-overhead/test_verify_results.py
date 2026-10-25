"""Adversarial artifact tests; all timing numbers below are synthetic."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import random

import benchmark as b

import verify_results as v


def synthetic_result():
    cases = b.build_cases()
    rng = random.Random(20261025)
    schedule = []
    for block in range(9):
        cells = [(c, o) for c in cases for o in
                 ['noop', 'payload_copy', 'header_pack', 'finite_scan', 'frame_pack', 'frame_decode']]
        rng.shuffle(cells)
        for order, (case, operation) in enumerate(cells):
            schedule.append({'case': case, 'operation': operation, 'block': block, 'order': order})
    rows = [dict(entry, iterations=50, wall_ns=1000, cpu_ns=500,
                 wall_ns_per_op=20.0, cpu_ns_per_op=10.0) for entry in schedule]
    summaries = [{'case': case, 'operation': operation, 'batches': 9,
                  'wall_ns_per_op': {'median': 20.0, 'min': 20.0, 'max': 20.0, 'iqr': 0.0},
                  'cpu_ns_per_op': {'median': 10.0, 'min': 10.0, 'max': 10.0, 'iqr': 0.0}}
                 for case, operation in sorted({(r['case'], r['operation']) for r in rows})]
    return {'schema': 1, 'status': 'complete', 'run_id': 'run-001',
            'scope': 'single-host single-process framing controls; no sockets, mesh, model, inference, or device claim',
            'started_at_utc': '2026-10-25T06:00:00+00:00', 'finished_at_utc': '2026-10-25T06:00:01+00:00',
            'elapsed_monotonic_seconds': 1.0,
            'config': {'blocks': 9, 'iterations': 50, 'warmup': 5, 'seed': 20261025},
            'environment': b.environment(), 'freeze_sha256': 'a' * 64,
            'sources': {name: 'b' * 64 for name in b.SOURCE_FILES},
            'inputs': {name: {'payload_bytes': len(c.frame.payload), 'frame_bytes': len(c.wire),
                              'payload_sha256': b.sha256(c.frame.payload), 'frame_sha256': b.sha256(c.wire)}
                       for name, c in cases.items()},
            'schedule': schedule, 'rows': rows, 'summaries': summaries}


class VerificationTests(unittest.TestCase):
    def test_valid_synthetic_grid_recomputes_every_row(self):
        fixture = synthetic_result()
        self.assertEqual(v.validate_record(fixture, fixture['sources'], fixture['freeze_sha256']),
                         {'run_id': 'run-001', 'rows': 216, 'cells': 24})

    def test_rejects_missing_duplicate_reordered_and_extra_rows(self):
        original = synthetic_result()
        mutations = [original['rows'][:-1], original['rows'] + [original['rows'][0]],
                     [original['rows'][1], original['rows'][0]] + original['rows'][2:],
                     [original['rows'][0]] + original['rows'][:-1]]
        for rows in mutations:
            fixture = copy.deepcopy(original)
            fixture['rows'] = rows
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                v.validate_record(fixture, original['sources'], original['freeze_sha256'])

    def test_rejects_timing_tampering_and_boolean_numeric_aliases(self):
        original = synthetic_result()
        for field, value in [('wall_ns', 0), ('wall_ns', -1), ('cpu_ns', True),
                             ('iterations', True), ('wall_ns_per_op', float('nan')),
                             ('wall_ns_per_op', 999.0), ('block', False), ('order', True)]:
            fixture = copy.deepcopy(original)
            fixture['rows'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                v.validate_record(fixture, original['sources'], original['freeze_sha256'])

    def test_rejects_changed_summary_config_identity_inputs_and_sources(self):
        original = synthetic_result()
        for mutate in [
            lambda r: r['summaries'][0]['wall_ns_per_op'].update(median=1),
            lambda r: r['config'].update(iterations=51),
            lambda r: r.update(run_id='unplanned-run'),
            lambda r: r.update(status='failed'),
            lambda r: r.update(scope='mesh throughput'),
            lambda r: r['inputs']['audit_reply'].update(frame_bytes=42),
            lambda r: r['sources'].update({'benchmark.py': '0' * 64}),
            lambda r: r.update(freeze_sha256='0' * 64),
            lambda r: r.update(unplanned=True),
            lambda r: r['schedule'][0].update(operation='noop'),
        ]:
            fixture = copy.deepcopy(original)
            mutate(fixture)
            with self.assertRaises(ValueError):
                v.validate_record(fixture, original['sources'], original['freeze_sha256'])

    def test_rejects_impossible_batch_or_aggregate_duration(self):
        original = synthetic_result()
        for duration in (181_000_000_000, 100_000_000):
            fixture = copy.deepcopy(original)
            for row in fixture['rows']:
                row['wall_ns'] = duration
                row['wall_ns_per_op'] = duration / 50
            for summary in fixture['summaries']:
                summary['wall_ns_per_op'] = {'median': duration / 50, 'min': duration / 50,
                                             'max': duration / 50, 'iqr': 0.0}
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                v.validate_record(fixture, original['sources'], original['freeze_sha256'])
        fixture = copy.deepcopy(original)
        fixture['elapsed_monotonic_seconds'] = 0.000001
        with self.assertRaises(ValueError):
            v.validate_record(fixture, original['sources'], original['freeze_sha256'])
        for elapsed in [True, 0.0, float('nan'), 180.01]:
            fixture = copy.deepcopy(original)
            fixture['elapsed_monotonic_seconds'] = elapsed
            with self.subTest(elapsed=elapsed), self.assertRaises(ValueError):
                v.validate_record(fixture, original['sources'], original['freeze_sha256'])

    def test_strict_json_rejects_duplicate_keys_nonfinite_and_oversize(self):
        for raw in ['{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                v.parse_json(raw)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'large.json'
            path.write_text(' ' * (4 * 1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                v.read_json(path)

    def test_journal_must_match_complete_result_and_no_extra_events(self):
        fixture = synthetic_result()
        start = {k: value for k, value in fixture.items()
                 if k not in ('rows', 'summaries', 'finished_at_utc', 'elapsed_monotonic_seconds')}
        start['status'] = 'running'
        events = [{'event': 'start', 'metadata': start}]
        events += [{'event': 'row', 'row': row} for row in fixture['rows']]
        events += [{'event': 'finish', 'status': 'complete', 'rows': 216,
                    'finished_at_utc': fixture['finished_at_utc'],
                    'elapsed_monotonic_seconds': fixture['elapsed_monotonic_seconds']}]
        v.validate_journal(events, fixture)
        for altered in [events[:-1], events + [events[-1]], events[1:]]:
            with self.assertRaises(ValueError):
                v.validate_journal(altered, fixture)
        changed = copy.deepcopy(events)
        changed[1]['row']['wall_ns'] += 1
        with self.assertRaises(ValueError):
            v.validate_journal(changed, fixture)


if __name__ == '__main__':
    unittest.main()
