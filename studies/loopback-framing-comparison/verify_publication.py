"""Verify exact public metadata derivatives and unchanged retained observations.

Read-only, standard-library artifact verification. No sockets, child processes,
model work, timing observations, source rewriting, or monkey-patching.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path, PurePosixPath
import sys

ROOT=Path(__file__).resolve().parent
STUDY='reproduction/studies/loopback-framing-comparison'
FREEZE='c8367af12ccb2434ea5a15d6f3fe162e521994768c74e75c98eb40b4b4c68f65'
POSTDATA='13a8694371348c7ce725954021ab7ef656c1db20ba3006145f636313a08093d3'
ADAPTATIONS='3df33bde06bd837b55bedf31ed5378d314724ca144ee58c8781a1ec088f8cd3b'
PAIRS='06cdf53831e193f201af7e668a268c8c2e506f2f61140cf7f5cb8c541bc2218b'
GENERATED={'README.md','PUBLIC_ADAPTATIONS.json','ORIGINAL_PUBLIC_FILE_PAIRS.json',
           'verify_publication.py','test_verify_publication.py'}


def need(ok,message):
    if not ok:raise ValueError(message)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def strict(raw):
    def pairs(items):
        output={}
        for key,value in items:
            need(key not in output,'duplicate JSON key');output[key]=value
        return output
    def invalid(value):raise ValueError('nonfinite JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def path_under(root,name):
    relative=PurePosixPath(name)
    need(type(name) is str and not relative.is_absolute() and name and '..' not in relative.parts,
         'unsafe package-relative path')
    root=Path(root).resolve();path=root
    for part in relative.parts:
        path=path/part
        need(not path.is_symlink(),'symlink evidence is not permitted')
    need(path.resolve().is_relative_to(root),'escaped package path')
    return path


def read(root,name):
    path=path_under(root,name)
    try:
        with path.open('rb') as file:raw=file.read(4*1024*1024+1)
    except OSError as exc:
        raise ValueError('artifact unavailable: '+name) from exc
    need(len(raw)<=4*1024*1024,'artifact cap')
    return raw


def load(root,name):return strict(read(root,name))


def verify_tables(root,runs):
    source=path_under(root,STUDY+'/SUMMARY.csv')
    with source.open(newline='') as f:
        reader=csv.DictReader(f);rows=list(reader);fieldnames=reader.fieldnames
    metrics=('baseline_ns','candidate_ns','paired_ratio','paired_difference_ns')
    statistics=('median','min','max','iqr')
    columns=['run','case','paired_batches','exchanges_per_batch']+[m+'_'+s for m in metrics for s in statistics]
    need(fieldnames==columns and len(rows)==8,'CSV schema and denominator')
    count=0;wanted_table=[]
    for run in runs:
        for summary in run['summary']:
            row=rows[count];count+=1
            need(row['run']==run['mode'] and row['case']==summary['case']
                 and row['paired_batches']=='10' and row['exchanges_per_batch']=='10','CSV cell identity')
            for metric in metrics:
                for statistic in statistics:
                    need(float(row[metric+'_'+statistic])==summary[metric][statistic],'CSV numerical mismatch')
            wanted_table.append([run['mode'],summary['case'],f"{summary['baseline_ns']['median']/1000:.3f}",
                                 f"{summary['candidate_ns']['median']/1000:.3f}",f"{summary['paired_ratio']['median']:.6f}",
                                 f"{summary['paired_difference_ns']['median']/1000:.3f}"])
    observed=[[cell.strip() for cell in line.split('|')[1:-1]]
              for line in read(root,'RESULTS.md').decode().splitlines() if line.startswith('| run-')]
    need(observed==wanted_table,'reader table numerical mismatch')
    return {'csv_statistics':128,'report_numeric_cells':32}


def regular_file_names(root):
    """Inspect entry types before opening evidence; never follow links or FIFOs."""
    need(root.is_dir() and not root.is_symlink(),'package must be a real directory')
    names=set()
    def inaccessible(error):
        raise ValueError('package entry scan failed') from error
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=inaccessible):
        for name in dirs+files:
            path=Path(directory)/name
            mode=path.lstat().st_mode
            need(not stat.S_ISLNK(mode),'all package symlinks are prohibited')
            need(name!='__pycache__','cache directories/files are prohibited; use Python -B')
            need(stat.S_ISDIR(mode) or stat.S_ISREG(mode),'non-regular package entry')
            if stat.S_ISREG(mode):names.add(str(path.relative_to(root)))
    return names


def verify(root=ROOT):
    root=Path(root)
    actual_names=regular_file_names(root)
    need(digest(read(root,'PUBLIC_ADAPTATIONS.json'))==ADAPTATIONS,'unreviewed adaptation mapping')
    need(digest(read(root,'ORIGINAL_PUBLIC_FILE_PAIRS.json'))==PAIRS,'unreviewed original/public pairs')
    adaptation=load(root,'PUBLIC_ADAPTATIONS.json');pairs=load(root,'ORIGINAL_PUBLIC_FILE_PAIRS.json')
    need(set(pairs)=={'schema','files'} and type(pairs['schema']) is int and pairs['schema']==1,'pair schema')
    need(set(adaptation)=={'schema','scope','original_freeze_sha256','original_postdata_sha256','files'}
         and adaptation['schema']==1 and adaptation['original_freeze_sha256']==FREEZE
         and adaptation['original_postdata_sha256']==POSTDATA,'adaptation schema')
    need(len(pairs['files'])==149 and len(adaptation['files'])==17,'fixed derivative denominator')
    changed=set()
    for name,pair in pairs['files'].items():
        need(set(pair)=={'original_sha256','public_sha256'},'pair keys')
        need(digest(read(root,name))==pair['public_sha256'],'public bytes changed: '+name)
        if pair['original_sha256']!=pair['public_sha256']:
            changed.add(name)
            need(name in adaptation['files'],'unmapped derivative')
            mapped=adaptation['files'][name]
            need(mapped['original_sha256']==pair['original_sha256'] and mapped['public_sha256']==pair['public_sha256'],
                 'original/public derivative mismatch')
            need(name.endswith(('.md','.txt')) or name in ('reviews/REVIEW.json','reviews/POSTRUN_REVIEW.json'),
                 'scientific data or code adaptation prohibited')
    need(changed==set(adaptation['files']),'adaptation inventory mismatch')

    def original(name,expected):
        path_under(root,name)
        need(name in pairs['files'] and pairs['files'][name]['original_sha256']==expected,
             'original provenance mismatch: '+name)

    # No historical baseline check is dropped: all original 92 files are bundled.
    inventory=load(root,STUDY+'/BASELINE_INVENTORY.json')
    need(len(inventory['files'])==92,'historical inventory denominator')
    need(inventory['local_source_commit']=='ca3b43adc952dbf22c91d2985512836a5cf78bdd'
         and inventory['published_context_commit']=='18690974e3b7c82dd75d69509db5c54f3fae4925','baseline commits')
    for name,expected in inventory['files'].items():original('reproduction/'+name,expected)
    need(digest(read(root,STUDY+'/PRE_DATA_SHA256.json'))==FREEZE,'original freeze changed')
    frozen=load(root,STUDY+'/PRE_DATA_SHA256.json')
    need(len(frozen['sources'])==12,'frozen source denominator')
    for name,expected in frozen['sources'].items():
        resolved=(path_under(root,STUDY)/name).resolve()
        need(resolved.is_relative_to(root.resolve()),'frozen path escape')
        original(str(resolved.relative_to(root.resolve())),expected)
    need(digest(read(root,STUDY+'/POST_DATA_SHA256.json'))==POSTDATA,'reviewed evidence inventory changed')
    postdata=load(root,STUDY+'/POST_DATA_SHA256.json')
    need(len(postdata['files'])==50,'reviewed artifact denominator')
    for name,expected in postdata['files'].items():original(STUDY+'/'+name,expected)

    # The imported verifier itself was already checked byte-for-byte above.
    spec=importlib.util.spec_from_file_location('_accepted_loopback_verifier',path_under(root,STUDY+'/verify_results.py'))
    verifier=importlib.util.module_from_spec(spec);sys.modules[spec.name]=verifier;spec.loader.exec_module(verifier)
    records={};hashes={};checked=[]
    for label in ('canary-001','run-001','run-002'):
        directory=STUDY+'/'+label
        result=load(root,directory+'/result.json');receiver=load(root,directory+'/receiver.json')
        journal_raw=read(root,directory+'/journal.jsonl')
        need(journal_raw.endswith(b'\n'),'journal framing')
        journal=[strict(line) for line in journal_raw.splitlines()]
        need(result['receiver_sha256']==digest(read(root,directory+'/receiver.json')),'receiver binding')
        checked.append(verifier.verify_data(result,receiver,journal,FREEZE))
        records[label]=result;hashes[label]=digest(read(root,directory+'/result.json'))
    a=records['run-001'];b=records['run-002'];canary=records['canary-001']
    need((a['mode'],b['mode'],canary['mode'])==('run-001','run-002','canary'),'run identities')
    need(a['instance_id']!=b['instance_id'],'distinct process instances')
    need(verifier.timestamp(a['finished_at_utc'])<=verifier.timestamp(b['started_at_utc']),'run order')
    need(a['environment']==b['environment'] and a['freeze_sha256']==b['freeze_sha256'],'run environment')
    need(b['admission']['previous_result_sha256']==hashes['run-001'] and
         dict(b['admission'],previous_result_sha256=None)==a['admission'],'previous run chain')
    ca=load(root,'admissions/canary.json');co=load(root,'admissions/collection.json')
    need(ca=={'schema':1,'stage':'canary','freeze_sha256':FREEZE},'canary admission')
    need(co=={'schema':1,'stage':'collection','freeze_sha256':FREEZE,'canary_result_sha256':hashes['canary-001']},
         'collection admission')
    need(canary['admission']['admission_sha256']==digest(read(root,'admissions/canary.json')),'canary receipt chain')
    need(a['admission']['admission_sha256']==digest(read(root,'admissions/collection.json'))
         and a['admission']['canary_result_sha256']==hashes['canary-001'],'collection receipt chain')
    receipt=load(root,STUDY+'/COLLECTION_RECEIPT.json')
    need(receipt['freeze_sha256']==FREEZE and receipt['canary_result_sha256']==hashes['canary-001']
         and receipt['canary_admission_sha256']==digest(read(root,'admissions/canary.json'))
         and receipt['collection_admission_sha256']==digest(read(root,'admissions/collection.json')),'execution receipt chain')
    original('reviews/REVIEW.json',receipt['independent_predata_review_sha256'])
    pre_review=load(root,'reviews/REVIEW.json');post_review=load(root,'reviews/POSTRUN_REVIEW.json')
    need(pre_review['decision']=='PASS' and pre_review['freeze_sha256']==FREEZE,'predata review')
    need(post_review['decision']=='PASS' and post_review['predata_manifest_sha256']==FREEZE
         and post_review['postdata_manifest_sha256']==POSTDATA,'postdata review')
    original(STUDY+'/RESULTS.md',post_review['report_sha256'])
    original('RESULTS.md',post_review['report_sha256'])
    need(post_review['run_001_result_sha256']==hashes['run-001']
         and post_review['run_002_result_sha256']==hashes['run-002']
         and post_review['canary_result_sha256']==hashes['canary-001'],'reviewed raw result identity')
    table_checks=verify_tables(root,[a,b])

    # Current whole-package inventory is separate from the historical freeze.
    manifest=load(root,'PUBLICATION_SHA256.json')
    need(set(manifest)=={'schema','files'} and type(manifest['schema']) is int and manifest['schema']==1,'publication schema')
    expected_names=set(pairs['files'])|GENERATED
    need(set(manifest['files'])==expected_names,'publication inventory scope')
    need(actual_names==expected_names|{'PUBLICATION_SHA256.json'},'unlisted or missing package files')
    for name,expected in manifest['files'].items():need(digest(read(root,name))==expected,'publication file changed: '+name)
    return {'status':'verified','original_public_pairs':149,'metadata_derivatives':17,'historical_files':92,
            'frozen_source_entries':12,'reviewed_evidence_files':50,'measured_rows':160,
            'measured_exchanges':1600,'warmup_exchanges':32,'canary_exchanges':8,
            'public_files':len(expected_names),**table_checks}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',type=Path,default=ROOT)
    print(json.dumps(verify(parser.parse_args().base),sort_keys=True))
