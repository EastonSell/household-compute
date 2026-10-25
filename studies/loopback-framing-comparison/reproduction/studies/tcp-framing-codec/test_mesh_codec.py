import dataclasses
import struct
import unittest
from mesh_codec import *

RID = bytes(range(16))

def frame(k, stage=0, mode=Mode.TOKEN, epoch=0, sequence=0, prior=0, length=0, payload=b''):
    return Frame(Header(k, stage, mode, RID, epoch, sequence, prior, length, len(payload)), payload)

def ready(mode=Mode.TOKEN):
    s = Session(RID, mode)
    for stage in (0, 1):
        s.accept(frame(Kind.HELLO, stage, mode), 'request')
        s.accept(frame(Kind.READY, stage, mode), 'response')
    return s

def operation(s, length=1, token=7):
    prior, seq = s.cache, s.sequence + 1
    data = struct.pack('>I', s.previous_token if prior else 1) * length
    common = dict(mode=s.mode, epoch=s.epoch, sequence=seq, prior=prior, length=length)
    frames = [frame(Kind.DECODE if prior else Kind.PREFILL, payload=data, **common),
              frame(Kind.ACTIVATION_RESULT, payload=bytes(2304 * length), **common),
              frame(Kind.ACTIVATION_DECODE if prior else Kind.ACTIVATION_PREFILL,
                    stage=1, payload=bytes(2304 * length), **common),
              frame(Kind.TOKEN if s.mode == Mode.TOKEN else Kind.AUDIT, stage=1,
                    payload=struct.pack('>I', token) + (bytes(196608) if s.mode == Mode.AUDIT else b''), **common)]
    for f, d in zip(frames, ('request', 'response', 'request', 'response')):
        s.accept(f, d)
    return frames

