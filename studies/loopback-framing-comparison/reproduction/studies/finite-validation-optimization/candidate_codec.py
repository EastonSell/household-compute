"""Bounded, source-only mesh protocol. No network, process, or model code."""
from dataclasses import dataclass
from enum import IntEnum
import math
import struct
import sys

# This study changes only the finite FP32 predicate; all codec work stays intact.
# A native cast is correct only when C float is IEEE binary32, little-endian.
# Unknown / big-endian hosts keep the original explicitly little-endian scan.
_NATIVE_FP32_LE = (sys.byteorder == 'little' and
                   getattr(float, '__getformat__', lambda _: 'unknown')('float')
                   == 'IEEE, little-endian')


def finite_scan(tensor):
    """Private study predicate for contiguous, whole-number-of-FP32 byte buffers.

    A memoryview avoids per-element singleton tuples. map avoids the Python
    generator frame; Python float objects and isfinite calls remain. This is a
    mechanism hypothesis, not evidence of speed or total allocation savings.
    """
    if _NATIVE_FP32_LE:
        return all(map(math.isfinite, memoryview(tensor).cast('f')))
    return all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', tensor))


MAGIC = b'CMTP'
VERSION = 1
HEADER = struct.Struct('>4sBBBB16sIIIIII16s')
MAX_U32 = 2**32 - 1
VOCAB = 49152
MAX_CONTEXT = 64
WIDTH = 576
MAX_PAYLOAD = 196612
MAX_FRAME = 64 + MAX_PAYLOAD

class Kind(IntEnum):
    HELLO = 1
    READY = 2
    PREFILL = 3
    DECODE = 4
    ACTIVATION_PREFILL = 5
    ACTIVATION_DECODE = 6
    ACTIVATION_RESULT = 7
    TOKEN = 8
    AUDIT = 9
    RESET = 10
    RESET_ACK = 11
    STOP = 12
    STOP_ACK = 13
    ERROR = 14

class Mode(IntEnum):
    TOKEN = 1
    AUDIT = 2

class ErrorCode(IntEnum):
    PROTOCOL = 1
    TIMEOUT = 2
    IO = 3
    EXECUTION = 4
    CANCELLED = 5

class ProtocolError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProtocolError(message)

@dataclass(frozen=True)
class Header:
    kind: Kind
    stage: int
    mode: Mode
    run_id: bytes
    epoch: int = 0
    sequence: int = 0
    prior: int = 0
    length: int = 0
    payload_length: int = 0

    def validate(self):
        require(type(self.kind) is Kind and type(self.mode) is Mode, 'invalid enum')
        require(type(self.stage) is int and self.stage in (0, 1), 'invalid stage')
        require(type(self.run_id) is bytes and len(self.run_id) == 16, 'invalid run id')
        for n in (self.epoch, self.sequence, self.prior, self.length, self.payload_length):
            require(type(n) is int and 0 <= n <= MAX_U32, 'invalid unsigned field')
        require(self.payload_length <= MAX_PAYLOAD, 'payload cap')
        k = self.kind
        if k in (Kind.PREFILL, Kind.DECODE, Kind.ACTIVATION_PREFILL,
                 Kind.ACTIVATION_DECODE, Kind.ACTIVATION_RESULT, Kind.TOKEN, Kind.AUDIT):
            require(self.sequence >= 1 and 1 <= self.length <= 64 and
                    self.prior + self.length <= 64, 'invalid compute metadata')
        if k in (Kind.PREFILL, Kind.ACTIVATION_PREFILL):
            require(self.prior == 0, 'prefill with cache')
        if k in (Kind.DECODE, Kind.ACTIVATION_DECODE):
            require(self.prior >= 1 and self.length == 1, 'invalid decode')
        if k in (Kind.PREFILL, Kind.DECODE, Kind.ACTIVATION_RESULT):
            require(self.stage == 0, 'wrong stage opcode')
        if k in (Kind.ACTIVATION_PREFILL, Kind.ACTIVATION_DECODE, Kind.TOKEN, Kind.AUDIT):
            require(self.stage == 1, 'wrong stage opcode')
        if k == Kind.TOKEN:
            require(self.mode == Mode.TOKEN, 'token in audit mode')
        if k == Kind.AUDIT:
            require(self.mode == Mode.AUDIT, 'audit in token mode')
        if k in (Kind.HELLO, Kind.READY):
            require((self.epoch, self.sequence, self.prior, self.length) == (0, 0, 0, 0), 'handshake metadata')
        if k in (Kind.RESET, Kind.RESET_ACK):
            require(self.epoch >= 1 and (self.sequence, self.prior, self.length) == (0, 0, 0), 'reset metadata')
        if k in (Kind.STOP, Kind.STOP_ACK):
            require(self.length == 0, 'stop metadata')
        expected = 0
        if k in (Kind.PREFILL, Kind.DECODE):
            expected = 4 * self.length
        elif k in (Kind.ACTIVATION_PREFILL, Kind.ACTIVATION_DECODE, Kind.ACTIVATION_RESULT):
            expected = 2304 * self.length
        elif k in (Kind.TOKEN, Kind.ERROR):
            expected = 4
        elif k == Kind.AUDIT:
            expected = MAX_PAYLOAD
        require(self.payload_length == expected, 'opcode payload length')
        return self

    def pack(self):
        self.validate()
        return HEADER.pack(MAGIC, VERSION, self.kind, self.stage, self.mode,
                           self.run_id, self.epoch, self.sequence, self.prior,
                           self.length, self.payload_length, 0, bytes(16))

    @classmethod
    def unpack(cls, data):
        require(len(data) == 64, 'header size')
        magic, version, k, stage, mode, rid, epoch, seq, prior, length, size, flags, reserved = HEADER.unpack(data)
        require(magic == MAGIC and version == VERSION, 'magic/version')
        require(flags == 0 and reserved == bytes(16), 'reserved field')
        try:
            return cls(Kind(k), stage, Mode(mode), rid, epoch, seq, prior, length, size).validate()
        except ValueError as exc:
            raise ProtocolError('invalid header: ' + str(exc)) from exc

