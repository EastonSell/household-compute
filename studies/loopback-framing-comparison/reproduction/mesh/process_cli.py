"""Run an explicitly opted-in, same-host two-worker experiment over private pipes."""
import argparse
import json

from .process_mesh import run_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opt-in', action='store_true', help='authorize these two local fixed-kernel workers')
    parser.add_argument('--width', type=int, default=64)
    parser.add_argument('--latency-ms', type=float, default=0)
    parser.add_argument('--bytes-per-second', type=float)
    parser.add_argument('--timeout-seconds', type=float, default=5)
    parser.add_argument('--fault', choices=['disconnect', 'stall'])
    args = parser.parse_args()
    try:
        result = run_experiment(**vars(args))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['status'] == 'ok' and result['workers_cleaned_up'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
