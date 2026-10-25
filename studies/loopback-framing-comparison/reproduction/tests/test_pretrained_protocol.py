import struct
import unittest

from mesh.pretrained_protocol import encode_frame, decode_frame, validate_tokens


class ProtocolTests(unittest.TestCase):
    def test_float32_frame_roundtrip(self):
        payload = struct.pack('<4f', 1, 2, 3, 4)
        frame = encode_frame([1, 4], payload)
        shape, restored = decode_frame(frame)
        self.assertEqual(shape, [1, 4])
        self.assertEqual(restored, payload)

    def test_rejects_truncated_or_mismatched_payload(self):
        frame = encode_frame([1, 2], struct.pack('<2f', 1, 2))
        for malformed in [b'', frame[:-1], frame + b'x']:
            with self.assertRaises(ValueError):
                decode_frame(malformed)
        with self.assertRaises(ValueError):
            encode_frame([1, 3], struct.pack('<2f', 1, 2))

    def test_shape_limits(self):
        for shape in [[], [0], [True], [1, 1, 1, 1], [1000000]]:
            with self.assertRaises(ValueError):
                encode_frame(shape, b'')

    def test_token_bounds_and_no_padding_or_cache_interface(self):
        self.assertEqual(validate_tokens([1, 42, 49151]), [1, 42, 49151])
        for tokens in [[], [True], [-1], [49152], [1] * 65, [[1]]]:
            with self.assertRaises(ValueError):
                validate_tokens(tokens)


if __name__ == '__main__':
    unittest.main()
