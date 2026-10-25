"""Nonblocking loopback adapter and exclusive direct-child cleanup. Stdlib only."""
import errno
import math
import select
import socket
import subprocess
import time


class DeadlineError(TimeoutError):
    pass


class CleanupError(DeadlineError):
    def __init__(self, result, cause):
        super().__init__('owned-child cleanup failed')
        self.result = result
        self.cause_type = type(cause).__name__


class Budget:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.previous = None

    def remaining(self, deadline):
        now = self.clock()
        if (type(now) not in (int, float) or not math.isfinite(now) or
            type(deadline) not in (int, float) or not math.isfinite(deadline) or
            (self.previous is not None and now < self.previous) or now >= deadline):
            raise DeadlineError('invalid clock or expired absolute deadline')
        self.previous = now
        return deadline - now


class SocketIO:
    def __init__(self, sock, clock=time.monotonic, select_fn=select.select):
        self.sock = sock
        self.sock.setblocking(False)
        self.budget = Budget(clock)
        self.select = select_fn
        self.sent = self.received = 0

    def wait(self, reading, deadline):
        while True:
            timeout = min(0.05, self.budget.remaining(deadline))
            try:
                r, w, _ = self.select([self.sock] if reading else [],
                                      [] if reading else [self.sock], [], timeout)
            except InterruptedError:
                continue
            self.budget.remaining(deadline)
            if r or w:
                return

    def read(self, n, deadline):
        if type(n) is not int or not 1 <= n <= 196676:
            raise ValueError('invalid bounded read')
        while True:
            self.budget.remaining(deadline)
            try:
                data = self.sock.recv(n)
            except BlockingIOError:
                self.wait(True, deadline)
                continue
            except InterruptedError:
                continue
            if not data:
                raise EOFError('peer closed')
            if type(data) is not bytes or len(data) > n:
                raise OSError('read contract')
            self.received += len(data)
            self.budget.remaining(deadline)
            return data

    def write(self, view, deadline):
        if not 0 < len(view) <= 196676:
            raise ValueError('invalid bounded write')
        while True:
            self.budget.remaining(deadline)
            try:
                count = self.sock.send(view)
            except BlockingIOError:
                self.wait(False, deadline)
                continue
            except InterruptedError:
                continue
            if type(count) is not int or not 0 < count <= len(view):
                raise OSError('write contract')
            self.sent += count
            self.budget.remaining(deadline)
            return count

    def read_exact(self, n, deadline):
        if type(n) is not int or not 1 <= n <= 196676:
            raise ValueError('invalid exact read')
        chunks = bytearray()
        while len(chunks) < n:
            chunks.extend(self.read(n - len(chunks), deadline))
        return bytes(chunks)

    def send_all(self, data, deadline):
        if not 0 < len(data) <= 196676:
            raise ValueError('invalid exact write')
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            offset += self.write(view[offset:], deadline)


def validate_address(target):
    if (type(target) is not tuple or len(target) != 2 or target[0] != '127.0.0.1' or
        type(target[1]) is not int or not 1 <= target[1] <= 65535):
        raise ValueError('only literal IPv4 loopback and nonzero port permitted')


def connect(sock, target, deadline, clock=time.monotonic, select_fn=select.select):
    validate_address(target)
    io = SocketIO(sock, clock, select_fn)
    io.budget.remaining(deadline)
    error = sock.connect_ex(target)
    if error in (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK, errno.EINTR):
        io.wait(False, deadline)
        error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    io.budget.remaining(deadline)
    if error != 0:
        raise OSError(error, 'loopback connect failed')
    validate_address(sock.getpeername())
    return io


def accept(listener, deadline, clock=time.monotonic, select_fn=select.select):
    io = SocketIO(listener, clock, select_fn)
    while True:
        io.budget.remaining(deadline)
        try:
            conn, peer = listener.accept()
        except BlockingIOError:
            io.wait(True, deadline)
            continue
        except InterruptedError:
            continue
        try:
            io.budget.remaining(deadline)
            validate_address(peer)
        except BaseException:
            close = getattr(conn, 'close', None)
            if close is not None:
                close()
            raise
        return SocketIO(conn, clock, select_fn)


def cleanup_child(child, deadline, clock=time.monotonic):
    """Only call with the Popen object this driver created and exclusively reaps.

    No other thread/reaper may touch it. Popen handles its own wait/kill identity
    guard; never issue naked PID signals or process-group operations here.
    """
    result = {'pid': child.pid, 'returncode': None, 'terminated': False,
              'killed': False, 'reaped': False}
    budget = Budget(clock)
    try:
        for action in (None, 'terminate', 'kill'):
            code = child.poll()
            if code is not None:
                result.update(returncode=code, reaped=True)
                return result
            budget.remaining(deadline)
            if action is not None:
                result['terminated' if action == 'terminate' else 'killed'] = True
                getattr(child, action)()
            try:
                code = child.wait(timeout=min(1.0, budget.remaining(deadline)))
            except subprocess.TimeoutExpired:
                continue
            result.update(returncode=code, reaped=True)
            return result
        raise DeadlineError('owned child not reaped within cleanup reserve')
    except BaseException as exc:
        raise CleanupError(result, exc) from exc
