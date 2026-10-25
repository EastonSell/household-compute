"""Reusable private-pipe workers for the fixed synthetic neural workload."""
import json
import math
import multiprocessing
import threading
import time

from .process_mesh import _Stopped, _check, _encode, _layer, _receive, _wait, _worker


def validate_request(width, latency_ms, bytes_per_second, timeout_seconds):
    if type(width) is not int or not 1 <= width <= 256:
        raise ValueError('width must be an integer between 1 and 256')
    for name, value, positive in [('latency_ms', latency_ms, False), ('bytes_per_second', bytes_per_second, True), ('timeout_seconds', timeout_seconds, True)]:
        if name == 'bytes_per_second' and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
            raise ValueError(f'invalid {name}')
    # Conservative JSON activation size upper bound, checked before workers start.
    if bytes_per_second is not None and not math.isfinite((width * 32 + 2) / bytes_per_second + latency_ms / 1000):
        raise ValueError('derived emulated delay must be finite')


def input_vector(width):
    return [(index % 11 - 5) / 11 for index in range(width)]


def reference_forward(width):
    vector = input_vector(width)
    started = time.perf_counter()
    output = _layer(_layer(vector, 0), 1)
    return output, time.perf_counter() - started


class WorkerSession:
    """Spawn once, serve sequential requests, invalidate after any failed request.

    Only trusted, fixed local kernels are supported. Not a remote-code API.
    """
    def __init__(self, *, opt_in=False, cancel_event=None):
        if opt_in is not True:
            raise ValueError('explicit opt-in required')
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self.processes = []
        self.connections = []
        self.cleanup = None
        self.failed = False
        self.startup_seconds = 0.0
        self.shutdown_grace_seconds = .2

    def __enter__(self):
        if self.processes or self.cleanup is not None:
            raise RuntimeError('session cannot be restarted')
        started = time.perf_counter()
        context = multiprocessing.get_context('spawn')
        try:
            for stage in range(2):
                parent, child = context.Pipe(duplex=True)
                process = context.Process(target=_worker, args=(child, stage, None))
                try:
                    process.start()
                except BaseException:
                    parent.close()
                    child.close()
                    raise
                child.close()
                self.processes.append(process)
                self.connections.append(parent)
            for connection in self.connections:
                if _receive(connection, started + 10, self.cancel_event) != b'ready':
                    raise _Stopped('disconnected')
            self.startup_seconds = time.perf_counter() - started
            return self
        except BaseException:
            self.close()
            raise

    def forward(self, *, width=64, latency_ms=0, bytes_per_second=None, timeout_seconds=5):
        if self.failed:
            raise RuntimeError('failed session cannot be reused')
        if len(self.connections) != 2 or self.cleanup is not None:
            raise RuntimeError('session is not active')
        validate_request(width, latency_ms, bytes_per_second, timeout_seconds)
        current = input_vector(width)
        started = time.perf_counter()
        deadline = started + timeout_seconds
        result = {'status': 'running', 'worker_compute_seconds': [], 'interstage_payload_bytes': 0,
                  'emulated_wait_requested_seconds': 0.0, 'emulated_wait_observed_seconds': 0.0}
        try:
            for stage, connection in enumerate(self.connections):
                _check(deadline, self.cancel_event)
                payload = _encode(current)
                if stage == 1:
                    result['interstage_payload_bytes'] = len(payload)
                    delay = latency_ms / 1000 + (len(payload) / bytes_per_second if bytes_per_second is not None else 0)
                    result['emulated_wait_requested_seconds'] = delay
                    wait_started = time.perf_counter()
                    try:
                        if delay:
                            _wait(delay, deadline, self.cancel_event)
                    finally:
                        result['emulated_wait_observed_seconds'] = time.perf_counter() - wait_started if delay else 0.0
                try:
                    connection.send_bytes(payload)
                except (BrokenPipeError, OSError):
                    raise _Stopped('disconnected') from None
                response = json.loads(_receive(connection, deadline, self.cancel_event))
                current = response['output']
                result['worker_compute_seconds'].append(response['compute_seconds'])
            result['output'] = current
            result['status'] = 'ok'
        except _Stopped as stopped:
            self.failed = True
            result['status'] = str(stopped)
        result['split_seconds'] = time.perf_counter() - started
        return result

    def close(self):
        if self.cleanup is not None:
            return
        started = time.perf_counter()
        for connection in self.connections:
            try:
                connection.send_bytes(b'')
            except (BrokenPipeError, OSError):
                pass
            connection.close()
        forced = []
        for process in self.processes:
            process.join(self.shutdown_grace_seconds)
            force = process.is_alive()
            forced.append(force)
            if force:
                process.terminate()
                process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
        self.cleanup = {'workers_cleaned_up': all(not p.is_alive() for p in self.processes),
                        'worker_exitcodes': [p.exitcode for p in self.processes],
                        'worker_forced_termination': forced, 'cleanup_seconds': time.perf_counter() - started}
        for process in self.processes:
            if not process.is_alive():
                process.close()

    def __exit__(self, *_):
        self.close()
