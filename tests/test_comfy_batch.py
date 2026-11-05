"""Behavioral tests using an in-memory backend; no network or GPU calls."""
import copy
import base64
from contextlib import ExitStack
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
batch=importlib.import_module('comfy_batch')


class Backend:
    def __init__(self, ids=('A','B','C'), dependencies=None):
        dependencies=dependencies or {}
        self.film={'title':'test','segments':[dict(id=sid,edit_seconds=5,source_frames=124,
            prompt_en='authored',references=[],continuity_from=dependencies.get(sid)) for sid in ids]}
        self.state={'jobs':{}}
        self.approved_ids=set(ids)
        self.events=[]
        self.approval_reads=[]
        self.clock=0
        self.stall=set()
        self.uncertain=set()

    def load_state(self,p):
        return copy.deepcopy(self.state)

    def approved(self,p,sid,**kwargs):
        self.approval_reads.append(sid)
        if sid not in self.approved_ids:
            raise ValueError('No approval: '+sid)
        return self.film,{'records':{},'segment_ids':list(self.approved_ids)},{},'digest'

    def prepare(self,p,sid):
        self.events.append(('prepare',sid))
        assert sid not in self.state['jobs'], 'No implicit take replacement'
        self.state['jobs'][sid]={'segment_id':sid,'status':'prepared'}
        return copy.deepcopy(self.state['jobs'][sid])

    def submit(self,p,sid,execute=False):
        assert execute
        self.events.append(('submit',sid))
        j=self.state['jobs'][sid]
        assert j['status']=='prepared'
        if sid in self.uncertain:
            j.update(status='submission_uncertain',requested_prompt_id='requested-'+sid)
            raise OSError('POST response was lost')
        j.update(status='submitted',prompt_id='pid-'+sid)
        return copy.deepcopy(j)

    def collect(self,p,sid):
        self.events.append(('collect',sid))
        j=self.state['jobs'][sid]
        assert j['status'] in batch.ACTIVE
        if sid not in self.stall:
            j['status']='downloaded'
        return copy.deepcopy(j)

    def sleep(self,seconds):
        self.clock+=seconds

    def patches(self):
        stack=ExitStack()
        targets=[
            (batch.common,'load_film',lambda p:copy.deepcopy(self.film)),
            (batch.common,'ready_errors',lambda *a,**k:[]),
            (batch.run,'inspect_project',lambda p:{'segments':[{'id':s['id']} for s in self.film['segments']],'configuration_issues':[]}),
            (batch.run,'load_state',self.load_state),
            (batch.run,'approved',self.approved),
            (batch.run,'approved_segment',lambda *a:None),
            (batch.run,'references',lambda *a:[]),
            (batch.run,'continuity_label',lambda *a:'Picture 1'),
            (batch.run,'validate_prompt_references',lambda *a:None),
            (batch.run,'job_matches',lambda *a:None),
            (batch.run,'validate_continuity',lambda *a:None),
            (batch.run,'prepare',self.prepare),
            (batch.run,'submit',self.submit),
            (batch.run,'collect',self.collect),
            (batch.run,'assemble',lambda *a,**k:{'output':k['output']}),
            (batch.time,'monotonic',lambda:self.clock),
            (batch.time,'sleep',self.sleep),
        ]
        for obj,name,value in targets:
            stack.enter_context(patch.object(obj,name,value))
        stack.enter_context(patch('builtins.print'))
        return stack


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='batch_behavior_',dir=Path(__file__).parent)
        self.project=Path(self.temp.name)

    def tearDown(self):
        if not self.project.resolve().is_relative_to(Path(__file__).parent.resolve()):
            raise RuntimeError('Fixture cleanup escaped the tests directory')
        self.temp.cleanup()

    def run_with(self,fake,**kw):
        with fake.patches():
            return batch.run_batch(self.project,poll_seconds=1,wait_seconds=10,**kw)

    def test_offline_inspection_has_no_prepare_submit_collect_or_status_write(self):
        f=Backend()
        result=self.run_with(f)
        self.assertEqual(result['phase'],'offline_ready')
        self.assertEqual(result['segment_ids'],['A','B','C'])
        self.assertEqual(f.events,[])
        self.assertFalse((self.project/'execution').exists())

    def test_all_independent_jobs_submit_before_first_collect(self):
        f=Backend()
        result=self.run_with(f,execute=True)
        first_collect=next(i for i,x in enumerate(f.events) if x[0]=='collect')
        self.assertEqual([x for x in f.events[:first_collect] if x[0]=='submit'],
                         [('submit','A'),('submit','B'),('submit','C')])
        self.assertEqual(result['phase'],'complete')
        saved=json.loads((self.project/'execution/batch-status.json').read_text(encoding='utf-8'))
        self.assertEqual([x['prompt_id'] for x in saved['jobs']],['pid-A','pid-B','pid-C'])

    def test_real_dependency_waits_but_unrelated_job_does_not(self):
        f=Backend(dependencies={'B':'A'})
        result=self.run_with(f,execute=True)
        first_collect=next(i for i,x in enumerate(f.events) if x[0]=='collect')
        self.assertEqual([x for x in f.events[:first_collect] if x[0]=='submit'],
                         [('submit','A'),('submit','C')])
        self.assertLess(f.events.index(('collect','A')),f.events.index(('prepare','B')))
        self.assertEqual(result['phase'],'complete')

    def test_any_missing_approval_blocks_entire_selected_scope_before_upload(self):
        f=Backend()
        f.approved_ids.remove('B')
        result=self.run_with(f,execute=True)
        self.assertEqual(result['phase'],'not_ready')
        self.assertTrue(any('No approval: B' in e for e in result['errors']))
        self.assertEqual(f.events,[])

    def test_recovery_uses_frozen_ids_without_loading_current_draft_or_approval(self):
        f=Backend(ids=('A','B'))
        f.state['jobs']={'A':{'status':'submitted','prompt_id':'original-A'},
                         'B':{'status':'submission_uncertain','requested_prompt_id':'original-B'}}
        with f.patches(),patch.object(batch.common,'load_film',side_effect=AssertionError('Current draft must not be loaded')):
            result=batch.run_batch(self.project,recover=True,poll_seconds=1)
        self.assertEqual(result['phase'],'complete')
        self.assertEqual(f.events,[('collect','A'),('collect','B')])
        self.assertEqual(f.approval_reads,[])
        self.assertEqual([x['prompt_id'] for x in result['jobs']],['original-A','original-B'])

    def test_recovery_missing_task_is_not_prepared(self):
        f=Backend()
        f.state['jobs']={'A':{'status':'submitted','prompt_id':'pid-A'}}
        with self.assertRaisesRegex(ValueError,'requires existing'):
            self.run_with(f,recover=True,segment_ids=['A','B'])
        self.assertEqual(f.events,[])

    def test_recovery_without_frozen_prompt_id_reports_missing_task(self):
        f=Backend(ids=('A',))
        f.state['jobs']['A']={'status':'submitted'}
        result=self.run_with(f,recover=True)
        self.assertEqual(result['phase'],'needs_attention')
        self.assertIn('Missing frozen prompt ID',result['errors']['A'])
        self.assertEqual(f.events,[])

    def test_failed_take_and_its_dependency_are_not_replaced(self):
        f=Backend(dependencies={'B':'A'})
        f.state['jobs']['A']={'status':'failed','prompt_id':'failed-A'}
        result=self.run_with(f,execute=True)
        self.assertEqual(result['phase'],'needs_attention')
        self.assertEqual(set(result['errors']),{'A','B'})
        self.assertEqual(f.events,[('prepare','C'),('submit','C'),('collect','C')])
        self.assertEqual(f.state['jobs']['A']['prompt_id'],'failed-A')

    def test_uncertain_post_is_collected_without_second_post(self):
        f=Backend(ids=('A',))
        f.uncertain.add('A')
        result=self.run_with(f,execute=True)
        self.assertEqual(result['phase'],'complete')
        self.assertEqual(f.events.count(('submit','A')),1)
        self.assertEqual(result['jobs'][0]['prompt_id'],'requested-A')

    def test_selected_scope_completes_without_touching_other_segments(self):
        f=Backend()
        result=self.run_with(f,execute=True,segment_ids=['B'])
        self.assertEqual(result['segment_ids'],['B'])
        self.assertEqual(set(f.state['jobs']),{'B'})
        self.assertEqual(result['phase'],'complete')

    def test_partial_scope_cannot_be_assembled_as_full_film(self):
        f=Backend()
        with self.assertRaisesRegex(ValueError,'complete film scope'):
            self.run_with(f,execute=True,segment_ids=['B'],assemble='output/full.mp4')
        self.assertEqual(f.events,[])

    def test_external_dependency_must_be_downloaded_before_any_selected_upload(self):
        f=Backend(dependencies={'B':'A'})
        f.state['jobs']['A']={'status':'submitted','prompt_id':'pid-A'}
        result=self.run_with(f,execute=True,segment_ids=['B','C'])
        self.assertEqual(result['phase'],'not_ready')
        self.assertTrue(any('predecessor outside this scope' in e for e in result['errors']))
        self.assertEqual(f.events,[])

    def test_timeout_preserves_id_and_does_not_repeat_gpu_post(self):
        f=Backend(ids=('A',))
        f.stall.add('A')
        with f.patches():
            result=batch.run_batch(self.project,execute=True,poll_seconds=1,wait_seconds=2)
        self.assertEqual(result['phase'],'waiting_timeout')
        self.assertEqual(result['jobs'][0]['prompt_id'],'pid-A')
        self.assertEqual(f.events.count(('submit','A')),1)
        self.assertEqual(f.state['jobs']['A']['status'],'submitted')

    def test_prepared_submits_once_and_downloaded_is_reused(self):
        f=Backend(ids=('A','B'))
        f.state['jobs']={'A':{'status':'prepared'},'B':{'status':'downloaded','prompt_id':'old-B'}}
        result=self.run_with(f,execute=True)
        self.assertEqual(result['phase'],'complete')
        self.assertEqual(f.events,[('submit','A'),('collect','A')])
        self.assertEqual(result['jobs'][1]['prompt_id'],'old-B')

    def test_full_film_assembly_occurs_only_after_every_download(self):
        f=Backend()
        with f.patches(),patch.object(batch.run,'assemble',side_effect=lambda *a,**k:
                f.events.append(('assemble',k['output'])) or {'output':k['output']}):
            result=batch.run_batch(self.project,execute=True,poll_seconds=1,assemble='output/full.mp4')
        self.assertEqual(result['assembly']['output'],'output/full.mp4')
        self.assertEqual(f.events[-1],('assemble','output/full.mp4'))
        self.assertEqual([j['status'] for j in result['jobs']],['downloaded']*3)

    def test_actual_offline_legacy_preflight_preserves_approval_bytes(self):
        # All normal planning/authorization/file APIs run; any network/process is forbidden.
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG1cAAAAASUVORK5CYII=')
        (self.project/'board.png').write_bytes(png)
        film=dict(title='Legacy approval fixture',script='Full fixture story.',audio_mode='h3_native',
            assets=[dict(id='BOARD',kind='image',path='board.png')],characters=[],
            segments=[dict(id='U01',mode='Ref2VA',edit_seconds=5,source_frames=124,
                storyboard_asset_id='BOARD',references=[dict(label='Picture 1',asset_id='BOARD')],
                prompt_en='<Picture 1> is the six-panel storyboard.',prompt_zh='图1是六宫格故事板。',
                shots=[dict(id=1,action='A simple walk.',camera='Fixed wide view.')],
                panels=[dict(index=i,time_seconds=t,shot=1,action='Walk '+str(i),camera='Fixed wide view.')
                        for i,t in enumerate([0,.8,1.8,2.6,3.8,4.8],1)])])
        batch.common.save(self.project/'film.json',film)
        review=self.project/'review/index.html';review.parent.mkdir();review.write_text('<html>Old reviewed package fixture</html>',encoding='utf8')
        legacy=dict(segment_ids=['U01'],user_confirmation='TEST_ONLY actual legacy approval fixture',
                    review_digest=batch.common.review_digest(self.project,film),html_sha256=batch.common.sha(review))
        batch.common.save(self.project/'approval.json',legacy)
        before=(self.project/'approval.json').read_bytes()
        with (patch.object(batch.run.urllib.request,'urlopen',side_effect=AssertionError('No network')),
              patch.object(batch.run.subprocess,'run',side_effect=AssertionError('No media process'))):
            result=batch.run_batch(self.project)
        self.assertEqual(result['phase'],'offline_ready',result)
        self.assertEqual(result['segment_ids'],['U01'])
        self.assertEqual((self.project/'approval.json').read_bytes(),before)
        self.assertFalse((self.project/'execution').exists())


if __name__=='__main__':
    unittest.main()