class CodecTests(unittest.TestCase):
    def test_header_layout(self):
        f = frame(Kind.PREFILL, sequence=1, length=1, payload=struct.pack('>I', 42))
        b = f.pack()
        self.assertEqual(HEADER.size, 64)
        self.assertEqual(b[:8], b'CMTP\x01\x03\x00\x01')
        self.assertEqual(b[8:24], RID)
        self.assertEqual(b[24:48], struct.pack('>6I', 0, 1, 0, 1, 4, 0))
        self.assertEqual(b[48:64], bytes(16))
        self.assertEqual(Header.unpack(b[:64]), f.header)

    def test_all_byte_fragmentation(self):
        f = frame(Kind.ACTIVATION_RESULT, sequence=1, length=2, payload=bytes(4608))
        decoder = Decoder()
        for i, b in enumerate(f.pack()):
            count, got = decoder.consume(bytes([b]))
            self.assertEqual(count, 1)
            self.assertLessEqual(len(decoder.buffer), MAX_FRAME)
            self.assertEqual(got, f if i == len(f.pack()) - 1 else None)

    def test_coalesced_frames_not_queued(self):
        frames = [frame(Kind.HELLO), frame(Kind.HELLO, stage=1)]
        data = b''.join(f.pack() for f in frames)
        d = Decoder()
        n, got = d.consume(data)
        self.assertEqual((n, got), (64, frames[0]))
        self.assertEqual(len(d.buffer), 0)
        self.assertEqual(d.consume(data[n:]), (64, frames[1]))

    def test_each_split_position(self):
        f = frame(Kind.PREFILL, sequence=1, length=4, payload=struct.pack('>4I', 1, 2, 3, 4))
        for split in range(1, len(f.pack())):
            d = Decoder()
            self.assertEqual(d.consume(f.pack()[:split]), (split, None))
            self.assertEqual(d.consume(f.pack()[split:])[1], f)

    def test_bad_header_fields_before_body(self):
        original = frame(Kind.HELLO).pack()
        mutations = [(0, b'BAD!'), (4, b'\x02'), (5, b'\xff'), (6, b'\x02'),
                     (7, b'\xff'), (40, struct.pack('>I', MAX_PAYLOAD + 1)),
                     (40, struct.pack('>I', 1)), (44, b'\x01'), (48, b'\x01')]
        for offset, value in mutations:
            with self.subTest(offset=offset, value=value):
                data = bytearray(original)
                data[offset:offset+len(value)] = value
                d = Decoder()
                with self.assertRaises(ProtocolError):
                    d.consume(bytes(data) + b'unread body')
                self.assertTrue(d.failed)
                self.assertEqual(len(d.buffer), 0)

    def test_session_header_gate_precedes_body(self):
        s = ready()
        f = frame(Kind.PREFILL, sequence=2, length=64, payload=bytes(256))
        d = Decoder(lambda h: s.check_header(h, 'request'), s.fail)
        with self.assertRaises(ProtocolError):
            d.consume(f.pack()[:64])
        self.assertEqual(s.state, 'failed')
        self.assertEqual(len(d.buffer), 0)

    def test_short_header_and_body_eof(self):
        raw = frame(Kind.PREFILL, sequence=1, length=1, payload=bytes(4)).pack()
        for n in (0, 1, 63, 64, 66):
            d = Decoder()
            d.consume(raw[:n])
            with self.assertRaises(ProtocolError):
                d.eof()
            with self.assertRaises(ProtocolError):
                d.consume(raw)

    def test_invalid_tokens(self):
        for kind, stage, mode in ((Kind.PREFILL, 0, Mode.TOKEN), (Kind.TOKEN, 1, Mode.TOKEN), (Kind.AUDIT, 1, Mode.AUDIT)):
            payload = struct.pack('>I', VOCAB) + (bytes(196608) if kind == Kind.AUDIT else b'')
            with self.assertRaises(ProtocolError):
                frame(kind, stage, mode, sequence=1, length=1, payload=payload).pack()

    def test_nonfinite_tensors(self):
        for bad in (float('nan'), float('inf'), -float('inf')):
            for kind, mode, count in ((Kind.ACTIVATION_RESULT, Mode.TOKEN, 576), (Kind.AUDIT, Mode.AUDIT, VOCAB)):
                payload = struct.pack('<f', bad) + bytes(4 * (count - 1))
                if kind == Kind.AUDIT:
                    payload = bytes(4) + payload
                with self.assertRaises(ProtocolError):
                    frame(kind, int(kind == Kind.AUDIT), mode, sequence=1, length=1, payload=payload).pack()

    def test_mode_specific_reply(self):
        for k, mode, size in ((Kind.TOKEN, Mode.AUDIT, 4), (Kind.AUDIT, Mode.TOKEN, MAX_PAYLOAD)):
            with self.assertRaises(ProtocolError):
                frame(k, 1, mode, sequence=1, length=1, payload=bytes(size)).pack()

    def test_fixed_caps(self):
        f = frame(Kind.ACTIVATION_PREFILL, 1, sequence=1, length=64, payload=bytes(147456))
        self.assertEqual(len(f.pack()), 147520)
        with self.assertRaises(ProtocolError):
            dataclasses.replace(f, header=dataclasses.replace(f.header, length=65)).pack()
        a = frame(Kind.AUDIT, 1, Mode.AUDIT, sequence=1, length=1, payload=bytes(MAX_PAYLOAD))
        self.assertEqual(len(a.pack()), MAX_FRAME)

    def test_closed_error_enum(self):
        for code in ErrorCode:
            frame(Kind.ERROR, payload=struct.pack('>I', code)).validate()
        with self.assertRaises(ProtocolError):
            frame(Kind.ERROR, payload=struct.pack('>I', 99)).validate()

    def test_local_field_types_and_bounds(self):
        h = frame(Kind.HELLO).header
        for name, value in (('epoch', -1), ('sequence', MAX_U32 + 1), ('stage', True), ('mode', 1), ('kind', 1), ('run_id', b'x')):
            with self.assertRaises(ProtocolError):
                dataclasses.replace(h, **{name: value}).pack()

