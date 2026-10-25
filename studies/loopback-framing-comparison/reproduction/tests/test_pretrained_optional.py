"""Opt-in real-weight integration tests; skipped without MESH_MODEL_DIR."""
import os
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('MESH_MODEL_DIR'), 'set MESH_MODEL_DIR with optional pinned runtime to test real weights')
class PretrainedTests(unittest.TestCase):
    def test_failed_experiment_keeps_cleanup_and_failure_evidence(self):
        from mesh.pretrained_experiment import run
        with patch('mesh.pretrained_experiment.PretrainedSession.forward', return_value={'status': 'protocol_error'}):
            result = run(os.environ['MESH_MODEL_DIR'], opt_in=True, repeats=2)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['phase'], 'correctness_gate')
        self.assertIn('protocol_error', result['failure']['reason'])
        self.assertTrue(result['cleanup']['workers_cleaned_up'])
        self.assertIn('correctness_gate', result)
        self.assertIn('cases', result)

    def test_private_pipe_workers_match_and_exit(self):
        import torch
        from mesh.pretrained_model import load_reference
        from mesh.pretrained_session import PretrainedSession
        directory = os.environ['MESH_MODEL_DIR']
        torch.set_num_threads(1)
        model = load_reference(directory)
        ids = torch.tensor([[1, 42, 314, 7]])
        with torch.inference_mode():
            expected = model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False, num_logits_to_keep=1).logits[:, -1, :]
            with PretrainedSession(directory, opt_in=True) as session:
                result = session.forward(ids[0].tolist())
                self.assertEqual(result['status'], 'ok')
                torch.testing.assert_close(result['logits'], expected, rtol=1e-4, atol=1e-4)
                self.assertEqual(result['logits'].argmax(-1).item(), expected.argmax(-1).item())
        self.assertTrue(session.cleanup['workers_cleaned_up'])
        self.assertEqual(session.cleanup['worker_exitcodes'], [0, 0])

    def test_real_partitions_match_monolithic_last_token_logits(self):
        import torch
        from mesh.pretrained_model import Partition, load_reference, verify_model
        directory = os.environ['MESH_MODEL_DIR']
        verify_model(directory)
        torch.set_num_threads(1)
        model = load_reference(directory)
        first, second = Partition(directory, 0), Partition(directory, 1)
        with torch.inference_mode():
            for tokens in [[1], [1, 42, 314, 7], [1, 14, 77, 123, 9, 41, 256, 78]]:
                ids = torch.tensor([tokens])
                expected = model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False).logits[:, -1, :]
                actual = second(first(ids))
                torch.testing.assert_close(actual, expected, rtol=1e-4, atol=1e-4)
                self.assertEqual(actual.argmax(-1).item(), expected.argmax(-1).item())


if __name__ == '__main__':
    unittest.main()