@dataclass(frozen=True)
class Frame:
    header: Header
    payload: bytes = b''

    def validate(self):
        h = self.header.validate()
        require(type(self.payload) is bytes and len(self.payload) == h.payload_length, 'body size')
        k = h.kind
        if k in (Kind.PREFILL, Kind.DECODE, Kind.TOKEN, Kind.AUDIT):
            tokens = self.payload if k in (Kind.PREFILL, Kind.DECODE) else self.payload[:4]
            require(all(t[0] < VOCAB for t in struct.iter_unpack('>I', tokens)), 'token range')
        if k == Kind.ERROR:
            require(struct.unpack('>I', self.payload)[0] in set(ErrorCode), 'unknown error code')
        tensor = self.payload[4:] if k == Kind.AUDIT else self.payload
        if k in (Kind.ACTIVATION_PREFILL, Kind.ACTIVATION_DECODE, Kind.ACTIVATION_RESULT, Kind.AUDIT):
            require(finite_scan(tensor), 'nonfinite tensor')
        return self

    def pack(self):
        self.validate()
        return self.header.pack() + self.payload

class Session:
    """Validate the whole controller-relay transcript, one frame at a time.

    Commit global cache/sequence only after an accepted stage1 response. This
    does not execute models or establish worker cache contents. Any external
    execution/IO failure MUST call fail(); no recovery or rollback is offered.
    Handshake/reset/stop visit stage0 then stage1 in this fixed implementation.
    """
    def __init__(self, run_id, mode):
        require(type(run_id) is bytes and len(run_id) == 16 and type(mode) is Mode, 'identity')
        self.run_id, self.mode = run_id, mode
        self.state = 'hello0'
        self.epoch = self.sequence = self.cache = 0
        self.previous_token = None
        self.pending = None
        self.activation = None
        self.failure = None

    def fail(self, reason):
        if self.state != 'failed':
            self.failure = str(reason)[:160]
        self.state = 'failed'
        self.pending = self.activation = None

    def check_header(self, h, direction):
        try:
            self._check_header(h, direction)
        except (ProtocolError, ValueError) as exc:
            self.fail(exc)
            raise

    def _check_header(self, h, direction):
        h.validate()
        require(self.state not in ('failed', 'closed'), 'terminal session')
        require(direction in ('request', 'response'), 'direction')
        require(h.run_id == self.run_id and h.mode == self.mode, 'session identity')
        if h.kind == Kind.ERROR:
            # ERROR echoes the outstanding metadata, or the current idle state.
            if self.pending is not None:
                p = self.pending
                require((h.stage, h.epoch, h.sequence, h.prior, h.length) ==
                        (p.stage, p.epoch, p.sequence, p.prior, p.length), 'error metadata')
            else:
                require((h.epoch, h.sequence, h.prior, h.length) ==
                        (self.epoch, self.sequence, self.cache, 0), 'idle error metadata')
            return
        transitions = {
            'hello0': (Kind.HELLO, 0, 'request'), 'ready0': (Kind.READY, 0, 'response'),
            'hello1': (Kind.HELLO, 1, 'request'), 'ready1': (Kind.READY, 1, 'response'),
            'activation': (Kind.ACTIVATION_RESULT, 0, 'response'),
            'reply': (Kind.TOKEN if self.mode == Mode.TOKEN else Kind.AUDIT, 1, 'response'),
            'reset_ack0': (Kind.RESET_ACK, 0, 'response'), 'reset1': (Kind.RESET, 1, 'request'),
            'reset_ack1': (Kind.RESET_ACK, 1, 'response'),
            'stop_ack0': (Kind.STOP_ACK, 0, 'response'), 'stop1': (Kind.STOP, 1, 'request'),
            'stop_ack1': (Kind.STOP_ACK, 1, 'response'),
        }
        if self.state == 'idle':
            require(direction == 'request' and h.stage == 0, 'idle direction/stage')
            if h.kind == Kind.RESET:
                require(self.epoch < MAX_U32 and h.epoch == self.epoch + 1, 'reset epoch')
                return
            require((h.epoch, h.prior) == (self.epoch, self.cache), 'cache/epoch mismatch')
            if h.kind == Kind.STOP:
                require(h.sequence == self.sequence, 'stop sequence')
                return
            require(h.kind == (Kind.PREFILL if self.cache == 0 else Kind.DECODE), 'compute phase')
            require(self.sequence < MAX_U32 and h.sequence == self.sequence + 1, 'compute sequence')
            return
        if self.state == 'relay':
            p = self.pending
            expected = Kind.ACTIVATION_PREFILL if p.prior == 0 else Kind.ACTIVATION_DECODE
            require((h.kind, h.stage, direction) == (expected, 1, 'request'), 'relay order')
        else:
            require((h.kind, h.stage, direction) == transitions[self.state], 'unexpected frame')
        if self.pending is not None:
            p = self.pending
            require((h.epoch, h.sequence, h.prior, h.length) ==
                    (p.epoch, p.sequence, p.prior, p.length), 'response/relay echo mismatch')

    def accept(self, frame, direction):
        try:
            self.check_header(frame.header, direction)
            frame.validate()
            h, k = frame.header, frame.header.kind
            if k == Kind.ERROR:
                self.fail('peer error ' + str(struct.unpack('>I', frame.payload)[0]))
                raise ProtocolError('terminal peer error')
            if k == Kind.DECODE:
                require(struct.unpack('>I', frame.payload)[0] == self.previous_token, 'broken greedy chain')
            if self.state == 'relay':
                require(frame.payload == self.activation, 'relay changed activation')
                self.activation = None
            old = self.state
            next_states = {'hello0': 'ready0', 'ready0': 'hello1', 'hello1': 'ready1',
                           'ready1': 'idle', 'activation': 'relay', 'relay': 'reply',
                           'reset_ack0': 'reset1', 'reset1': 'reset_ack1',
                           'reset_ack1': 'idle', 'stop_ack0': 'stop1',
                           'stop1': 'stop_ack1', 'stop_ack1': 'closed'}
            if old == 'idle':
                self.state = {Kind.RESET: 'reset_ack0', Kind.STOP: 'stop_ack0'}.get(k, 'activation')
                self.pending = h
            elif old == 'reply':
                self.epoch, self.sequence, self.cache = h.epoch, h.sequence, h.prior + h.length
                self.previous_token = struct.unpack('>I', frame.payload[:4])[0]
                self.pending = None
                self.state = 'idle'
            else:
                self.state = next_states[old]
                if old == 'activation':
                    self.activation = frame.payload
                if old in ('hello0', 'hello1', 'relay', 'reset1', 'stop1'):
                    self.pending = h
                if old in ('ready0', 'ready1', 'stop_ack1'):
                    self.pending = None
                if old == 'reset_ack1':
                    self.epoch, self.sequence, self.cache = h.epoch, 0, 0
                    self.pending = self.previous_token = None
        except (ProtocolError, ValueError) as exc:
            self.fail(exc)
            raise

