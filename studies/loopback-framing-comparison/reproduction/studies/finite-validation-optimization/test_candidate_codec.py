"""Untimed correctness gates; no benchmark clocks or allocation measurements."""
import importlib.util
from pathlib import Path
import random
import struct
import sys
import unittest
from unittest import mock

import candidate_codec as candidate

ROOT = Path(__file__).resolve().parent

def load_baseline():
    spec = importlib.util.spec_from_file_location('finite_validation_baseline', ROOT.parent / 'tcp-framing-codec' / 'mesh_codec.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

baseline = load_baseline()

class FiniteScanTests(unittest.TestCase):
    def test_accepts_little_endian_finite_boundaries_unchanged(self):
        # Catches swapping native endian or rejecting zero/subnormal/extreme finite.
        words = (0, 0x80000000, 1, 0x80000001, 0x007fffff, 0x807fffff,
                 0x00800000, 0x80800000, 0x3f800000, 0xbf800000,
                 0x7f7fffff, 0xff7fffff, 0x0000807f, 0x000080ff)
        payload = b''.join(word.to_bytes(4, 'little') for word in words)
        before = bytes(payload)
        self.assertIs(candidate.finite_scan(payload), True)
        self.assertEqual(payload, before)
        self.assertIs(candidate.finite_scan(b''), True)

    def test_rejects_signed_infinity_signaling_and_quiet_nan(self):
        # Catches testing only NaN or only infinity, or inspecting wrong byte order.
        words = (0x7f800000, 0xff800000, 0x7f800001, 0xff800001,
                 0x7fbfffff, 0xffbfffff, 0x7fc00000, 0xffc00000,
                 0x7fffffff, 0xffffffff)
        for word in words:
            for index in (0, 7, 15):
                payload = bytearray(struct.pack('<16f', *range(16)))
                payload[4*index:4*index+4] = word.to_bytes(4, 'little')
                with self.subTest(word=hex(word), index=index):
                    self.assertIs(candidate.finite_scan(bytes(payload)), False)

    def test_classifies_every_upper_halfword_with_boundary_lower_halfwords(self):
        # Independent IEEE exponent oracle: every sign/exponent/top-mantissa bit.
        for upper in range(65536):
            expected = (upper & 0x7f80) != 0x7f80
            for lower in (0, 1, 0x7fff, 0xffff):
                word = (upper << 16) | lower
                self.assertIs(candidate.finite_scan(word.to_bytes(4, 'little')), expected,
                              'wrong classification for 0x%08x' % word)

    def test_fallback_classifies_every_upper_halfword(self):
        with mock.patch.object(candidate, '_NATIVE_FP32_LE', False):
            for upper in range(65536):
                expected = (upper & 0x7f80) != 0x7f80
                for lower in (0, 1, 0x7fff, 0xffff):
                    word = (upper << 16) | lower
                    self.assertIs(candidate.finite_scan(word.to_bytes(4, 'little')), expected)

    def test_seeded_full_width_patterns_match_independent_exponent_oracle(self):
        rng = random.Random(202610250731)
        for _ in range(4096):
            word = rng.getrandbits(32)
            self.assertIs(candidate.finite_scan(word.to_bytes(4, 'little')),
                          (word & 0x7f800000) != 0x7f800000)

    def test_portable_fallback_uses_little_endian_wire_format(self):
        # Forcing the fallback on this host is not execution on big-endian hardware.
        with mock.patch.object(candidate, '_NATIVE_FP32_LE', False):
            for word, expected in ((0x7f800000, False), (0x0000807f, True),
                                   (0xff800000, False), (0x000080ff, True),
                                   (0x00000001, True), (0x80000000, True)):
                self.assertIs(candidate.finite_scan(word.to_bytes(4, 'little')), expected)


class CodecParityTests(unittest.TestCase):
    def activation(self, module, payload=None, length=1):
        if payload is None:
            words = (0, 0x80000000, 1, 0x80000001, 0x007fffff, 0x807fffff,
                     0x00800000, 0x80800000, 0x3f800000, 0xbf800000,
                     0x7f7fffff, 0xff7fffff, 0x0000807f, 0x000080ff)
            payload = b''.join(words[i % len(words)].to_bytes(4, 'little') for i in range(576*length))
        return module.Frame(module.Header(module.Kind.ACTIVATION_RESULT, 0,
                            module.Mode.TOKEN, bytes(range(16)), sequence=1,
                            length=length, payload_length=len(payload)), payload)

    def normalize(self, frame):
        if frame is None:
            return None
        return dict(vars(frame.header)), frame.payload

    def outcome(self, module, chunks):
        decoder = module.Decoder()
        trace = []
        for chunk in chunks:
            try:
                consumed, frame = decoder.consume(chunk)
                trace.append(('accepted', consumed, self.normalize(frame), bytes(decoder.buffer)))
            except Exception as exc:
                trace.append(('rejected', type(exc).__name__, str(exc),
                              decoder.failed, bytes(decoder.buffer), decoder.header))
                break
        return trace

    def test_all_original_contract_tests_run_unchanged_on_candidate(self):
        # Reuses tests for state, deadlines, malformed headers, I/O counts, and caps.
        import io
        spec = importlib.util.spec_from_file_location('candidate_original_contract_tests',
                         ROOT.parent / 'tcp-framing-codec' / 'test_mesh_codec.py')
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {'mesh_codec': candidate}):
            spec.loader.exec_module(module)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        output = io.StringIO()
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
        self.assertEqual(result.testsRun, 34)
        self.assertTrue(result.wasSuccessful(), output.getvalue())

    def test_exact_pack_decode_and_original_payload_object_preserved(self):
        for length in (1, 16, 64):
            original = self.activation(baseline, length=length)
            improved = self.activation(candidate, original.payload, length)
            self.assertEqual(original.pack(), improved.pack())
            self.assertIs(improved.validate(), improved)
            self.assertIs(improved.payload, original.payload)
            self.assertEqual(self.normalize(candidate.Decoder().consume(original.pack())[1]),
                             self.normalize(original))
        tensor = self.activation(baseline).payload
        payload = (49151).to_bytes(4, 'big') + (tensor * 86)[:196608]
        # All audit tensor words, including sign/zero/subnormals, remain bit-identical.
        wires = []
        for module in (baseline, candidate):
            frame = module.Frame(module.Header(module.Kind.AUDIT, 1, module.Mode.AUDIT,
                                 bytes(range(16)), sequence=1, length=1,
                                 payload_length=196612), payload)
            wires.append(frame.pack())
            self.assertEqual(module.Decoder().consume(wires[-1])[1].payload, payload)
        self.assertEqual(wires[0], wires[1])

    def test_every_activation_split_and_coalesced_surplus_matches_baseline(self):
        raw = self.activation(baseline).pack()
        for split in range(len(raw) + 1):
            chunks = [raw[:split], raw[split:]]
            self.assertEqual(self.outcome(candidate, chunks), self.outcome(baseline, chunks))
        coalesced = raw + raw
        for module in (baseline, candidate):
            decoder = module.Decoder()
            count, frame = decoder.consume(coalesced)
            self.assertEqual(count, len(raw))
            self.assertEqual(frame.pack(), raw)
            self.assertEqual(decoder.consume(coalesced[count:])[0], len(raw))
            self.assertFalse(decoder.buffer)

    def test_bytewise_activation_delivery_matches_baseline(self):
        raw = self.activation(baseline).pack()
        chunks = [raw[i:i+1] for i in range(len(raw))]
        self.assertEqual(self.outcome(candidate, chunks), self.outcome(baseline, chunks))

    def test_nonfinite_at_first_middle_last_activation_and_audit_positions(self):
        words = (0x7f800000, 0xff800000, 0x7f800001, 0xff800001,
                 0x7fc00000, 0xffc00000, 0x7fffffff, 0xffffffff)
        for audit, count in ((False, 576), (True, 49152)):
            for index in (0, count//2, count-1):
                for word in words:
                    payload = bytearray(bytes(4*count))
                    payload[4*index:4*index+4] = word.to_bytes(4, 'little')
                    if audit:
                        payload = bytes(4) + payload
                    raw = []
                    for module in (baseline, candidate):
                        if audit:
                            header = module.Header(module.Kind.AUDIT, 1, module.Mode.AUDIT,
                                          bytes(range(16)), sequence=1, length=1, payload_length=len(payload))
                        else:
                            header = self.activation(module).header
                        frame = module.Frame(header, bytes(payload))
                        with self.assertRaisesRegex(module.ProtocolError, '^nonfinite tensor$'):
                            frame.pack()
                        raw.append(header.pack() + bytes(payload))
                    self.assertEqual(raw[0], raw[1])
                    self.assertEqual(self.outcome(candidate, [raw[0][:65], raw[0][65:]]),
                                     self.outcome(baseline, [raw[0][:65], raw[0][65:]]))

    def test_header_rejection_and_terminal_state_match_baseline(self):
        raw = self.activation(baseline).pack()
        mutations = ((0,b'BAD!'), (4,b'\x02'), (5,b'\xff'), (6,b'\x02'),
                     (7,b'\xff'), (32,b'\xff'*4), (28,bytes(4)),
                     (36,(65).to_bytes(4,'big')), (40,(196613).to_bytes(4,'big')),
                     (40,(2305).to_bytes(4,'big')), (44,b'\x01'), (48,b'\x01'))
        for offset, value in mutations:
            bad = bytearray(raw)
            bad[offset:offset+len(value)] = value
            expected = self.outcome(baseline, [bytes(bad)])
            self.assertEqual(expected[0][0], 'rejected')
            self.assertEqual(self.outcome(candidate, [bytes(bad)]), expected)
        for truncated in (0,1,63,64,65,len(raw)-1):
            states = []
            for module in (baseline,candidate):
                decoder = module.Decoder()
                decoder.consume(raw[:truncated])
                with self.assertRaisesRegex(module.ProtocolError, '^EOF$'):
                    decoder.eof()
                with self.assertRaisesRegex(module.ProtocolError, '^terminal decoder$'):
                    decoder.consume(raw)
                states.append((decoder.failed, bytes(decoder.buffer), decoder.header))
            self.assertEqual(states[0], states[1])

    def test_body_type_size_token_and_error_rejection_match_baseline(self):
        for payload in (b'', b'\x00', bytes(2303), bytes(2305), bytearray(2304), memoryview(bytes(2304))):
            errors = []
            for module in (baseline, candidate):
                frame = module.Frame(self.activation(module).header, payload)
                with self.assertRaises(module.ProtocolError) as caught:
                    frame.pack()
                errors.append(str(caught.exception))
            self.assertEqual(errors, ['body size','body size'])
        for kind,stage,mode,payload in ((8,1,1,(49152).to_bytes(4,'big')),
                                       (9,1,2,(49152).to_bytes(4,'big')+bytes(196608)),
                                       (14,0,1,(99).to_bytes(4,'big'))):
            outcomes=[]
            for module in (baseline,candidate):
                header=module.Header(module.Kind(kind),stage,module.Mode(mode),bytes(range(16)),
                                     sequence=1,length=1,payload_length=len(payload))
                outcomes.append(self.outcome(module,[header.pack()+payload]))
            self.assertEqual(outcomes[0],outcomes[1])
            self.assertEqual(outcomes[0][0][0],'rejected')


if __name__ == '__main__':
    unittest.main()