class StateTests(unittest.TestCase):
    def test_success_token_and_audit_chain(self):
        for mode in Mode:
            s = ready(mode)
            operation(s, 4)
            operation(s, token=9)
            self.assertEqual((s.state, s.sequence, s.cache, s.previous_token), ('idle', 2, 5, 9))

    def test_no_commit_before_final_reply(self):
        s = ready()
        frames = operation(ready(), 4)
        for f, d in zip(frames[:3], ('request', 'response', 'request')):
            s.accept(f, d)
            self.assertEqual((s.cache, s.sequence), (0, 0))
        s.accept(frames[3], 'response')
        self.assertEqual((s.cache, s.sequence), (4, 1))

    def test_duplicates_skips_stale(self):
        for seq in (1, 3):
            s = ready()
            operation(s)
            with self.assertRaises(ProtocolError):
                s.accept(frame(Kind.DECODE, sequence=seq, prior=1, length=1, payload=struct.pack('>I', 7)), 'request')
            self.assertEqual(s.state, 'failed')

    def test_wrong_cache_epoch_identity_direction(self):
        for change in ({'prior': 1}, {'epoch': 1}, {'run_id': b'x' * 16}, {'mode': Mode.AUDIT}, {'stage': 1}):
            s = ready()
            f = frame(Kind.PREFILL, sequence=1, length=1, payload=bytes(4))
            with self.assertRaises(ProtocolError):
                s.accept(dataclasses.replace(f, header=dataclasses.replace(f.header, **change)), 'request')
            self.assertEqual(s.state, 'failed')
        s = ready()
        with self.assertRaises(ProtocolError):
            s.accept(frame(Kind.STOP), 'response')

    def test_wrong_greedy_token(self):
        s = ready()
        operation(s)
        with self.assertRaises(ProtocolError):
            s.accept(frame(Kind.DECODE, sequence=2, prior=1, length=1, payload=bytes(4)), 'request')

    def test_relay_bytes_must_match(self):
        s = ready()
        frames = operation(ready())
        s.accept(frames[0], 'request')
        s.accept(frames[1], 'response')
        corrupt = dataclasses.replace(frames[2], payload=struct.pack('<f', 1.0) + bytes(2300))
        with self.assertRaises(ProtocolError):
            s.accept(corrupt, 'request')

    def test_reply_echo_and_kind(self):
        for change in ({'sequence': 2}, {'length': 2}, {'epoch': 1}, {'kind': Kind.ERROR}):
            s = ready()
            frames = operation(ready())
            for f, d in zip(frames[:3], ('request', 'response', 'request')):
                s.accept(f, d)
            with self.assertRaises(ProtocolError):
                s.accept(dataclasses.replace(frames[3], header=dataclasses.replace(frames[3].header, **change)), 'response')

    def test_reset_both_ack_required_and_replay(self):
        s = ready()
        original = operation(s, 4)
        for stage in (0, 1):
            s.accept(frame(Kind.RESET, stage, epoch=1), 'request')
            self.assertEqual((s.epoch, s.cache), (0, 4))
            s.accept(frame(Kind.RESET_ACK, stage, epoch=1), 'response')
        self.assertEqual((s.epoch, s.cache, s.sequence, s.previous_token), (1, 0, 0, None))
        replay = operation(s, 4)
        self.assertEqual([f.payload for f in original], [f.payload for f in replay])

    def test_second_reset_ack_failure(self):
        s = ready()
        for f, d in ((frame(Kind.RESET, epoch=1), 'request'), (frame(Kind.RESET_ACK, epoch=1), 'response'), (frame(Kind.RESET, 1, epoch=1), 'request')):
            s.accept(f, d)
        with self.assertRaises(ProtocolError):
            s.accept(frame(Kind.RESET_ACK, 1, epoch=2), 'response')
        with self.assertRaises(ProtocolError):
            s.accept(frame(Kind.RESET, epoch=1), 'request')

    def test_reset_during_operation(self):
        s = ready()
        s.accept(frame(Kind.PREFILL, sequence=1, length=1, payload=bytes(4)), 'request')
        with self.assertRaises(ProtocolError):
            s.accept(frame(Kind.RESET, epoch=1), 'request')

    def test_overflow_never_wraps(self):
        s = ready()
        s.sequence = MAX_U32
        with self.assertRaises(ProtocolError):
            s.accept(frame(Kind.PREFILL, sequence=1, length=1, payload=bytes(4)), 'request')
        s = ready()
        s.epoch = MAX_U32
        with self.assertRaises(ProtocolError):
            s.accept(frame(Kind.RESET, epoch=1), 'request')

    def test_stop_terminal(self):
        s = ready()
        operation(s)
        for stage in (0, 1):
            s.accept(frame(Kind.STOP, stage, sequence=1, prior=1), 'request')
            s.accept(frame(Kind.STOP_ACK, stage, sequence=1, prior=1), 'response')
        self.assertEqual(s.state, 'closed')
        with self.assertRaises(ProtocolError):
            s.accept(frame(Kind.HELLO), 'request')

    def test_error_and_external_failure_terminal(self):
        s = ready()
        with self.assertRaises(ProtocolError):
            s.accept(frame(Kind.ERROR, payload=struct.pack('>I', ErrorCode.IO)), 'response')
        self.assertEqual(s.state, 'failed')
        for reason in ('controller failure between stages', 'worker compute then truncated response', 'cancelled'):
            s = ready()
            s.fail(reason)
            with self.assertRaises(ProtocolError):
                s.accept(frame(Kind.HELLO), 'request')
            self.assertEqual(s.failure, reason)