class Decoder:
    """One bounded frame buffer. consume returns (consumed, frame-or-None).

    Caller retains coalesced surplus; no unbounded frame queue. Header gate is
    invoked before any body buffering. Feed the accepted frame to Session before
    consuming the next frame. EOF/deadline are terminal even at a frame boundary.
    """
    def __init__(self, gate=lambda h: None, on_failure=lambda reason: None):
        self.gate, self.on_failure = gate, on_failure
        self.buffer = bytearray()
        self.header = None
        self.failed = False

    def fail(self, reason):
        self.failed = True
        self.buffer.clear()
        self.header = None
        self.on_failure(reason)

    def consume(self, data):
        require(not self.failed, 'terminal decoder')
        used = 0
        try:
            view = memoryview(data)
            while used < len(view) or (self.header is not None and self.header.payload_length == 0):
                target = 64 if self.header is None else 64 + self.header.payload_length
                count = min(target - len(self.buffer), len(view) - used)
                self.buffer.extend(view[used:used + count])
                used += count
                if len(self.buffer) < target:
                    return used, None
                if self.header is None:
                    self.header = Header.unpack(self.buffer)
                    self.gate(self.header)
                    if self.header.payload_length:
                        continue
                frame = Frame(self.header, bytes(self.buffer[64:])).validate()
                self.buffer.clear()
                self.header = None
                return used, frame
            return used, None
        except (ProtocolError, ValueError) as exc:
            self.fail(exc)
            raise

    def eof(self):
        self.fail('EOF')
        raise ProtocolError('EOF')

