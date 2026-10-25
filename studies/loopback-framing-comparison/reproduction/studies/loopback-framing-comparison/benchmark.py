"""Fixed two-process loopback experiment. Main is gated by independent admission."""
import argparse
from datetime import datetime, timezone
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import socket
import statistics
import struct
import subprocess
import sys
import time
import uuid

import deadline_adapter as adapter

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
CODEC_PATHS = {'baseline': ROOT.parent / 'tcp-framing-codec/mesh_codec.py',
               'candidate': ROOT.parent / 'finite-validation-optimization/candidate_codec.py'}
CODEC_HASHES = {'baseline':'3fcb2b2dffd7d95e56d4887ce02a63482ff612b4a7c0313e9fbcb715a419b5aa',
                'candidate':'0cde18f73e790b7e7f600bf1dc25f6a9059e2a6289396584698bee0f6e77a58b'}
CASES = ('activation_decode', 'activation_prefill_16', 'activation_prefill_64', 'audit_reply')
VARIANTS = ('baseline', 'candidate')
ACK = struct.Struct('>4sIII')
CONTROL = struct.Struct('>4sI')
MAX_FILE = 1024 * 1024
SOURCE_FILES = ('PROTOCOL.md', 'IMPLEMENTATION_PLAN.md', 'README.md', 'benchmark.py',
                'deadline_adapter.py', 'verify_results.py', 'test_adapter.py',
                'test_benchmark.py', 'test_verify_results.py', 'BASELINE_INVENTORY.json',
                '../tcp-framing-codec/mesh_codec.py',
                '../finite-validation-optimization/candidate_codec.py')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def read_json(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= MAX_FILE, 'input artifact cap')
    return loads(raw), digest(raw)


def encoded(value):
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
    require(len(raw) <= MAX_FILE, 'output artifact cap')
    return raw


def write_json(path, value):
    raw = encoded(value)
    with Path(path).open('xb') as f:
        f.write(raw)


class Journal:
    def __init__(self, path):
        self.file = Path(path).open('xb')
        self.size = 0
    def add(self, value, terminal=False):
        raw = encoded(value)
        require(self.size + len(raw) <= MAX_FILE - (0 if terminal else 4096), 'journal cap')
        self.file.write(raw)
        self.file.flush()
        self.size += len(raw)
    def close(self):
        self.file.close()


def check_inventory():
    inventory, _ = read_json(ROOT / 'BASELINE_INVENTORY.json')
    require(set(inventory) == {'schema', 'local_source_commit', 'published_context_commit', 'files'},
            'inventory schema')
    for name, expected in inventory['files'].items():
        require(digest((REPO/name).read_bytes()) == expected, 'historical file changed: '+name)


def freeze():
    data, sha = read_json(ROOT / 'PRE_DATA_SHA256.json')
    require(set(data) == {'schema', 'frozen_at_utc', 'sources'} and type(data['schema']) is int
            and data['schema'] == 1 and set(data['sources']) == set(SOURCE_FILES), 'freeze schema')
    for name, expected in data['sources'].items():
        require(digest((ROOT/name).read_bytes()) == expected, 'frozen source changed: '+name)
    check_inventory()
    return sha


def admit(path, mode, frozen, canary_path, previous_path):
    data, sha = read_json(path)
    stage = 'canary' if mode == 'canary' else 'collection'
    keys = {'schema', 'stage', 'freeze_sha256'}
    if stage == 'collection': keys.add('canary_result_sha256')
    require(set(data)==keys and type(data['schema']) is int and data['schema']==1
            and data['stage']==stage and data['freeze_sha256']==frozen, 'admission mismatch')
    evidence = {'stage': stage, 'admission_sha256': sha, 'canary_result_sha256': None,
                'previous_result_sha256': None}
    if stage == 'collection':
        require(canary_path is not None, 'canary required')
        canary, canary_sha = read_json(canary_path)
        require(canary_sha == data['canary_result_sha256'] and canary['status']=='complete'
                and canary['mode']=='canary' and canary['freeze_sha256']==frozen,
                'canary binding failed')
        evidence['canary_result_sha256'] = canary_sha
    if mode == 'run-002':
        require(previous_path is not None, 'successful first run required')
        prev, prev_sha = read_json(previous_path)
        require(prev['status']=='complete' and prev['mode']=='run-001'
                and prev['freeze_sha256']==frozen and prev['admission']==dict(evidence, previous_result_sha256=None),
                'previous run binding failed')
        evidence['previous_result_sha256'] = prev_sha
    else:
        require(previous_path is None, 'unexpected previous run')
    return evidence


