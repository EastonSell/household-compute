"""Scripted sockets, waits, and children only. Never opens sockets or processes."""
import errno
import subprocess
import unittest
from unittest.mock import patch
import deadline_adapter as a


class Clock:
    def __init__(self, values=(0,)):
        self.values = iter(values)
        self.last = 0
    def __call__(self):
        self.last = next(self.values, self.last)
        return self.last


class FakeSocket:
    def __init__(self, reads=(), writes=(), connects=0, peer=('127.0.0.1', 12345)):
        self.reads = iter(reads)
        self.writes = iter(writes)
        self.blocking = None
        self.connects = connects
        self.peer = peer
    def setblocking(self, value): self.blocking = value
    def recv(self, n):
        result = next(self.reads)
        if isinstance(result, BaseException): raise result
        if len(result) > n: raise AssertionError('test script violates recv bound')
        return result
    def send(self, view):
        result = next(self.writes, len(view))
        if isinstance(result, BaseException): raise result
        return result
    def connect_ex(self, target):
        self.target = target
        return self.connects
    def getsockopt(self, *args): return 0
    def getpeername(self): return self.peer
    def accept(self):
        result = next(self.reads)
        if isinstance(result, BaseException): raise result
        return result


class FakeChild:
    pid = 123456789
    def __init__(self, waits):
        self.waits = iter(waits)
        self.returncode = None
        self.signals = []
    def poll(self): return self.returncode
    def wait(self, timeout):
        value = next(self.waits)
        if value == 'timeout': raise subprocess.TimeoutExpired('fake-owned-child', timeout)
        self.returncode = value
        return value
    def terminate(self):
        if self.returncode is not None: raise AssertionError('signal after reap')
        self.signals.append('terminate')
    def kill(self):
        if self.returncode is not None: raise AssertionError('signal after reap')
        self.signals.append('kill')


class AdapterTests(unittest.TestCase):
    def test_partial_send_and_recv_account_actual_bytes(self):
        io = a.SocketIO(FakeSocket([b'a', b'bc'], [1, 2]), clock=Clock())
        io.send_all(b'abc', 1)
        self.assertEqual(io.read_exact(3, 1), b'abc')
        self.assertEqual((io.sent, io.received), (3, 3))
        self.assertIs(io.sock.blocking, False)

    def test_would_block_and_interrupt_keep_deadline(self):
        waits = []
        def wait(r, w, x, timeout):
            waits.append(timeout)
            return r, w, []
        io = a.SocketIO(FakeSocket([BlockingIOError(), InterruptedError(), b'x']),
                        clock=Clock(), select_fn=wait)
        self.assertEqual(io.read_exact(1, 0.03), b'x')
        self.assertEqual(waits, [0.03])

    def test_readiness_does_not_extend_expired_deadline(self):
        io = a.SocketIO(FakeSocket([BlockingIOError(), b'x']),
                        clock=Clock([0, 0, 2, 2]), select_fn=lambda *x: ([], [], []))
        with self.assertRaises(a.DeadlineError): io.read_exact(1, 1)
        self.assertEqual(io.received, 0)

    def test_backward_and_nonfinite_clocks_rejected(self):
        for vals in ([1, 0], [float('nan')], [float('inf')]):
            io = a.SocketIO(FakeSocket([b'x']), clock=Clock(vals))
            with self.assertRaises(a.DeadlineError): io.read_exact(1, 3)

    def test_late_successful_syscall_retains_actual_bytes(self):
        io=a.SocketIO(FakeSocket([b'x']),clock=Clock([0,2]))
        with self.assertRaises(a.DeadlineError):io.read_exact(1,1)
        self.assertEqual(io.received,1)
        io=a.SocketIO(FakeSocket(writes=[1]),clock=Clock([0,2]))
        with self.assertRaises(a.DeadlineError):io.send_all(b'x',1)
        self.assertEqual(io.sent,1)

    def test_cleanup_exhaustion_retains_attempted_signals_and_unreaped_state(self):
        child=FakeChild(['timeout','timeout','timeout'])
        with self.assertRaises(a.CleanupError) as caught:a.cleanup_child(child,10,clock=Clock())
        self.assertEqual(caught.exception.result,{'pid':123456789,'returncode':None,
            'terminated':True,'killed':True,'reaped':False})
        self.assertEqual(child.signals,['terminate','kill'])

    def test_eof_and_zero_write_are_terminal(self):
        with self.assertRaises(EOFError):
            a.SocketIO(FakeSocket([b'']), clock=Clock()).read_exact(1, 1)
        with self.assertRaises(OSError):
            a.SocketIO(FakeSocket(writes=[0]), clock=Clock()).send_all(b'x', 1)

    def test_forbids_nonloopback_and_bad_ports_before_connect(self):
        for target in [('localhost', 9), ('0.0.0.0', 9), ('127.0.0.2', 9),
                       ('127.0.0.1', 0), ('127.0.0.1', True), ('127.0.0.1', 65536)]:
            with self.assertRaises(ValueError):
                a.connect(FakeSocket(), target, 1, clock=Clock())

    def test_connect_in_progress_and_refused(self):
        io = a.connect(FakeSocket(connects=errno.EINPROGRESS), ('127.0.0.1', 12345),
                       1, clock=Clock(), select_fn=lambda r,w,x,t:(r,w,[]))
        self.assertEqual(io.sock.target, ('127.0.0.1', 12345))
        with self.assertRaises(OSError):
            a.connect(FakeSocket(connects=errno.ECONNREFUSED), ('127.0.0.1', 12345), 1, clock=Clock())

    def test_accept_rejects_nonloopback_peer(self):
        child = FakeSocket()
        with self.assertRaises(ValueError):
            a.accept(FakeSocket([(child, ('192.0.2.1', 9))]), 1, clock=Clock())

    def test_clean_child_is_reaped_without_signals(self):
        child = FakeChild([0])
        result = a.cleanup_child(child, 10, clock=Clock())
        self.assertEqual(child.signals, [])
        self.assertEqual(result, {'pid': 123456789, 'returncode': 0, 'terminated': False,
                                  'killed': False, 'reaped': True})

    def test_escalation_only_targets_same_owned_child(self):
        child = FakeChild(['timeout', 'timeout', -9])
        result = a.cleanup_child(child, 10, clock=Clock())
        self.assertEqual(child.signals, ['terminate', 'kill'])
        self.assertEqual(result['returncode'], -9)
        self.assertTrue(result['reaped'])

    def test_expired_cleanup_never_claims_reaped(self):
        with self.assertRaises(a.DeadlineError):
            a.cleanup_child(FakeChild(['timeout']), 0, clock=Clock())

    def test_already_reaped_child_not_signaled(self):
        child = FakeChild([])
        child.returncode = 4
        result = a.cleanup_child(child, 10, clock=Clock())
        self.assertEqual(result['returncode'], 4)
        self.assertEqual(child.signals, [])


if __name__ == '__main__': unittest.main()
