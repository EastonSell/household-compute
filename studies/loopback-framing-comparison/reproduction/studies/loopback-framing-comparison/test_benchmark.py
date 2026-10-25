"""Pure fixture, fake-clock, admission and accounting tests, with sockets denied."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import benchmark as b


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.no_socket = patch('socket.socket', side_effect=AssertionError('no real sockets in preparation'))
        self.no_spawn = patch('subprocess.Popen', side_effect=AssertionError('no child in preparation'))
        self.no_socket.start(); self.no_spawn.start()
        self.addCleanup(self.no_socket.stop); self.addCleanup(self.no_spawn.stop)

    def test_fixtures_retain_prior_exact_sizes_and_bytes(self):
        codecs, cases = b.build_cases()
        self.assertEqual([len(cases['baseline'][name].pack()) for name in b.CASES],
                         [2368, 36928, 147520, 196676])
        for name in b.CASES:
            self.assertIs(cases['baseline'][name].payload, cases['candidate'][name].payload)
            self.assertEqual(cases['baseline'][name].pack(), cases['candidate'][name].pack())
        self.assertEqual(hashlib.sha256(Path(b.CODEC_PATHS['candidate']).read_bytes()).hexdigest(),
                         '0cde18f73e790b7e7f600bf1dc25f6a9059e2a6289396584698bee0f6e77a58b')

    def test_full_fixed_denominator_and_balanced_pairing(self):
        plan = b.schedule('run-001')
        self.assertEqual(len(plan), 88)
        self.assertEqual(sum(x['iterations'] for x in plan if x['phase']=='measure'), 800)
        self.assertEqual(sum(x['iterations'] for x in plan if x['phase']=='warmup'), 16)
        for case in b.CASES:
            orders = [[x['variant'] for x in plan if x['block']==block and x['case']==case
                       and x['phase']=='measure'] for block in range(10)]
            self.assertEqual(orders.count(['baseline','candidate']), 5)
            self.assertEqual(orders.count(['candidate','baseline']), 5)
        self.assertEqual(b.schedule('run-002'), plan)

    def test_canary_has_no_measured_rows(self):
        plan = b.schedule('canary')
        self.assertEqual(len(plan), 8)
        self.assertEqual({x['phase'] for x in plan}, {'canary'})
        self.assertEqual(sum(x['iterations'] for x in plan), 8)
        with self.assertRaises(ValueError): b.schedule('other')

    def test_timer_wraps_all_operations_and_not_checks(self):
        log = []
        values = iter([100, 170])
        def clock(): log.append('clock'); return next(values)
        def op(i): log.append(i)
        self.assertEqual(b.measure(op, 3, clock), 70)
        self.assertEqual(log, ['clock', 0, 1, 2, 'clock'])

    def test_timer_rejects_nonpositive_and_boolean_intervals(self):
        for clocks in ([1,1],[2,1],[False,True]):
            with self.assertRaises(ValueError): b.measure(lambda _: None, 1, iter(clocks).__next__)

    def test_wrong_ack_rejected(self):
        b.check_ack(b.ACK.pack(b'ACK1', 2, 3, 2368), 2, 3, 2368)
        for args in [(b'BAD1',2,3,2368),(b'ACK1',1,3,2368),(b'ACK1',2,4,2368),(b'ACK1',2,3,2369)]:
            with self.assertRaises(ValueError): b.check_ack(b.ACK.pack(*args), 2, 3, 2368)

    def test_missing_admission_fails_before_sockets(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises((ValueError, FileNotFoundError)):
                b.admit(Path(d)/'absent.json', 'canary', '0'*64, None, None)

    def test_admission_bound_to_exact_stage_and_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'admit.json'
            p.write_text(json.dumps({'schema':1,'stage':'canary','freeze_sha256':'a'*64}))
            receipt = b.admit(p, 'canary', 'a'*64, None, None)
            self.assertEqual(receipt['stage'], 'canary')
            with self.assertRaises(ValueError): b.admit(p, 'canary', 'b'*64, None, None)
            with self.assertRaises(ValueError): b.admit(p, 'run-001', 'a'*64, None, None)

    def test_strict_json_rejects_duplicates_and_nonfinite(self):
        for raw in ('{"schema":1,"schema":1}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError): b.loads(raw)

    def test_exclusive_output_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'result.json'
            b.write_json(p, {'a':1})
            with self.assertRaises(FileExistsError): b.write_json(p, {'a':2})
            self.assertEqual(json.loads(p.read_text()), {'a':1})

    def test_output_size_rejected_without_creating_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'big.json'
            with self.assertRaises(ValueError): b.write_json(p, {'a':'a'*(1024*1024)})
            self.assertFalse(p.exists())

    def test_journal_reserves_terminal_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'journal.jsonl'
            j = b.Journal(p)
            j.add({'event':'start'})
            with self.assertRaises(ValueError): j.add({'event':'row','value':'x'*(1024*1024)})
            j.add({'event':'terminal','status':'failed'}, terminal=True)
            j.close()
            self.assertEqual(len(p.read_text().splitlines()), 2)
            with self.assertRaises(FileExistsError): b.Journal(p)


    def test_real_codec_receiver_handles_fragmented_synthetic_session(self):
        codecs,cases=b.build_cases()
        script=bytearray()
        for row in b.schedule('canary'):
            script.extend(b.CONTROL.pack(b'CMD1',row['index']))
            script.extend(cases[row['variant']][row['case']].pack())
        script.extend(b.CONTROL.pack(b'DONE',8))
        class MemoryIO:
            def __init__(self):self.sent=self.received=0;self.output=bytearray()
            def read(self,n,end):
                part=bytes(script[:min(n,37)]);del script[:len(part)]
                self.received+=len(part)
                if not part:raise EOFError()
                return part
            def read_exact(self,n,end):
                value=bytearray()
                while len(value)<n:value.extend(self.read(n-len(value),end))
                return bytes(value)
            def send_all(self,data,end):self.sent+=len(data);self.output.extend(data)
        io=MemoryIO();records=[]
        with patch.object(b.time,'monotonic',return_value=0):
            b.receive_session(io,'canary',codecs,cases,85,records)
        self.assertEqual(len(records),8)
        self.assertFalse(script)
        self.assertEqual(io.received,767056)
        self.assertEqual(io.sent,200)
        self.assertEqual(io.output[-8:],b.CONTROL.pack(b'DONE',8))

    def test_receiver_retains_preceding_commands_after_later_failure(self):
        codecs,cases=b.build_cases();row=b.schedule('canary')[0]
        script=bytearray(b.CONTROL.pack(b'CMD1',0)+cases['baseline'][row['case']].pack()+b'BAD!0000')
        class MemoryIO:
            sent=received=0
            def read(self,n,end):
                value=bytes(script[:n]);del script[:n];self.received+=len(value);return value
            def read_exact(self,n,end):return self.read(n,end)
            def send_all(self,data,end):self.sent+=len(data)
        records=[];progress={}
        with patch.object(b.time,'monotonic',return_value=0):
            with self.assertRaises(ValueError):b.receive_session(MemoryIO(),'canary',codecs,cases,85,records,progress)
        self.assertEqual(progress['inflight']['index'],1)
        self.assertEqual(progress['inflight']['stage'],'control')
        self.assertEqual(progress['inflight']['received'],8)
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['received'],2368)

    def _drive_with_doubles(self, fault=None):
        codecs,cases=b.build_cases()
        commands=[dict(row,sent=(64+len(cases[row['variant']][row['case']].payload))*row['iterations'],
                       received=16*row['iterations']) for row in b.schedule('canary')]
        replies=bytearray(b'HELLOACK')
        for row in commands:
            replies.extend(b.CONTROL.pack(b'RDY1',row['index']))
            replies.extend(b.ACK.pack(b'ACK1',row['index'],0,row['sent']))
        replies.extend(b.CONTROL.pack(b'DONE',8))
        class Sock:
            closed=False
            def setblocking(self,x):pass
            def bind(self,x):
                if x!=('127.0.0.1',0):raise AssertionError('bad bind')
            def listen(self,x):
                if x!=1:raise AssertionError('bad backlog')
            def getsockname(self):return ('127.0.0.1',12345)
            def fileno(self):return 99
            def setsockopt(self,*args):pass
            def close(self):
                self.closed=True
                if getattr(self,'fail_close',False):raise OSError('scripted close failure')
        class IO:
            sent=received=0
            def write(self,data,end):self.sent+=len(data);return len(data)
            def send_all(self,data,end):self.sent+=len(data)
            def read_exact(self,n,end):
                value=bytes(replies[:n]);del replies[:n];self.received+=len(value);return value
        class Child:
            pid=12345;returncode=None
            def poll(self):return self.returncode
            def wait(self,timeout):self.returncode=0;return 0
            def terminate(self):raise AssertionError('unexpected signal')
            def kill(self):raise AssertionError('unexpected signal')
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'new';a=Namespace(output=str(output),mode='canary',admission=str(Path(d)/'admit.json'),
                                          canary_result=None,previous_result=None)
            sockets=[Sock(),Sock()];child=Child();io=IO();budget_type=b.adapter.Budget
            sockets[1].fail_close=(fault=='close')
            original_add=b.Journal.add
            def journal_add(journal,event,terminal=False):
                if fault=='journal' and event['event']=='untimed':raise OSError('scripted journal failure')
                if fault=='terminal' and event['event']=='terminal':raise OSError('scripted terminal failure')
                return original_add(journal,event,terminal)
            def spawn(*args,**kwargs):
                receiver={'status':'complete','mode':'canary','freeze_sha256':'a'*64,
                          'commands':[dict(row,sent=row['received'],received=row['sent']) for row in commands],
                          'totals':{'sent':208,'received':767088},
                          'candidate_native':codecs['candidate']._NATIVE_FP32_LE,'error_type':None}
                b.write_json(output/'receiver.json',receiver)
                return child
            with patch.object(b.socket,'socket',side_effect=sockets),patch.object(b.subprocess,'Popen',side_effect=spawn),\
                 patch.object(b.adapter,'connect',return_value=io),patch.object(b,'freeze',return_value='a'*64),\
                 patch.object(b.time,'monotonic',return_value=.1),\
                 patch.object(b.adapter,'Budget',side_effect=lambda *a,**k:budget_type(clock=lambda:.1)),\
                 patch.object(b.Journal,'add',journal_add),\
                 patch.object(b,'admit',return_value={'stage':'canary','admission_sha256':'b'*64,\
                     'canary_result_sha256':None,'previous_result_sha256':None}):
                status=b.driver(a,'a'*64,{'stage':'canary','admission_sha256':'b'*64,
                                        'canary_result_sha256':None,'previous_result_sha256':None},0)
            self.assertEqual(status,1 if fault else 0)
            self.assertTrue(all(s.closed for s in sockets))
            result=json.loads((output/'result.json').read_text())
            self.assertEqual(result['rows'],[])
            self.assertTrue(result['cleanup']['reaped'])
            self.assertEqual(result['cleanup']['returncode'],0)
            if fault!='journal':self.assertEqual(result['totals'],{'sent':767088,'received':208})
            else:self.assertEqual(result['totals'],{'sent':2408,'received':32})

    def test_driver_canary_closes_and_reaps_with_socket_free_doubles(self):
        self._drive_with_doubles()

    def test_driver_journal_failure_still_reaps_owned_child(self):
        self._drive_with_doubles('journal')

    def test_driver_terminal_journal_failure_still_writes_result(self):
        self._drive_with_doubles('terminal')

    def test_driver_socket_close_failure_still_reaps_owned_child(self):
        self._drive_with_doubles('close')


if __name__ == '__main__': unittest.main()
