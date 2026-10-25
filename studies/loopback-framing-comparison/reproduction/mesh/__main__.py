"""Offline CLI; emits JSON to stdout and errors to stderr."""
import argparse
import json
from pathlib import Path

from .benchmark import benchmark
from .model import simulate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    simulation = commands.add_parser('simulate', help='compare named explicit placements')
    simulation.add_argument('scenario', type=Path)
    timing = commands.add_parser('benchmark', help='measure local Python CPU matvec only')
    timing.add_argument('--size', type=int, default=64)
    timing.add_argument('--iterations', type=int, default=20)
    timing.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    try:
        if args.command == 'benchmark':
            result = benchmark(args.size, args.iterations, args.repeats)
        else:
            scenario = json.loads(args.scenario.read_text())
            feasible, rejected = [], []
            for candidate in scenario['placements']:
                try:
                    estimate = simulate(scenario, candidate['devices'])
                    feasible.append({'name': candidate['name'], **estimate})
                except ValueError as error:
                    rejected.append({'name': candidate['name'], 'reason': str(error)})
            feasible.sort(key=lambda item: item['total_seconds'])
            result = {'kind': 'analytical_comparison', 'feasible': feasible, 'rejected': rejected}
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