def build_cases():
    codecs = {}
    for variant, path in CODEC_PATHS.items():
        require(digest(path.read_bytes()) == CODEC_HASHES[variant], 'codec digest mismatch')
        name = 'loopback_' + variant
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        codecs[variant] = module
    cases = {v:{} for v in VARIANTS}
    for name, length, prior, audit in zip(CASES, (1,16,64,1), (1,0,0,1), (False,False,False,True)):
        count = 49152 if audit else 576*length
        tensor = struct.pack('<'+'f'*count, *(((i%257)-128)/128 for i in range(count)))
        payload = struct.pack('>I', 7)+tensor if audit else tensor
        expected = None
        for variant in VARIANTS:
            c = codecs[variant]
            h = c.Header(c.Kind.AUDIT if audit else c.Kind.ACTIVATION_RESULT,
                         1 if audit else 0, c.Mode.AUDIT if audit else c.Mode.TOKEN,
                         bytes(range(16)), 0, 1, prior, length, len(payload))
            frame = c.Frame(h, payload)
            wire = frame.pack()
            used, decoded = c.Decoder().consume(wire)
            require(used==len(wire) and type(decoded) is c.Frame and decoded==frame, 'fixture roundtrip')
            require(expected is None or wire==expected, 'codec wire mismatch')
            expected = wire
            cases[variant][name] = frame
    return codecs, cases


def fixture_metadata(cases):
    return {name: {'frame_bytes': len(cases['baseline'][name].pack()),
                   'payload_bytes': len(cases['baseline'][name].payload),
                   'wire_sha256': digest(cases['baseline'][name].pack()),
                   'payload_sha256': digest(cases['baseline'][name].payload)} for name in CASES}


def schedule(mode):
    require(mode in ('canary','run-001','run-002'), 'run label')
    result = []
    def add(phase, block, case, variant, iterations):
        result.append(dict(index=len(result), phase=phase, block=block, case=case,
                           variant=variant, iterations=iterations))
    for case in CASES:
        for variant in VARIANTS:
            add('canary' if mode=='canary' else 'warmup', -1, case, variant, 1 if mode=='canary' else 2)
    if mode != 'canary':
        for block in range(10):
            for c, case in enumerate(CASES):
                order = VARIANTS if (block+c)%2==0 else VARIANTS[::-1]
                for variant in order:
                    add('measure', block, case, variant, 10)
    return result


def measure(operation, iterations, wall=time.perf_counter_ns):
    start = wall()
    for i in range(iterations): operation(i)
    end = wall()
    require(type(start) is int and type(end) is int and end > start, 'invalid timer interval')
    return end-start


def check_ack(data, index, iteration, frame_bytes):
    require(data == ACK.pack(b'ACK1',index,iteration,frame_bytes), 'invalid acknowledgement')


def describe(values):
    q1, _, q3 = statistics.quantiles(values, n=4, method='inclusive')
    return {'median':statistics.median(values), 'min':min(values), 'max':max(values), 'iqr':q3-q1}


def summaries(rows):
    if not rows: return []
    result = []
    for case in CASES:
        a = [r['wall_ns']/r['iterations'] for r in rows if r['case']==case and r['variant']=='baseline']
        b = [r['wall_ns']/r['iterations'] for r in rows if r['case']==case and r['variant']=='candidate']
        require(len(a)==len(b)==10, 'summary denominator')
        result.append({'case':case, 'baseline_ns':describe(a), 'candidate_ns':describe(b),
                       'paired_ratio':describe([y/x for x,y in zip(a,b)]),
                       'paired_difference_ns':describe([y-x for x,y in zip(a,b)])})
    return result


