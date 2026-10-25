"""Optional persistent model partitions over private pipes, no network service."""
import json
import math
import struct
import multiprocessing
try:
    import resource
except ImportError:  # Windows and other platforms without Unix resource accounting.
    resource = None
import time

from .pretrained_protocol import MAX_FRAME_BYTES, decode_frame, encode_frame, validate_tokens
from .process_mesh import _Stopped, _check, _wait
from .session import WorkerSession


def _peak_rss_kib():
    if resource is None:
        return None
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def _validate_metrics(report, timing_key):
    value = report[timing_key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid worker timing')
    if report['peak_rss_kib'] is not None and (type(report['peak_rss_kib']) is not int or report['peak_rss_kib'] <= 0):
        raise ValueError('invalid worker memory metric')


def pack_tensor(tensor):
    array = tensor.detach().cpu().contiguous().numpy().astype('<f4', copy=False)
    return encode_frame(list(array.shape), array.tobytes())


def unpack_tensor(frame):
    import numpy as np
    import torch
    shape, payload = decode_frame(frame)
    return torch.from_numpy(np.frombuffer(payload, dtype='<f4').copy().reshape(shape))


def _recv(connection, deadline, cancel_event):
    while True:
        _check(deadline, cancel_event)
        if connection.poll(min(.01, max(0, deadline - time.perf_counter()))):
            try:
                return connection.recv_bytes(MAX_FRAME_BYTES)
            except (EOFError, OSError):
                raise _Stopped('disconnected') from None


def _model_worker(connection, directory, stage):
    try:
        import torch
        from .pretrained_model import Partition
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        started = time.perf_counter()
        partition = Partition(directory, stage)
        connection.send_bytes(json.dumps({'ready': True, 'stage': stage, 'load_seconds': time.perf_counter() - started,
                                          'peak_rss_kib': _peak_rss_kib()}).encode())
        request_id = 0
        with torch.inference_mode():
            while True:
                payload = connection.recv_bytes(MAX_FRAME_BYTES)
                if not payload:
                    return
                request_id += 1
                value = torch.tensor([validate_tokens(json.loads(payload))], dtype=torch.int64) if stage == 0 else unpack_tensor(payload)
                started = time.perf_counter()
                output = partition(value)
                elapsed = time.perf_counter() - started
                frame = pack_tensor(output)
                connection.send_bytes(json.dumps({'stage': stage, 'request_id': request_id, 'compute_seconds': elapsed,
                                                  'peak_rss_kib': _peak_rss_kib()}).encode())
                connection.send_bytes(frame)
    except (EOFError, BrokenPipeError):
        return
    finally:
        connection.close()


class PretrainedSession(WorkerSession):
    def __init__(self, directory, *, opt_in=False, cancel_event=None):
        super().__init__(opt_in=opt_in, cancel_event=cancel_event)
        self.directory = str(directory)
        self.load_reports = []
        self.shutdown_grace_seconds = 3.0
        self.request_id = 0

    def __enter__(self):
        if self.processes or self.cleanup is not None:
            raise RuntimeError('session cannot be restarted')
        started = time.perf_counter()
        context = multiprocessing.get_context('spawn')
        try:
            for stage in range(2):
                parent, child = context.Pipe(duplex=True)
                process = context.Process(target=_model_worker, args=(child, self.directory, stage))
                try:
                    process.start()
                except BaseException:
                    parent.close()
                    child.close()
                    raise
                child.close()
                self.processes.append(process)
                self.connections.append(parent)
                # Sequential readiness avoids simultaneous model-load transients.
                report = json.loads(_recv(parent, started + 120, self.cancel_event))
                if not isinstance(report, dict) or set(report) != {'ready', 'stage', 'load_seconds', 'peak_rss_kib'} or report['ready'] is not True or type(report['stage']) is not int or report['stage'] != stage:
                    raise ValueError('invalid readiness report')
                _validate_metrics(report, 'load_seconds')
                self.load_reports.append(report)
            self.startup_seconds = time.perf_counter() - started
            return self
        except BaseException:
            self.close()
            raise

    def forward(self, tokens, *, latency_ms=0, bytes_per_second=None, timeout_seconds=10):
        import math
        if self.failed or self.cleanup is not None or len(self.connections) != 2:
            raise RuntimeError('session is not active or has failed')
        validate_tokens(tokens)
        for name, value, positive in [('latency_ms', latency_ms, False), ('bytes_per_second', bytes_per_second, True), ('timeout_seconds', timeout_seconds, True)]:
            if name == 'bytes_per_second' and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
                raise ValueError(f'invalid {name}')
        if bytes_per_second is not None and not math.isfinite(MAX_FRAME_BYTES / bytes_per_second + latency_ms / 1000):
            raise ValueError('derived delay must be finite')
        self.request_id += 1
        payload = json.dumps(tokens).encode()
        result = {'worker_compute_seconds': [], 'worker_peak_rss_kib': [], 'emulated_wait_requested_seconds': 0.0,
                  'emulated_wait_observed_seconds': 0.0, 'activation_frame_bytes': 0}
        started = time.perf_counter()
        deadline = started + timeout_seconds
        try:
            for stage, connection in enumerate(self.connections):
                _check(deadline, self.cancel_event)
                if stage == 1:
                    result['activation_frame_bytes'] = len(payload)
                    delay = latency_ms / 1000 + (len(payload) / bytes_per_second if bytes_per_second is not None else 0)
                    result['emulated_wait_requested_seconds'] = delay
                    wait_started = time.perf_counter()
                    try:
                        if delay:
                            _wait(delay, deadline, self.cancel_event)
                    finally:
                        result['emulated_wait_observed_seconds'] = time.perf_counter() - wait_started if delay else 0.0
                connection.send_bytes(payload)
                report = json.loads(_recv(connection, deadline, self.cancel_event))
                if not isinstance(report, dict) or set(report) != {'stage', 'request_id', 'compute_seconds', 'peak_rss_kib'}:
                    raise ValueError('invalid response report')
                if type(report['stage']) is not int or report['stage'] != stage or type(report['request_id']) is not int or report['request_id'] != self.request_id:
                    raise ValueError('out-of-order response report')
                _validate_metrics(report, 'compute_seconds')
                payload = _recv(connection, deadline, self.cancel_event)
                shape, values = decode_frame(payload)
                expected_shape = [1, len(tokens), 576] if stage == 0 else [1, 49152]
                if shape != expected_shape or not all(math.isfinite(value[0]) for value in struct.iter_unpack('<f', values)):
                    raise ValueError('invalid response tensor')
                result['worker_compute_seconds'].append(report['compute_seconds'])
                result['worker_peak_rss_kib'].append(report['peak_rss_kib'])
            result['logits'] = unpack_tensor(payload)
            result['status'] = 'ok'
        except (ValueError, KeyError, TypeError, UnicodeDecodeError, struct.error) as error:
            self.failed = True
            result['status'] = 'protocol_error'
        except (_Stopped, BrokenPipeError, EOFError, OSError) as error:
            self.failed = True
            result['status'] = str(error) if isinstance(error, _Stopped) else 'disconnected'
        result['split_seconds'] = time.perf_counter() - started
        return result
