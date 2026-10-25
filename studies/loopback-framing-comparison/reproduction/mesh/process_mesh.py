"""Real local processes, private pipes, and explicitly emulated network delay.

This is not a network service or sandbox. Workers execute only this fixed kernel.
"""
import json
import math
import multiprocessing
import platform
import sys
import threading
import time


class _Stopped(Exception):
    pass


def _layer(vector, stage):
    """Deterministic dense layer with bias and ReLU, using synthetic weights."""
    width = len(vector)
    return [max(0.0, sum(value * (((row * 3 + col * 5 + stage) % 17 - 8) / (width * 8))
                         for col, value in enumerate(vector)) + (row % 5 - 2) / 20)
            for row in range(width)]


def _encode(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _worker(connection, stage, fault):
    try:
        connection.send_bytes(b'ready')
        while True:
            request = connection.recv_bytes(100000)
            if not request:
                return
            if fault == 'disconnect':
                return
            if fault == 'stall':
                time.sleep(60)  # Parent cancellation/timeout must terminate this worker.
            vector = json.loads(request)
            started = time.perf_counter()
            output = _layer(vector, stage)
            elapsed = time.perf_counter() - started
            connection.send_bytes(_encode({'output': output, 'compute_seconds': elapsed}))
    except (EOFError, BrokenPipeError):
        return
    finally:
        connection.close()


def _check(deadline, cancel_event):
    if cancel_event.is_set():
        raise _Stopped('cancelled')
    if time.perf_counter() >= deadline:
        raise _Stopped('timeout')


def _receive(connection, deadline, cancel_event):
    while True:
        _check(deadline, cancel_event)
        if connection.poll(min(.01, max(0, deadline - time.perf_counter()))):
            try:
                return connection.recv_bytes(100000)
            except (EOFError, OSError):
                raise _Stopped('disconnected') from None


def _wait(seconds, deadline, cancel_event):
    finish = time.perf_counter() + seconds
    while True:
        _check(deadline, cancel_event)
        remaining = finish - time.perf_counter()
        if remaining <= 0:
            return
        cancel_event.wait(min(.01, remaining, max(0, deadline - time.perf_counter())))


def run_experiment(*, opt_in=False, width=64, latency_ms=0, bytes_per_second=None,
                   timeout_seconds=5, cancel_event=None, fault=None):
    """Run two spawned workers and compare their forward pass with local execution.

    The only emulated link is the stage-0 -> stage-1 activation boundary. Input,
    result, readiness and control messages use actual local pipes without emulated
    latency. The request timeout starts after both workers report ready; startup
    has a separate 10-second budget. Cancellation applies to startup and requests.
    """
    if opt_in is not True:
        raise ValueError('explicit opt-in is required to start local workers')
    if type(width) is not int or not 1 <= width <= 256:
        raise ValueError('width must be an integer between 1 and 256')
    for name, value, positive in [('latency_ms', latency_ms, False), ('timeout_seconds', timeout_seconds, True),
                                  ('bytes_per_second', bytes_per_second, True)]:
        if name == 'bytes_per_second' and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
            raise ValueError(f'{name} must be finite and {"positive" if positive else "nonnegative"}')
    if fault not in (None, 'disconnect', 'stall'):
        raise ValueError('fault must be disconnect, stall, or None')
    cancel_event = cancel_event if cancel_event is not None else threading.Event()
    vector = [(index % 11 - 5) / 11 for index in range(width)]
    started = time.perf_counter()
    reference_activation = _layer(vector, 0)
    reference = _layer(reference_activation, 1)
    reference_seconds = time.perf_counter() - started
    expected_payload_bytes = len(_encode(reference_activation))
    expected_delay = latency_ms / 1000 + (expected_payload_bytes / bytes_per_second if bytes_per_second is not None else 0)
    if not math.isfinite(expected_delay):
        raise ValueError('derived emulated delay must be finite; increase bytes_per_second')
    result = {
        'kind': 'local_process_experiment', 'status': 'starting', 'width': width,
        'python': sys.version.split()[0], 'implementation': platform.python_implementation(),
        'machine': platform.machine(),
        'reference_seconds': reference_seconds,
        'worker_count': 2, 'worker_compute_seconds': [],
        'latency_ms_assumption': latency_ms, 'bytes_per_second_assumption': bytes_per_second,
        'fault_injected': fault, 'timeout_seconds': timeout_seconds,
        'interstage_payload_bytes': 0, 'emulated_wait_requested_seconds': 0.0,
        'emulated_wait_observed_seconds': 0.0,
        'scope': 'Actual same-host worker processes and fixed synthetic neural forward pass; not VMs, physical network, trained model, or device-performance measurement.',
    }
    context = multiprocessing.get_context('spawn')
    processes, connections = [], []
    inference_started = None
    startup_started = time.perf_counter()
    try:
        for stage in range(2):
            parent, child = context.Pipe(duplex=True)
            process = context.Process(target=_worker, args=(child, stage, fault if stage == 0 else None))
            try:
                process.start()
            except BaseException:
                parent.close()
                child.close()
                raise
            child.close()
            processes.append(process)
            connections.append(parent)
        for connection in connections:
            if _receive(connection, startup_started + 10, cancel_event) != b'ready':
                raise _Stopped('disconnected')
        result['startup_seconds'] = time.perf_counter() - startup_started
        inference_started = time.perf_counter()
        deadline = inference_started + timeout_seconds
        current = vector
        for stage, connection in enumerate(connections):
            _check(deadline, cancel_event)
            payload = _encode(current)
            if stage == 1:
                result['interstage_payload_bytes'] = len(payload)
                delay = latency_ms / 1000 + (len(payload) / bytes_per_second if bytes_per_second is not None else 0)
                result['emulated_wait_requested_seconds'] = delay
                wait_started = time.perf_counter()
                try:
                    if delay:
                        _wait(delay, deadline, cancel_event)
                finally:
                    result['emulated_wait_observed_seconds'] = time.perf_counter() - wait_started if delay else 0.0
            try:
                connection.send_bytes(payload)
            except (BrokenPipeError, OSError):
                raise _Stopped('disconnected') from None
            response = json.loads(_receive(connection, deadline, cancel_event))
            current = response['output']
            result['worker_compute_seconds'].append(response['compute_seconds'])
        result['max_abs_error'] = max(abs(a - b) for a, b in zip(current, reference))
        result['output_checksum'] = sum(current)
        result['status'] = 'ok'
    except _Stopped as stopped:
        result['status'] = str(stopped)
    finally:
        now = time.perf_counter()
        if 'startup_seconds' not in result:
            result['startup_seconds'] = now - startup_started
        result['inference_wall_seconds'] = now - inference_started if inference_started is not None else 0.0
        cleanup_started = time.perf_counter()
        for connection in connections:
            try:
                connection.send_bytes(b'')
            except (BrokenPipeError, OSError):
                pass
            connection.close()
        forced = []
        for process in processes:
            process.join(.2)
            force = process.is_alive()
            forced.append(force)
            if force:
                process.terminate()
                process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
        result['cleanup_seconds'] = time.perf_counter() - cleanup_started
        result['worker_exitcodes'] = [process.exitcode for process in processes]
        result['worker_forced_termination'] = forced
        result['workers_cleaned_up'] = all(not process.is_alive() for process in processes)
        for process in processes:
            if not process.is_alive():
                process.close()
    return result