def environment(codecs):
    return {'python':platform.python_version(), 'implementation':platform.python_implementation(),
            'platform':platform.system(), 'kernel':platform.release(), 'machine':platform.machine(),
            'logical_cpus':os.cpu_count(), 'byteorder':sys.byteorder,
            'native_float_format':float.__getformat__('float'),
            'candidate_native':codecs['candidate']._NATIVE_FP32_LE,
            'gc_enabled':gc.isenabled(), 'gc_thresholds':list(gc.get_threshold()),
            'tcp_nodelay':True,
            'timer':{'implementation':time.get_clock_info('perf_counter').implementation,
                     'resolution':time.get_clock_info('perf_counter').resolution,
                     'monotonic':time.get_clock_info('perf_counter').monotonic,
                     'adjustable':time.get_clock_info('perf_counter').adjustable}}


def deadline(work_end):
    return min(time.monotonic()+2.0, work_end)


def send_exchange(io, codec, frame, row, iteration, work_end):
    end = deadline(work_end)
    ledger = codec.Ledger()
    codec.write_frame(io.write, frame, ledger, 'c0', time.monotonic, end, lambda exc: None)
    check_ack(io.read_exact(16, end), row['index'], iteration, 64+len(frame.payload))


def receive_exchange(io, codec, frame, row, iteration, work_end):
    end = deadline(work_end)
    ledger = codec.Ledger()
    decoded = codec.read_frame(io.read, codec.Decoder(), ledger, 'c0', time.monotonic, end)
    require(type(decoded) is codec.Frame and decoded==frame, 'receiver exact frame mismatch')
    io.send_all(ACK.pack(b'ACK1',row['index'],iteration,64+len(frame.payload)), end)


def receive_session(io, mode, codecs, cases, work_end, records, progress=None):
    if progress is None: progress={}
    for row in schedule(mode):
        before=(io.sent,io.received)
        active={'index':row['index'],'stage':'control','completed_exchanges':0,'sent':0,'received':0}
        progress['inflight']=active
        try:
            require(io.read_exact(8, work_end)==CONTROL.pack(b'CMD1',row['index']), 'command schedule mismatch')
            io.send_all(CONTROL.pack(b'RDY1',row['index']), work_end)
            before = (io.sent, io.received)
            active['stage']='data'
            for i in range(row['iterations']):
                receive_exchange(io, codecs[row['variant']], cases[row['variant']][row['case']], row, i, work_end)
                active['completed_exchanges']+=1
            records.append(dict(row, sent=io.sent-before[0], received=io.received-before[1]))
        finally:
            active.update(sent=io.sent-before[0],received=io.received-before[1])
        progress['inflight']=None
    require(io.read_exact(8, work_end)==CONTROL.pack(b'DONE',len(records)), 'finish command')
    io.send_all(CONTROL.pack(b'DONE',len(records)), work_end)
    return records


def receiver(args, frozen, admission):
    listener = conn = io = None
    result = {'status':'failed','mode':args.mode,'freeze_sha256':frozen,'commands':[],
              'totals':None,'inflight':None,'candidate_native':None,'error_type':None}
    try:
        codecs, cases = build_cases()
        result['candidate_native'] = codecs['candidate']._NATIVE_FP32_LE
        work_end = args.started+85
        listener = socket.socket(fileno=args.fd)
        require(listener.getsockname()[0]=='127.0.0.1', 'listener address')
        io = adapter.accept(listener, min(args.started+10, work_end))
        conn = io.sock
        listener.close(); listener = None
        conn.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        require(io.read_exact(32,min(args.started+10,work_end))==bytes.fromhex(args.nonce), 'nonce mismatch')
        io.send_all(b'HELLOACK',min(args.started+10,work_end))
        receive_session(io,args.mode,codecs,cases,work_end,result['commands'],result)
        result['totals'] = {'sent':io.sent,'received':io.received}
        require(freeze()==frozen, 'receiver source changed')
        require(admit(args.admission,args.mode,frozen,args.canary_result,args.previous_result)==admission,
                'receiver admission changed')
        result['status']='complete'
    except BaseException as exc:
        result['error_type']=type(exc).__name__
    finally:
        if io is not None:result['totals']={'sent':io.sent,'received':io.received}
        for owned_socket in (conn,listener):
            if owned_socket is not None:
                try:owned_socket.close()
                except BaseException as exc:
                    result['status']='failed'
                    if result['error_type'] is None:result['error_type']=type(exc).__name__
        write_json(Path(args.output)/'receiver.json',result)
    return 0 if result['status']=='complete' else 1


