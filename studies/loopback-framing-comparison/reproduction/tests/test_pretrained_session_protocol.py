"""Malformed local-worker responses must never leave a reusable session."""
import json
import struct
import unittest
from unittest.mock import patch

from mesh.pretrained_session import PretrainedSession
from mesh.pretrained_protocol import encode_frame


class PipeStub:
    def send_bytes(self, payload):
        pass

    def close(self):
        pass


class SessionProtocolTests(unittest.TestCase):
    def check_bad_reply(self, replies):
        session = PretrainedSession('unused', opt_in=True)
        session.connections = [PipeStub(), PipeStub()]
        with patch('mesh.pretrained_session._recv', side_effect=replies):
            result = session.forward([1, 42])
        self.assertEqual(result['status'], 'protocol_error')
        self.assertTrue(session.failed)
        with self.assertRaises(RuntimeError):
            session.forward([1, 42])
        session.close()
        self.assertTrue(session.cleanup['workers_cleaned_up'])

    def test_missing_report_fields_invalidate_session(self):
        self.check_bad_reply([b'{}'])

    def test_invalid_json_invalidates_session(self):
        self.check_bad_reply([b'not json'])

    def test_out_of_order_stage_report_invalidates_session(self):
        self.check_bad_reply([json.dumps({'stage': 1, 'request_id': 1, 'compute_seconds': .01, 'peak_rss_kib': 100}).encode()])

    def test_stale_request_report_invalidates_session(self):
        self.check_bad_reply([json.dumps({'stage': 0, 'request_id': 2, 'compute_seconds': .01, 'peak_rss_kib': 100}).encode()])

    def test_invalid_final_shape_invalidates_session(self):
        report0 = json.dumps({'stage': 0, 'request_id': 1, 'compute_seconds': .01, 'peak_rss_kib': 100}).encode()
        report1 = json.dumps({'stage': 1, 'request_id': 1, 'compute_seconds': .01, 'peak_rss_kib': 100}).encode()
        activation = encode_frame([1, 2, 576], b'\0' * (2 * 576 * 4))
        bad_logits = encode_frame([1, 1], struct.pack('<f', 0))
        self.check_bad_reply([report0, activation, report1, bad_logits])

    def test_nonfinite_metric_invalidates_session(self):
        self.check_bad_reply([json.dumps({'stage': 0, 'request_id': 1, 'compute_seconds': float('nan'), 'peak_rss_kib': 100}).encode()])

    def test_invalid_frame_invalidates_session(self):
        self.check_bad_reply([json.dumps({'stage': 0, 'request_id': 1, 'compute_seconds': .01, 'peak_rss_kib': 100}).encode(), b'bad frame'])


class OptionalResourceTests(unittest.TestCase):
    def test_module_imports_without_unix_resource(self):
        import importlib.util
        import sys
        from pathlib import Path
        import mesh.pretrained_session
        spec = importlib.util.spec_from_file_location('mesh._without_resource', Path(mesh.pretrained_session.__file__))
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'resource': None}):
            spec.loader.exec_module(module)
        self.assertIsNone(module._peak_rss_kib())


if __name__ == '__main__':
    unittest.main()
