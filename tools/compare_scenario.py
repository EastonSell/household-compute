"""Validate and compare explicit analytical placements, without experiments.

This additive entry point leaves the historical mesh CLI and study freezes intact.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mesh.model import simulate


def _object(value, path):
    if not isinstance(value, dict):
        raise ValueError(f'{path} must be an object')
    return value


def _text(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{path} must be a nonempty string')
    return value


def _number(value, path, positive=False):
    try:
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value) and value >= 0 and (not positive or value > 0))
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f'{path} must be a finite {"positive" if positive else "nonnegative"} number')


def _records(scenario, field, optional=False):
    records = scenario.get(field, [] if optional else None)
    if not isinstance(records, list) or (not optional and not records):
        raise ValueError(f'{field} must be a {"possibly empty" if optional else "nonempty"} array')
    for index, record in enumerate(records):
        _object(record, f'{field}[{index}]')
    return records


def validate(scenario):
    """Reject malformed input globally; leave resource infeasibility to simulate."""
    _object(scenario, 'scenario')
    ids = {}
    for field in ('devices', 'stages', 'placements'):
        records = _records(scenario, field)
        ids[field] = set()
        key = 'name' if field == 'placements' else 'id'
        for index, record in enumerate(records):
            path = f'{field}[{index}]'
            identifier = _text(record.get(key), f'{path}.{key}')
            if identifier in ids[field]:
                raise ValueError(f'{path}.{key}: duplicate {identifier!r}')
            ids[field].add(identifier)
            if field == 'devices':
                for number in ('memory_bytes', 'ops_per_second'):
                    _number(record.get(number), f'{path}.{number}', positive=True)
                if 'consent' in record and not isinstance(record['consent'], bool):
                    raise ValueError(f'{path}.consent must be a boolean; omission denies consent')
            elif field == 'stages':
                for number in ('operations', 'weights_bytes', 'workspace_bytes', 'output_bytes'):
                    _number(record.get(number), f'{path}.{number}')
            else:
                assignment = record.get('devices')
                if not isinstance(assignment, list) or len(assignment) != len(scenario['stages']):
                    raise ValueError(f'{path}.devices must assign one device per stage')
                for offset, device in enumerate(assignment):
                    _text(device, f'{path}.devices[{offset}]')
                    if device not in ids['devices']:
                        raise ValueError(f'{path}.devices[{offset}]: unknown device {device!r}')
    seen = set()
    for index, link in enumerate(_records(scenario, 'links', optional=True)):
        path = f'links[{index}]'
        for endpoint in ('source', 'target'):
            device = _text(link.get(endpoint), f'{path}.{endpoint}')
            if device not in ids['devices']:
                raise ValueError(f'{path}.{endpoint}: unknown device {device!r}')
        key = (link['source'], link['target'])
        if key in seen:
            raise ValueError(f'{path}: duplicate directed link')
        seen.add(key)
        _number(link.get('bytes_per_second'), f'{path}.bytes_per_second', positive=True)
        _number(link.get('latency_ms'), f'{path}.latency_ms')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key!r}')
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f'non-finite JSON constant: {value}')


def compare_bytes(content):
    """Return legacy comparison fields plus exact-byte input provenance."""
    scenario = json.loads(content.decode('utf-8'), object_pairs_hook=_unique_object,
                          parse_constant=_constant)
    validate(scenario)
    feasible, rejected = [], []
    for candidate in scenario['placements']:
        try:
            estimate = simulate(scenario, candidate['devices'])
        except ValueError as error:
            rejected.append({'name': candidate['name'], 'reason': str(error)})
            continue
        # Finite inputs can overflow on division or accumulation. Never publish
        # an invalid JSON number, or quietly label numerical overflow infeasible.
        try:
            json.dumps(estimate, allow_nan=False)
        except ValueError as error:
            raise ValueError(f"placement {candidate['name']!r}: non-finite arithmetic result") from error
        feasible.append({'name': candidate['name'], **estimate})
    feasible.sort(key=lambda item: item['total_seconds'])
    return {'kind': 'analytical_comparison', 'feasible': feasible, 'rejected': rejected,
            'scenario_sha256': hashlib.sha256(content).hexdigest(),
            'evidence_kind': 'assumption_conditional_not_measurement'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path, help='UTF-8 JSON scenario; never modified')
    args = parser.parse_args()
    try:
        result = compare_bytes(args.scenario.read_bytes())
        output = json.dumps(result, indent=2, allow_nan=False)
    except (OSError, UnicodeError, ValueError, OverflowError, RecursionError) as error:
        parser.error(str(error))
    print(output)


if __name__ == '__main__':
    main()