def utc():
    return datetime.now(timezone.utc).isoformat()


def driver(args, frozen, admission, started):
    output = Path(args.output)
    output.mkdir(parents=False,exist_ok=False)
    journal = Journal(output/'journal.jsonl')
    child = conn = listener = io = None
    result = {'schema':1,'status':'failed','mode':args.mode,'freeze_sha256':frozen,
              'admission':admission,'instance_id':str(uuid.uuid4()),'started_at_utc':utc(),
              'finished_at_utc':None,'elapsed_seconds':None,'environment':None,'fixtures':None,
              'rows':[],'commands':[],'totals':None,'inflight':None,'cleanup':None,'owned_child_pid':None,'receiver_sha256':None,
              'error_type':None,'cleanup_error_type':None,'summary':[]}
    try:
        require(sys.platform.startswith('linux'), 'Linux pass_fds implementation required')
        codecs,cases=build_cases()
        result['environment']=environment(codecs)
        result['fixtures']=fixture_metadata(cases)
        journal.add({'event':'start','mode':args.mode,'freeze_sha256':frozen,
                     'instance_id':result['instance_id']})
        work_end=started+85
        adapter.Budget().remaining(min(started+10,work_end))
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.setblocking(False)
        listener.bind(('127.0.0.1',0)); listener.listen(1)
        target=listener.getsockname(); adapter.validate_address(target)
        nonce=os.urandom(32)
        cmd=[sys.executable,'-B',str(ROOT/'benchmark.py'),'--receiver','--fd',str(listener.fileno()),
             '--nonce',nonce.hex(),'--started',str(started),'--mode',args.mode,
             '--admission',str(Path(args.admission).resolve()),'--output',str(output.resolve())]
        if args.canary_result: cmd += ['--canary-result',str(Path(args.canary_result).resolve())]
        if args.previous_result: cmd += ['--previous-result',str(Path(args.previous_result).resolve())]
        child=subprocess.Popen(cmd,pass_fds=(listener.fileno(),),stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
        result['owned_child_pid']=child.pid
        listener.close(); listener=None
        conn=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        conn.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        io=adapter.connect(conn,target,min(started+10,work_end))
        io.send_all(nonce,min(started+10,work_end))
        require(io.read_exact(8,min(started+10,work_end))==b'HELLOACK','handshake ack')
        for row in schedule(args.mode):
            adapter.Budget().remaining(work_end)
            before=(io.sent,io.received)
            active={'index':row['index'],'stage':'control','completed_exchanges':0,'sent':0,'received':0}
            result['inflight']=active
            try:
                io.send_all(CONTROL.pack(b'CMD1',row['index']),work_end)
                require(io.read_exact(8,work_end)==CONTROL.pack(b'RDY1',row['index']),'ready acknowledgement')
                before=(io.sent,io.received)
                active['stage']='data'
                def op(i):
                    send_exchange(io,codecs[row['variant']],cases[row['variant']][row['case']],row,i,work_end)
                    active['completed_exchanges']+=1
                wall_ns=None
                if row['phase']=='measure':wall_ns=measure(op,row['iterations'])
                else:
                    for i in range(row['iterations']):op(i)
                command=dict(row,sent=io.sent-before[0],received=io.received-before[1])
                require(command['sent']==row['iterations']*result['fixtures'][row['case']]['frame_bytes']
                        and command['received']==row['iterations']*16,'driver transfer accounting')
                result['commands'].append(command)
            finally:
                active.update(sent=io.sent-before[0],received=io.received-before[1])
            result['inflight']=None
            if wall_ns is not None:
                measured=dict(command,wall_ns=wall_ns,wall_ns_per_exchange=wall_ns/row['iterations'])
                result['rows'].append(measured)
                journal.add({'event':'row','row':measured})
            else:journal.add({'event':'untimed','command':command})
            adapter.Budget().remaining(work_end)
        io.send_all(CONTROL.pack(b'DONE',len(result['commands'])),work_end)
        require(io.read_exact(8,work_end)==CONTROL.pack(b'DONE',len(result['commands'])),'finish ack')
        result['totals']={'sent':io.sent,'received':io.received}
        result['status']='complete'
    except BaseException as exc:
        result['error_type']=type(exc).__name__
    finally:
        if io is not None:result['totals']={'sent':io.sent,'received':io.received}
        for owned_socket in (conn, listener):
            if owned_socket is not None:
                try:
                    owned_socket.close()
                except BaseException as exc:
                    result['status']='failed'
                    result['cleanup_error_type']=type(exc).__name__
        if child is not None:
            try:
                result['cleanup']=adapter.cleanup_child(child,started+90)
                require(result['cleanup']['returncode']==0 and not result['cleanup']['terminated']
                        and not result['cleanup']['killed'],'receiver did not exit cleanly')
            except BaseException as exc:
                result['status']='failed'
                if isinstance(exc,adapter.CleanupError):result['cleanup']=exc.result
                result['cleanup_error_type']=getattr(exc,'cause_type',type(exc).__name__)
        try:
            require(child is not None and result['cleanup'] is not None,'missing child lifecycle')
            receiver_result,receiver_sha=read_json(output/'receiver.json')
            result['receiver_sha256']=receiver_sha
            require(receiver_result['status']=='complete','receiver failure')
            require(freeze()==frozen,'source changed')
            require(admit(args.admission,args.mode,frozen,args.canary_result,args.previous_result)==admission,
                    'admission changed during run')
            if result['status']=='complete': result['summary']=summaries(result['rows'])
            result['elapsed_seconds']=time.monotonic()-started
            require(0 < result['elapsed_seconds'] < 90,'total run budget')
        except BaseException as exc:
            result['status']='failed'
            if result['error_type'] is None: result['error_type']=type(exc).__name__
        result['finished_at_utc']=utc()
        try:
            journal.add({'event':'terminal','status':result['status'],'rows':len(result['rows']),
                         'commands':len(result['commands']),'cleanup':result['cleanup'],
                         'error_type':result['error_type'],'cleanup_error_type':result['cleanup_error_type']},terminal=True)
        except BaseException as exc:
            result['status']='failed'
            if result['error_type'] is None:result['error_type']=type(exc).__name__
        try:
            journal.close()
        except BaseException as exc:
            result['status']='failed'
            if result['error_type'] is None:result['error_type']=type(exc).__name__
        write_json(output/'result.json',result)
    return 0 if result['status']=='complete' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',required=True,choices=['canary','run-001','run-002'])
    parser.add_argument('--admission',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--canary-result')
    parser.add_argument('--previous-result')
    parser.add_argument('--receiver',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--fd',type=int,help=argparse.SUPPRESS)
    parser.add_argument('--nonce',help=argparse.SUPPRESS)
    parser.add_argument('--started',type=float,help=argparse.SUPPRESS)
    args=parser.parse_args()
    started=time.monotonic()
    frozen=freeze()
    admission=admit(args.admission,args.mode,frozen,args.canary_result,args.previous_result)
    if args.receiver:
        require(type(args.fd) is int and args.fd>=3 and args.nonce is not None
                and len(args.nonce)==64 and args.started is not None,'receiver launch contract')
        return receiver(args,frozen,admission)
    require(args.fd is None and args.nonce is None and args.started is None,'unexpected child arguments')
    return driver(args,frozen,admission,started)


if __name__=='__main__':
    raise SystemExit(main())
