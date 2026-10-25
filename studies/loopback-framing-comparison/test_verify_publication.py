"""Public metadata mapping and adversarial artifact tests; no empirical work."""
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import tempfile
import unittest
import verify_publication as v

ROOT=Path(__file__).resolve().parent
STUDY='reproduction/studies/loopback-framing-comparison'


class PublicVerificationTests(unittest.TestCase):
    def copied(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        root=Path(directory.name)/'package';shutil.copytree(ROOT,root)
        return root

    def rehash_public_inventory(self,root):
        path=root/'PUBLICATION_SHA256.json';data=json.loads(path.read_text())
        data['files']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in root.rglob('*') if p.is_file() and p!=path and '__pycache__' not in p.parts}
        path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')

    def test_verifies_all_original_sources_and_retained_observations(self):
        result=v.verify(ROOT)
        self.assertEqual(result['historical_files'],92)
        self.assertEqual(result['frozen_source_entries'],12)
        self.assertEqual(result['measured_rows'],160)
        self.assertEqual(result['measured_exchanges'],1600)
        self.assertEqual(result['warmup_exchanges'],32)
        self.assertEqual(result['canary_exchanges'],8)
        self.assertEqual(result['csv_statistics'],128)
        self.assertEqual(result['report_numeric_cells'],32)

    def test_code_mutation_rejected_even_if_current_inventory_rehashed(self):
        root=self.copied();p=root/STUDY/'deadline_adapter.py';p.write_text(p.read_text()+'\n# changed\n')
        self.rehash_public_inventory(root)
        with self.assertRaises(ValueError):v.verify(root)

    def test_raw_observation_mutation_rejected_even_if_inventory_rehashed(self):
        root=self.copied();p=root/STUDY/'run-001/result.json';data=json.loads(p.read_text())
        data['rows'][0]['wall_ns']+=1;p.write_text(json.dumps(data))
        self.rehash_public_inventory(root)
        with self.assertRaises(ValueError):v.verify(root)

    def test_mapping_mutation_cannot_authorize_scientific_changes(self):
        root=self.copied();path=root/'PUBLIC_ADAPTATIONS.json';data=json.loads(path.read_text())
        data['files'][STUDY+'/benchmark.py']={'original_sha256':'a'*64,'public_sha256':'b'*64,'changes':['pretend editorial']}
        path.write_text(json.dumps(data));self.rehash_public_inventory(root)
        with self.assertRaises(ValueError):v.verify(root)

    def test_original_pair_mutation_rejected(self):
        root=self.copied();path=root/'ORIGINAL_PUBLIC_FILE_PAIRS.json';data=json.loads(path.read_text())
        data['files'][STUDY+'/run-001/result.json']['original_sha256']='a'*64
        path.write_text(json.dumps(data));self.rehash_public_inventory(root)
        with self.assertRaises(ValueError):v.verify(root)

    def test_missing_historical_dependency_rejected(self):
        root=self.copied();(root/'reproduction/mesh/model.py').unlink()
        self.rehash_public_inventory(root)
        with self.assertRaises(ValueError):v.verify(root)

    def test_unlisted_file_rejected_even_if_inventory_rehashed(self):
        root=self.copied();(root/'unreviewed.txt').write_text('not admitted')
        self.rehash_public_inventory(root)
        with self.assertRaises(ValueError):v.verify(root)

    def test_symlink_not_accepted_as_owned_evidence(self):
        root=self.copied();p=root/STUDY/'run-001/result.json';p.unlink();p.symlink_to(ROOT/STUDY/'run-001/result.json')
        with self.assertRaises(ValueError):v.verify(root)

    def test_unlisted_broken_symlink_rejected(self):
        root=self.copied();(root/'broken').symlink_to(root/'absent')
        with self.assertRaises(ValueError):v.verify(root)

    def test_unlisted_directory_symlink_rejected(self):
        root=self.copied();(root/'shadow').symlink_to(root/'reproduction',target_is_directory=True)
        with self.assertRaises(ValueError):v.verify(root)

    def test_cache_directory_cannot_hide_unlisted_content(self):
        root=self.copied();(root/'__pycache__').mkdir();(root/'__pycache__/hidden.txt').write_text('not allowed')
        with self.assertRaises(ValueError):v.verify(root)

    def test_nonregular_special_entry_rejected_without_opening(self):
        root=self.copied();os.mkfifo(root/'fifo')
        with self.assertRaises(ValueError):v.verify(root)

    def test_receipt_change_rejected_even_if_inventory_rehashed(self):
        root=self.copied();path=root/'admissions/collection.json';data=json.loads(path.read_text())
        data['canary_result_sha256']='a'*64;path.write_text(json.dumps(data))
        self.rehash_public_inventory(root)
        with self.assertRaises(ValueError):v.verify(root)

    def test_prose_derivative_pair_is_exact_not_pattern_based(self):
        root=self.copied();p=root/STUDY/'PROTOCOL.md';p.write_text(p.read_text()+'\nUnreviewed expansion.\n')
        self.rehash_public_inventory(root)
        with self.assertRaises(ValueError):v.verify(root)

    def test_table_checker_catches_changed_reader_number(self):
        root=self.copied();p=root/'RESULTS.md';p.write_text(p.read_text().replace('| 178.178 |','| 999.000 |',1))
        runs=[json.loads((root/STUDY/run/'result.json').read_text()) for run in ('run-001','run-002')]
        with self.assertRaises(ValueError):v.verify_tables(root,runs)

    def test_table_checker_catches_changed_full_precision_statistic(self):
        root=self.copied();p=root/STUDY/'SUMMARY.csv';p.write_text(p.read_text().replace('178177.8','178177.9',1))
        runs=[json.loads((root/STUDY/run/'result.json').read_text()) for run in ('run-001','run-002')]
        with self.assertRaises(ValueError):v.verify_tables(root,runs)

    def test_metadata_has_no_actual_local_paths(self):
        pairs=json.loads((ROOT/'ORIGINAL_PUBLIC_FILE_PAIRS.json').read_text())['files']
        for name in pairs:
            if name.endswith(('.md','.txt')) or name.startswith('reviews/'):
                self.assertIsNone(re.search(r'/workspace/|/home/|/opt/codex|/tmp/tmp[a-zA-Z0-9_]+/',
                                             (ROOT/name).read_text()),name)

    def test_strict_json_and_path_rejection(self):
        for raw in ('{"a":1,"a":2}','{"a":NaN}'):
            with self.assertRaises(ValueError):v.strict(raw)
        for path in ('../outside','/absolute','a/../../outside'):
            with self.assertRaises(ValueError):v.path_under(ROOT,path)

if __name__=='__main__':unittest.main()
