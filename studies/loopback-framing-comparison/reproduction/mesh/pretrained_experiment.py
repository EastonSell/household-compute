"""Pinned real-model, same-host partition correctness and small paired timings."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time

from .pretrained_model import MODEL_ID, REVISION, HASHES, load_reference, verify_model
from .pretrained_session import PretrainedSession
from .repeated import summarize
from .process_mesh import _Stopped

# Public example text, encoded once with the pinned tokenizer, no chat template.
CASES = [
    {'text': 'The capital of France is', 'tokens': [504, 3575, 282, 4649, 314]},
    {'text': 'A small computer sends an intermediate tensor to another computer. The main cost of this operation is',
     'tokens': [49, 1165, 2583, 14137, 354, 14019, 13104, 288, 1372, 2583, 30, 378, 1085, 1708, 282, 451, 4953, 314]},
]


def available_memory_bytes():
    # Host memory observation, not an enforceable cgroup/resource guarantee.
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise ValueError('cannot establish available host memory')


def run(directory, *, opt_in=False, repeats=3):
    if opt_in is not True:
        raise ValueError('explicit opt-in required')
    if type(repeats) is not int or not 2 <= repeats <= 10:
        raise ValueError('repeats must be 2..10')
    if sys.platform != 'linux':
        raise ValueError('this experimental memory/timing runner currently supports Linux only')
    available = available_memory_bytes()
    if available < 3 * 1024**3:
        raise ValueError('at least 3 GiB observed available host memory required')
    verify_model(directory)
    import torch
    import transformers
    torch.set_num_threads(1)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    load_started = time.perf_counter()
    model = load_reference(directory)
    reference_load = time.perf_counter() - load_started
    result = {'kind': 'pretrained_local_partition_measurement', 'status': 'running',
              'model_id': MODEL_ID, 'revision': REVISION, 'verified_sha256': HASHES,
              'torch': torch.__version__, 'transformers': transformers.__version__,
              'dtype': 'float32', 'attention': 'eager', 'threads_per_process': 1,
              'kv_cache': False, 'padding': False, 'batch_size': 1, 'split_after_layer': 14,
              'observed_available_host_memory_bytes_before_load': available,
              'reference_load_seconds': reference_load, 'correctness_gate': [], 'cases': [],
              'scope': 'Real pinned pretrained weights on one host over private pipes. Emulated waits are not physical-network, VM, or heterogeneous-device measurements. No quality benchmark or generation throughput claim.'}

    def reference(tokens):
        ids = torch.tensor([tokens], dtype=torch.int64)
        mask = torch.ones_like(ids)
        started = time.perf_counter()
        logits = model(input_ids=ids, attention_mask=mask, use_cache=False, num_logits_to_keep=1).logits[:, -1, :]
        return logits, time.perf_counter() - started

    def compare(actual, expected):
        torch.testing.assert_close(actual, expected, rtol=1e-4, atol=1e-4)
        if actual.argmax(-1).item() != expected.argmax(-1).item():
            raise ValueError('next-token argmax mismatch')
        return {'max_abs_error': (actual - expected).abs().max().item(),
                'next_token_id': actual.argmax(-1).item(), 'rtol': 1e-4, 'atol': 1e-4}

    session = PretrainedSession(directory, opt_in=True)
    try:
        with torch.inference_mode(), session:
            result['partition_startup_seconds'] = session.startup_seconds
            result['worker_load_reports'] = session.load_reports
            # All correctness gates pass before any retained timing sample.
            result['phase'] = 'correctness_gate'
            for case in CASES:
                expected, _ = reference(case['tokens'])
                split = session.forward(case['tokens'])
                if split['status'] != 'ok':
                    raise RuntimeError(f"correctness gate failed: {split['status']}")
                result['correctness_gate'].append({'tokens': len(case['tokens']), **compare(split['logits'], expected)})
            result['phase'] = 'paired_measurements'
            for case in CASES:
                for link in [{'latency_ms': 0, 'bytes_per_second': None}, {'latency_ms': 10, 'bytes_per_second': 1000000}]:
                    measured = {'text': case['text'], 'token_ids': case['tokens'], 'link_assumptions': link,
                                'warmup_pairs_excluded': 1, 'samples': []}
                    result['cases'].append(measured)
                    for index in range(-1, repeats):
                        order = 'reference_first' if index % 2 == 0 else 'split_first'
                        if order == 'reference_first':
                            expected, elapsed = reference(case['tokens'])
                        split = session.forward(case['tokens'], **link)
                        if split['status'] != 'ok':
                            raise RuntimeError(f"partition request failed: {split['status']}")
                        if order == 'split_first':
                            expected, elapsed = reference(case['tokens'])
                        accuracy = compare(split.pop('logits'), expected)
                        if index >= 0:
                            measured['samples'].append({**split, **accuracy, 'reference_seconds': elapsed, 'order': order})
                    for field in ['reference_seconds', 'split_seconds', 'emulated_wait_observed_seconds']:
                        measured[field] = summarize([sample[field] for sample in measured['samples']])
            result['status'] = 'ok'
            result['phase'] = 'complete'
    except (_Stopped, RuntimeError, ValueError, AssertionError, OSError) as error:
        result['status'] = 'failed'
        result['failure'] = {'type': type(error).__name__, 'reason': str(error)[:1000]}
    finally:
        result['cleanup'] = session.cleanup
        result['controller_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--opt-in', action='store_true')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    # Offline-only behavior even if the optional library has other defaults.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    try:
        result = run(args.model_dir, opt_in=args.opt_in, repeats=args.repeats)
    except (ValueError, OSError, RuntimeError, AssertionError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['status'] == 'ok' and result['cleanup']['workers_cleaned_up'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
