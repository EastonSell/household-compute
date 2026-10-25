"""Bounded repeated paired measurements; all network delays are emulated waits."""
import argparse
import json
import platform
import statistics
import sys

from .process_mesh import _Stopped
from .session import WorkerSession, reference_forward, validate_request


def summarize(values):
    """Descriptive statistics only. No confidence interval or population claim."""
    return {'count': len(values), 'minimum': min(values), 'median': statistics.median(values),
            'mean': statistics.mean(values), 'maximum': max(values)}


def _pair(session, width, link, order):
    if order == 'reference_first':
        reference, reference_seconds = reference_forward(width)
    split = session.forward(width=width, **link)
    if split['status'] != 'ok':
        return split
    if order == 'split_first':
        reference, reference_seconds = reference_forward(width)
    output = split.pop('output')
    error = max(abs(a - b) for a, b in zip(reference, output)) if len(reference) == len(output) else float('inf')
    if error != 0:
        return {'status': 'correctness_failure', 'output_lengths_match': len(reference) == len(output)}
    return {**split, 'order': order, 'reference_seconds': reference_seconds,
            'max_abs_error': error, 'split_to_reference_ratio': split['split_seconds'] / reference_seconds}


def run_suite(*, opt_in=False, widths=None, links=None, repeats=5, warmup=1, cancel_event=None):
    if opt_in is not True:
        raise ValueError('explicit opt-in required')
    widths = [8, 64] if widths is None else widths
    links = [{'latency_ms': 0, 'bytes_per_second': None}, {'latency_ms': 10, 'bytes_per_second': 100000}] if links is None else links
    if not 1 <= len(widths) <= 8 or not 1 <= len(links) <= 8:
        raise ValueError('provide 1 to 8 widths and links')
    if type(repeats) is not int or not 1 <= repeats <= 100 or type(warmup) is not int or not 0 <= warmup <= 10:
        raise ValueError('repeats must be 1..100 and warmup 0..10')
    if len(widths) * len(links) * (warmup + repeats) > 1000:
        raise ValueError('suite exceeds 1000 paired requests')
    for width in widths:
        for link in links:
            if set(link) != {'latency_ms', 'bytes_per_second'}:
                raise ValueError('links must contain only latency_ms and bytes_per_second')
            validate_request(width, link['latency_ms'], link['bytes_per_second'], 5)
    result = {'kind': 'repeated_local_process_measurement', 'status': 'ok',
              'python': sys.version.split()[0], 'machine': platform.machine(),
              'workload': 'fixed_synthetic_two_layer_relu', 'worker_processes_started': 0, 'cases': [],
              'interpretation': 'Descriptive same-host samples, not confidence intervals, physical-network measurements, VMs, or trained-model inference.'}
    session = WorkerSession(opt_in=True, cancel_event=cancel_event)
    try:
        with session:
            result['worker_processes_started'] = len(session.processes)
            result['startup_seconds'] = session.startup_seconds
            for width in widths:
                for link in links:
                    case = {'width': width, 'link_assumptions': dict(link), 'warmup_runs_excluded': warmup, 'samples': []}
                    result['cases'].append(case)
                    for index in range(warmup + repeats):
                        sample_index = index - warmup
                        order = 'reference_first' if sample_index % 2 == 0 else 'split_first'
                        sample = _pair(session, width, link, order)
                        if sample['status'] != 'ok':
                            result['status'] = sample['status']
                            case['failure'] = sample
                            return result
                        if sample_index >= 0:
                            case['samples'].append(sample)
                    for field in ['reference_seconds', 'split_seconds', 'split_to_reference_ratio', 'emulated_wait_observed_seconds']:
                        case[field] = summarize([sample[field] for sample in case['samples']])
    except _Stopped as error:
        result['status'] = str(error)
    finally:
        result['worker_processes_started'] = len(session.processes)
        result['cleanup'] = session.cleanup
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opt-in', action='store_true')
    parser.add_argument('--widths', type=int, nargs='+', default=[8, 64])
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--warmup', type=int, default=1)
    args = parser.parse_args()
    try:
        result = run_suite(**vars(args))
    except (ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['status'] == 'ok' and result['cleanup']['workers_cleaned_up'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