class Ledger:
    """Positive actual transfer counts, by directed link and frame disposition.

    send and recv are separate evidence. delivered_total counts only recv, not
    send+recv. Classification must occur after the full operation commits (or
    fails), not merely after a single frame finishes. Fixed four directed links.
    """
    LINKS = ('c0', '0c', 'c1', '1c')
    def __init__(self):
        self.counts = {(link, event, category): 0 for link in self.LINKS
                       for event in ('send', 'recv')
                       for category in ('pending', 'inference', 'lifecycle', 'failed')}

    def record(self, link, event, actual):
        require(link in self.LINKS and event in ('send', 'recv'), 'counter identity')
        require(type(actual) is int and actual > 0, 'positive transfer required')
        self.counts[link, event, 'pending'] += actual

    def settle(self, category):
        require(category in ('inference', 'lifecycle', 'failed'), 'counter category')
        for link in self.LINKS:
            for event in ('send', 'recv'):
                key = (link, event, 'pending')
                self.counts[link, event, category] += self.counts[key]
                self.counts[key] = 0

    def delivered_total(self, category):
        return sum(self.counts[link, 'recv', category] for link in self.LINKS)

    def reconcile(self):
        require(not any(v for (l, e, c), v in self.counts.items() if c == 'pending'), 'unsettled bytes')
        for link in self.LINKS:
            for category in ('inference', 'lifecycle', 'failed'):
                require(self.counts[link, 'send', category] == self.counts[link, 'recv', category], 'unreconciled stream')


def check_deadline(clock, deadline):
    require(math.isfinite(deadline) and clock() < deadline, 'deadline expired')


def read_frame(read, decoder, ledger, link, clock, deadline):
    """Pure callback adapter; read(n, absolute_deadline) must return <= n bytes.

    A blocking callback cannot be interrupted by this module. Real transport
    MUST enforce that same absolute deadline and cancellation while blocked.
    """
    try:
        while True:
            check_deadline(clock, deadline)
            remaining = (64 if decoder.header is None else 64 + decoder.header.payload_length) - len(decoder.buffer)
            data = read(remaining, deadline)
            require(type(data) is bytes and len(data) <= remaining, 'read contract')
            if data:
                ledger.record(link, 'recv', len(data))
            check_deadline(clock, deadline)
            if not data:
                decoder.eof()
            consumed, frame = decoder.consume(data)
            check_deadline(clock, deadline)
            require(consumed == len(data), 'unexpected surplus')
            if frame is not None:
                return frame
    except Exception as exc:
        decoder.fail(exc)
        ledger.settle('failed')
        raise


def write_frame(write, frame, ledger, link, clock, deadline, on_failure):
    """write(view, absolute_deadline) returns positive actual accepted bytes."""
    try:
        check_deadline(clock, deadline)
        data = frame.pack()
        position = 0
        while position < len(data):
            check_deadline(clock, deadline)
            n = write(memoryview(data)[position:], deadline)
            require(type(n) is int and 0 < n <= len(data) - position, 'write contract')
            ledger.record(link, 'send', n)
            position += n
            check_deadline(clock, deadline)
    except Exception as exc:
        on_failure(exc)
        ledger.settle('failed')
        raise