class TransportTests(unittest.TestCase):
    def test_partial_write_read_counts(self):
        f = frame(Kind.PREFILL, sequence=1, length=4, payload=bytes(16))
        wire = bytearray()
        ledger = Ledger()
        def write(v, deadline):
            n = min(3, len(v))
            wire.extend(v[:n])
            return n
        write_frame(write, f, ledger, 'c0', lambda: 0, 1, lambda e: None)
        def read(n, deadline):
            n = min(n, 7, len(wire))
            data = bytes(wire[:n])
            del wire[:n]
            return data
        self.assertEqual(read_frame(read, Decoder(), ledger, 'c0', lambda: 0, 1), f)
        ledger.settle('inference')
        ledger.reconcile()
        self.assertEqual(ledger.delivered_total('inference'), len(f.pack()))

    def test_byte_forecasts(self):
        for mode in Mode:
            s = ready(mode)
            for length in (4, 1):
                frames = operation(s, length)
                ledger = Ledger()
                for link, f in zip(Ledger.LINKS, frames):
                    for event in ('send', 'recv'):
                        ledger.record(link, event, len(f.pack()))
                ledger.settle('inference')
                ledger.reconcile()
                expected = 4612 * length + 260 + (196608 if mode == Mode.AUDIT else 0)
                self.assertEqual(ledger.delivered_total('inference'), expected)

    def test_slow_drip_fixed_deadline(self):
        clock = [0.0]
        seen = []
        s = ready()
        wire = bytearray(frame(Kind.PREFILL, sequence=1, length=1, payload=bytes(4)).pack())
        def read(n, deadline):
            seen.append(deadline)
            clock[0] += 0.1
            return bytes([wire.pop(0)])
        ledger = Ledger()
        with self.assertRaises(ProtocolError):
            read_frame(read, Decoder(on_failure=s.fail), ledger, 'c0', lambda: clock[0], 6.6)
        self.assertEqual(set(seen), {6.6})
        self.assertEqual(s.state, 'failed')
        self.assertEqual(ledger.delivered_total('failed'), len(seen))
        self.assertGreater(len(seen), 64)  # expiry in body, not renewable at header

    def test_validation_crossing_deadline_is_terminal(self):
        for finish_time in (1.0, 2.0):
            with self.subTest(finish_time=finish_time):
                now = [0.0]
                session, ledger = Session(RID, Mode.TOKEN), Ledger()
                def gate(header):
                    session.check_header(header, 'request')
                    now[0] = finish_time
                decoder = Decoder(gate, session.fail)
                with self.assertRaisesRegex(ProtocolError, 'deadline expired'):
                    read_frame(lambda n, d: frame(Kind.HELLO).pack(), decoder,
                               ledger, 'c0', lambda: now[0], 1.0)
                self.assertTrue(decoder.failed)
                self.assertEqual(session.state, 'failed')
                self.assertEqual(ledger.delivered_total('failed'), 64)
                self.assertEqual(ledger.counts['c0', 'recv', 'pending'], 0)

    def test_partial_write_deadline_retains_actual(self):
        now = [0]
        s = ready()
        ledger = Ledger()
        def write(v, deadline):
            now[0] += 1
            return 1
        with self.assertRaises(ProtocolError):
            write_frame(write, frame(Kind.HELLO), ledger, 'c0', lambda: now[0], 3, s.fail)
        self.assertEqual(ledger.counts['c0', 'send', 'failed'], 3)
        self.assertEqual(s.state, 'failed')
        with self.assertRaises(ProtocolError):
            ledger.reconcile()

    def test_zero_write_and_eof_fail(self):
        for op in ('read', 'write'):
            s, ledger = ready(), Ledger()
            with self.assertRaises(ProtocolError):
                if op == 'read':
                    read_frame(lambda n, d: b'', Decoder(on_failure=s.fail), ledger, 'c0', lambda: 0, 1)
                else:
                    write_frame(lambda v, d: 0, frame(Kind.HELLO), ledger, 'c0', lambda: 0, 1, s.fail)
            self.assertEqual(s.state, 'failed')

    def test_io_exception_poison(self):
        def broken(*args):
            raise OSError('synthetic IO failure')
        for op in ('read', 'write'):
            s, ledger = ready(), Ledger()
            with self.assertRaises(OSError):
                if op == 'read':
                    read_frame(broken, Decoder(on_failure=s.fail), ledger, 'c0', lambda: 0, 1)
                else:
                    write_frame(broken, frame(Kind.HELLO), ledger, 'c0', lambda: 0, 1, s.fail)
            self.assertEqual(s.state, 'failed')

    def test_accounting_rejects_invalid_and_unsettled(self):
        ledger = Ledger()
        for n in (0, -1, True, 1.5):
            with self.assertRaises(ProtocolError):
                ledger.record('c0', 'send', n)
        ledger.record('c0', 'send', 1)
        with self.assertRaises(ProtocolError):
            ledger.reconcile()

if __name__ == '__main__':
    unittest.main(verbosity=2)
