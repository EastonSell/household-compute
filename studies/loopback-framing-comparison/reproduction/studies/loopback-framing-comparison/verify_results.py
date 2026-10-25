"""Independent bounded artifact checks. Never imports codecs, runner or adapter."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import uuid

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent.parent
CASES=('activation_decode','activation_prefill_16','activation_prefill_64','audit_reply')
SOURCE_FILES=('PROTOCOL.md','IMPLEMENTATION_PLAN.md','README.md','benchmark.py',
              'deadline_adapter.py','verify_results.py','test_adapter.py','test_benchmark.py',
              'test_verify_results.py','BASELINE_INVENTORY.json','../tcp-framing-codec/mesh_codec.py',
              '../finite-validation-optimization/candidate_codec.py')
MAX_FILE=1024*1024


def need(value,message):
    if not value: raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def strict(raw):
    def pairs(values):
        result={}
        for k,v in values:
            need(k not in result,'duplicate JSON key')
            result[k]=v
        return result
    def invalid(value):raise ValueError('nonfinite JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def load(path):
    raw=Path(path).read_bytes()
    need(len(raw)<=MAX_FILE,'artifact too large')
    return strict(raw),sha(raw)


def keys(value,expected):
    need(type(value) is dict and set(value)==set(expected),'schema keys')


def integer(value,lo=0,hi=2**53):
    need(type(value) is int and lo<=value<=hi,'integer range')


def number(value,lo=0,hi=2**53,positive=False):
    need(type(value) in (int,float) and math.isfinite(value) and lo<=value<=hi
         and (not positive or value>0),'numeric range')


def hexhash(value):
    need(type(value) is str and len(value)==64 and all(x in '0123456789abcdef' for x in value),'hash')


def timestamp(value):
    need(type(value) is str,'timestamp type')
    parsed=datetime.fromisoformat(value)
    need(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds()==0,'UTC required')
    return parsed


def plan(mode):
    need(mode in ('canary','run-001','run-002'),'mode')
    ordered=[]
    for case in CASES:
        for variant in ('baseline','candidate'):
            ordered.append({'index':len(ordered),'phase':'canary' if mode=='canary' else 'warmup',
                            'block':-1,'case':case,'variant':variant,'iterations':1 if mode=='canary' else 2})
    if mode!='canary':
        for block in range(10):
            for c,case in enumerate(CASES):
                variants=('baseline','candidate') if (block+c)%2==0 else ('candidate','baseline')
                for variant in variants:
                    ordered.append({'index':len(ordered),'phase':'measure','block':block,
                                    'case':case,'variant':variant,'iterations':10})
    return ordered


def fixtures():
    result={}
    for c,name in enumerate(CASES):
        audit=c==3; length=(1,16,64,1)[c]; prior=(1,0,0,1)[c]
        tensor=b''.join(struct.pack('<f',((i%257)-128)/128) for i in range(49152 if audit else 576*length))
        payload=(struct.pack('>I',7) if audit else b'')+tensor
        header=struct.pack('>4sBBBB16sIIIIII16s',b'CMTP',1,9 if audit else 7,
                           1 if audit else 0,2 if audit else 1,bytes(range(16)),
                           0,1,prior,length,len(payload),0,bytes(16))
        result[name]={'frame_bytes':len(header+payload),'payload_bytes':len(payload),
                      'wire_sha256':sha(header+payload),'payload_sha256':sha(payload)}
    return result


def stats(values):
    quartiles=statistics.quantiles(values,n=4,method='inclusive')
    return {'median':statistics.median(values),'min':min(values),'max':max(values),
            'iqr':quartiles[2]-quartiles[0]}


def expected_summary(rows):
    if not rows:return []
    result=[]
    for case in CASES:
        a=[]; b=[]
        for block in range(10):
            pair={r['variant']:r['wall_ns']/r['iterations'] for r in rows if r['case']==case and r['block']==block}
            need(set(pair)=={'baseline','candidate'},'paired cell denominator')
            a.append(pair['baseline']);b.append(pair['candidate'])
        result.append({'case':case,'baseline_ns':stats(a),'candidate_ns':stats(b),
                       'paired_ratio':stats([y/x for x,y in zip(a,b)]),
                       'paired_difference_ns':stats([y-x for x,y in zip(a,b)])})
    return result


def verify_environment(env):
    keys(env,('python','implementation','platform','kernel','machine','logical_cpus','byteorder',
              'native_float_format','candidate_native','gc_enabled','gc_thresholds','tcp_nodelay','timer'))
    for k in ('python','implementation','platform','kernel','machine','native_float_format'):
        need(type(env[k]) is str and 0<len(env[k])<256,'environment string')
    need(env['platform']=='Linux' and env['byteorder'] in ('little','big'),'platform')
    if env['logical_cpus'] is not None:integer(env['logical_cpus'],1,1000000)
    need(type(env['candidate_native']) is bool and env['candidate_native']==
         (env['byteorder']=='little' and env['native_float_format']=='IEEE, little-endian'),'native path')
    need(type(env['gc_enabled']) is bool and env['tcp_nodelay'] is True,'runtime flags')
    need(type(env['gc_thresholds']) is list and len(env['gc_thresholds'])==3,'GC thresholds')
    for n in env['gc_thresholds']:integer(n)
    keys(env['timer'],('implementation','resolution','monotonic','adjustable'))
    need(type(env['timer']['implementation']) is str and env['timer']['monotonic'] is True
         and env['timer']['adjustable'] is False,'timer properties')
    number(env['timer']['resolution'],hi=1,positive=True)


def verify_data(r,c,j,frozen):
    keys(r,('schema','status','mode','freeze_sha256','admission','instance_id','started_at_utc',
            'finished_at_utc','elapsed_seconds','environment','fixtures','rows','commands','totals',
            'inflight','cleanup','owned_child_pid','receiver_sha256','error_type','cleanup_error_type','summary'))
    need(type(r['schema']) is int and r['schema']==1 and r['status']=='complete','completion schema')
    need(r['freeze_sha256']==frozen,'freeze binding');hexhash(frozen);hexhash(r['receiver_sha256'])
    need(r['error_type'] is None and r['cleanup_error_type'] is None and r['inflight'] is None,'error status')
    need(str(uuid.UUID(r['instance_id']))==r['instance_id'],'instance UUID')
    begin=timestamp(r['started_at_utc']);end=timestamp(r['finished_at_utc'])
    need(end>begin,'UTC interval');number(r['elapsed_seconds'],hi=90,positive=True)
    need(r['elapsed_seconds']<90,'operational budget')
    verify_environment(r['environment'])
    need(r['fixtures']==fixtures(),'fixture reconstruction')
    expected=plan(r['mode'])
    keys(r['admission'],('stage','admission_sha256','canary_result_sha256','previous_result_sha256'))
    hexhash(r['admission']['admission_sha256'])
    if r['mode']=='canary':
        need(r['admission']['stage']=='canary' and r['admission']['canary_result_sha256'] is None,'canary admission')
    else:
        need(r['admission']['stage']=='collection','collection admission');hexhash(r['admission']['canary_result_sha256'])
    if r['mode']=='run-002':hexhash(r['admission']['previous_result_sha256'])
    else:need(r['admission']['previous_result_sha256'] is None,'unexpected prior run')
    keys(r['cleanup'],('pid','returncode','terminated','killed','reaped'))
    integer(r['cleanup']['pid'],2);integer(r['owned_child_pid'],2)
    need(r['cleanup']['pid']==r['owned_child_pid'] and type(r['cleanup']['returncode']) is int
         and r['cleanup']['returncode']==0 and r['cleanup']['terminated'] is False
         and r['cleanup']['killed'] is False and r['cleanup']['reaped'] is True,'clean owned reap')
    need(type(r['commands']) is list and len(r['commands'])==len(expected),'command denominator')
    measured=[]
    for command,p in zip(r['commands'],expected):
        keys(command,set(p)|{'sent','received'})
        for k in ('index','iterations'):integer(command[k])
        need(type(command['block']) is int,'block type')
        need({k:command[k] for k in p}==p,'command order')
        integer(command['sent'],1);integer(command['received'],1)
        need(command['sent']==p['iterations']*r['fixtures'][p['case']]['frame_bytes']
             and command['received']==p['iterations']*16,'command byte accounting')
        if p['phase']=='measure':measured.append(command)
    need(type(r['rows']) is list and len(r['rows'])==len(measured),'measurement denominator')
    for row,command in zip(r['rows'],measured):
        keys(row,set(command)|{'wall_ns','wall_ns_per_exchange'})
        for k in ('index','iterations','sent','received'):integer(row[k])
        need(type(row['block']) is int,'measured block type')
        need({k:row[k] for k in command}==command,'measured row order')
        integer(row['wall_ns'],1,85_000_000_000)
        number(row['wall_ns_per_exchange'],positive=True)
        need(row['wall_ns_per_exchange']==row['wall_ns']/row['iterations'],'derived latency')
    wall_sum=sum(x['wall_ns'] for x in r['rows'])
    need(wall_sum<=r['elapsed_seconds']*1e9 and wall_sum<=(end-begin).total_seconds()*1e9+1e6,'enclosing interval')
    keys(r['totals'],('sent','received'))
    for value in r['totals'].values():integer(value,1)
    expected_totals={'sent':32+8+8*len(expected)+sum(x['sent'] for x in r['commands']),
                     'received':8+8+8*len(expected)+sum(x['received'] for x in r['commands'])}
    need(r['totals']==expected_totals,'all transfer accounting')
    keys(c,('status','mode','freeze_sha256','commands','totals','inflight','candidate_native','error_type'))
    need(c['status']=='complete' and c['mode']==r['mode'] and c['freeze_sha256']==frozen
         and c['error_type'] is None and c['inflight'] is None and type(c['candidate_native']) is bool
         and c['candidate_native']==r['environment']['candidate_native'],'receiver status')
    need(type(c['commands']) is list and len(c['commands'])==len(expected),'receiver denominator')
    for command in c['commands']:
        keys(command,set(expected[0])|{'sent','received'})
        for k in ('index','iterations','sent','received'):integer(command[k])
        need(type(command['block']) is int,'receiver block type')
    need(c['commands']==[dict(x,sent=x['received'],received=x['sent']) for x in r['commands']],
         'receiver command reconciliation')
    need(c['totals']=={'sent':r['totals']['received'],'received':r['totals']['sent']},'receiver totals')
    wanted=[{'event':'start','mode':r['mode'],'freeze_sha256':frozen,'instance_id':r['instance_id']}]
    row_iter=iter(r['rows'])
    for command in r['commands']:
        wanted.append({'event':'row','row':next(row_iter)} if command['phase']=='measure'
                      else {'event':'untimed','command':command})
    wanted.append({'event':'terminal','status':'complete','rows':len(r['rows']),'commands':len(expected),
                   'cleanup':r['cleanup'],'error_type':None,'cleanup_error_type':None})
    need(json.dumps(j,sort_keys=True,allow_nan=False)==json.dumps(wanted,sort_keys=True,allow_nan=False),
         'complete ordered journal')
    need(type(r['summary']) is list,'summary type')
    for summary in r['summary']:
        keys(summary,('case','baseline_ns','candidate_ns','paired_ratio','paired_difference_ns'))
        for k in ('baseline_ns','candidate_ns','paired_ratio','paired_difference_ns'):
            keys(summary[k],('median','min','max','iqr'))
            for n in summary[k].values():number(n,lo=-2**53)
    need(r['summary']==expected_summary(r['rows']),'summary reconstruction')
    return {'mode':r['mode'],'rows':len(r['rows']),'commands':len(expected)}


def verify_freeze():
    f,d=load(ROOT/'PRE_DATA_SHA256.json')
    keys(f,('schema','frozen_at_utc','sources'))
    need(type(f['schema']) is int and f['schema']==1,'freeze version');timestamp(f['frozen_at_utc'])
    keys(f['sources'],SOURCE_FILES)
    for name,expected in f['sources'].items():
        hexhash(expected);need(sha((ROOT/name).read_bytes())==expected,'source changed: '+name)
    inventory,_=load(ROOT/'BASELINE_INVENTORY.json')
    keys(inventory,('schema','local_source_commit','published_context_commit','files'))
    need(inventory['local_source_commit']=='ca3b43adc952dbf22c91d2985512836a5cf78bdd'
         and inventory['published_context_commit']=='18690974e3b7c82dd75d69509db5c54f3fae4925','baseline context')
    for name,expected in inventory['files'].items():
        hexhash(expected);need(sha((REPO/name).read_bytes())==expected,'historical file changed: '+name)
    return d


def verify_run(directory):
    frozen=verify_freeze()
    root=Path(directory)
    r,rsha=load(root/'result.json');c,csha=load(root/'receiver.json')
    need(r['receiver_sha256']==csha,'receiver hash')
    raw=(root/'journal.jsonl').read_bytes()
    need(len(raw)<=MAX_FILE and raw.endswith(b'\n'),'journal framing')
    j=[strict(line) for line in raw.splitlines()]
    checked=verify_data(r,c,j,frozen)
    return r,rsha,checked


def verify_pair(first,second):
    a,asha,acheck=verify_run(first);b,bsha,bcheck=verify_run(second)
    need((a['mode'],b['mode'])==('run-001','run-002'),'planned run set')
    need(a['instance_id']!=b['instance_id'],'distinct driver process instances')
    need(timestamp(a['finished_at_utc'])<=timestamp(b['started_at_utc']),'sequential run intervals')
    need(a['environment']==b['environment'] and a['freeze_sha256']==b['freeze_sha256'],'run set environment')
    need(b['admission']['previous_result_sha256']==asha and
         dict(b['admission'],previous_result_sha256=None)==a['admission'],'run set admission chain')
    return [acheck,bcheck]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directories',nargs='+');p.add_argument('--canary',action='store_true')
    args=p.parse_args()
    if args.canary:
        need(len(args.directories)==1,'one canary directory required')
        r,_,checked=verify_run(args.directories[0]);need(r['mode']=='canary','canary mode')
        answer=checked
    else:
        need(len(args.directories)==2,'both planned runs required')
        answer=verify_pair(*args.directories)
    print(json.dumps(answer,sort_keys=True))


if __name__=='__main__':main()
