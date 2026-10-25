"""Entirely invented artifacts, not empirical observations."""
import copy
import unittest
import benchmark as b
import verify_results as v


def synthetic(mode='run-001'):
    codecs,cases=b.build_cases()
    commands=[]; rows=[]; events=[]
    for plan in b.schedule(mode):
        frame_bytes=64+len(cases[plan['variant']][plan['case']].payload)
        command=dict(plan,sent=frame_bytes*plan['iterations'],received=16*plan['iterations'])
        commands.append(command)
        if plan['phase']=='measure':
            row=dict(command,wall_ns=100000+1000*plan['index'],wall_ns_per_exchange=(100000+1000*plan['index'])/10)
            rows.append(row); events.append({'event':'row','row':row})
        else: events.append({'event':'untimed','command':command})
    cleanup={'pid':12345,'returncode':0,'terminated':False,'killed':False,'reaped':True}
    result={'schema':1,'status':'complete','mode':mode,'freeze_sha256':'a'*64,
            'admission':{'stage':'canary' if mode=='canary' else 'collection','admission_sha256':'b'*64,
                         'canary_result_sha256':None if mode=='canary' else 'c'*64,'previous_result_sha256':None},
            'instance_id':'2b37ef61-0000-4000-8000-000000000001',
            'started_at_utc':'2026-10-25T00:00:00+00:00','finished_at_utc':'2026-10-25T00:00:02+00:00',
            'elapsed_seconds':3.,'environment':b.environment(codecs),'fixtures':b.fixture_metadata(cases),
            'rows':rows,'commands':commands,
            'totals':{'sent':32+8+8*len(commands)+sum(x['sent'] for x in commands),
                      'received':8+8+8*len(commands)+sum(x['received'] for x in commands)},
            'inflight':None,'cleanup':cleanup,'owned_child_pid':12345,'receiver_sha256':'d'*64,
            'error_type':None,'cleanup_error_type':None,'summary':b.summaries(rows)}
    receiver={'status':'complete','mode':mode,'freeze_sha256':'a'*64,
              'commands':[dict(x,sent=x['received'],received=x['sent']) for x in commands],
              'totals':{'sent':result['totals']['received'],'received':result['totals']['sent']},
              'inflight':None,'candidate_native':codecs['candidate']._NATIVE_FP32_LE,'error_type':None}
    journal=[{'event':'start','mode':mode,'freeze_sha256':'a'*64,'instance_id':result['instance_id']}]+events+[
        {'event':'terminal','status':'complete','rows':len(rows),'commands':len(commands),
         'cleanup':cleanup,'error_type':None,'cleanup_error_type':None}]
    return result,copy.deepcopy(receiver),copy.deepcopy(journal)


class VerifierTests(unittest.TestCase):
    def test_accepts_complete_invented_run_and_canary(self):
        for mode in ('canary','run-001'):
            result,receiver,journal=synthetic(mode)
            self.assertEqual(v.verify_data(result,receiver,journal,'a'*64),
                             {'mode':mode,'rows':0 if mode=='canary' else 80,'commands':8 if mode=='canary' else 88})

    def test_rejects_missing_duplicate_and_reordered_rows(self):
        for mutate in (lambda r:r['rows'].pop(),lambda r:r['rows'].append(r['rows'][0]),
                       lambda r:r['rows'].reverse()):
            r,c,j=synthetic(); mutate(r)
            with self.assertRaises(ValueError):v.verify_data(r,c,j,'a'*64)

    def test_rejects_edited_pair_accounting_and_summary(self):
        for mutate in (lambda r:r['rows'][0].update(variant='candidate'),
                       lambda r:r['commands'][0].update(sent=1),
                       lambda r:r['summary'][0]['paired_ratio'].update(median=999),
                       lambda r:r['rows'][0].update(wall_ns=True),
                       lambda r:r['rows'][0].update(wall_ns_per_exchange=float('nan'))):
            r,c,j=synthetic(); mutate(r)
            with self.assertRaises(ValueError):v.verify_data(r,c,j,'a'*64)

    def test_rejects_missing_reap_escalation_and_receiver_failure(self):
        for mutate in (lambda r,c:r['cleanup'].update(reaped=False),
                       lambda r,c:r['cleanup'].update(terminated=True),
                       lambda r,c:r.update(owned_child_pid=999),
                       lambda r,c:c.update(status='failed'),
                       lambda r,c:c['commands'].pop()):
            r,c,j=synthetic(); mutate(r,c)
            with self.assertRaises(ValueError):v.verify_data(r,c,j,'a'*64)

    def test_rejects_changed_fixture_freeze_journal_and_extra_fields(self):
        for mutate in (lambda r,c,j:r['fixtures']['activation_decode'].update(frame_bytes=1),
                       lambda r,c,j:r.update(freeze_sha256='b'*64),
                       lambda r,c,j:j.pop(),
                       lambda r,c,j:r.update(extra=True),
                       lambda r,c,j:c.update(candidate_native=not c['candidate_native'])):
            r,c,j=synthetic(); mutate(r,c,j)
            with self.assertRaises(ValueError):v.verify_data(r,c,j,'a'*64)

    def test_rejects_boolean_integer_aliases_and_inflight_completion(self):
        for mutate in (lambda r,c,j:r['rows'][0].update(block=False),
                       lambda r,c,j:c['commands'][0].update(index=False),
                       lambda r,c,j:j[1]['command'].update(index=False),
                       lambda r,c,j:r.update(inflight={'index':0}),
                       lambda r,c,j:c.update(inflight={'index':0})):
            r,c,j=synthetic();mutate(r,c,j)
            with self.assertRaises(ValueError):v.verify_data(r,c,j,'a'*64)

    def test_rejects_nonpositive_inconsistent_intervals_and_canary_timings(self):
        for mutate in (lambda r:r.update(elapsed_seconds=True),
                       lambda r:r.update(elapsed_seconds=0.00001),
                       lambda r:r.update(finished_at_utc=r['started_at_utc']),
                       lambda r:r['rows'][0].update(wall_ns=0)):
            r,c,j=synthetic();mutate(r)
            with self.assertRaises(ValueError):v.verify_data(r,c,j,'a'*64)
        r,c,j=synthetic('canary');r['rows']=[{'wall_ns':1}]
        with self.assertRaises(ValueError):v.verify_data(r,c,j,'a'*64)

if __name__=='__main__':unittest.main()
