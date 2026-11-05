"""Offline fixture tests for six-panel input readiness and its actual HTML output."""
import base64
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TEST_ROOT = Path(__file__).resolve().parent
SCRIPTS = TEST_ROOT.parent / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import common
import report


class ReviewHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.figures = []
        self.figure = None
        self.table = False
        self.rows = []
        self.row = None
        self.cell = None
        self.in_prompt_data = False
        self.prompt_data = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'figure' and 'storyboard-figure' in attrs.get('class', '').split():
            self.figure = {}
        if self.figure is not None and tag == 'a':
            self.figure['href'] = attrs.get('href')
        if self.figure is not None and tag == 'img':
            self.figure['src'] = attrs.get('src')
        if tag == 'table' and attrs.get('id', '').startswith('storyboard-anchors-'):
            self.table = True
        if self.table and tag == 'tr':
            self.row = []
        if self.table and tag == 'td':
            self.cell = ''
        if tag == 'script' and attrs.get('id') == 'prompt-data':
            self.in_prompt_data = True

    def handle_endtag(self, tag):
        if tag == 'figure' and self.figure is not None:
            self.figures.append(self.figure)
            self.figure = None
        if self.table and tag == 'td':
            self.row.append(self.cell)
            self.cell = None
        if self.table and tag == 'tr':
            if self.row:
                self.rows.append(self.row)
            self.row = None
        if tag == 'table':
            self.table = False
        if tag == 'script':
            self.in_prompt_data = False

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data
        if self.in_prompt_data:
            self.prompt_data += data


class StoryboardReportingTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='storyboard_fixture_', dir=TEST_ROOT)
        self.project = Path(self.temp.name).resolve()
        self.addCleanup(self.cleanup_fixture)
        (self.project / 'workflow.json').write_text('{}', encoding='utf-8')
        # A real one-pixel PNG is enough for input/HTML plumbing; no generation.
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG1cAAAAASUVORK5CYII=')
        for name in ('actor.png', 'board.png', 'environment.png'):
            (self.project / name).write_bytes(png)
        self.cfg = dict(workflow=str(self.project / 'workflow.json'), configuration_issues=[])
        self.setting_patch = patch.object(common, 'settings', return_value=self.cfg)
        self.setting_patch.start()
        self.addCleanup(self.setting_patch.stop)
        self.film = dict(
            title='Test <film>', duration_seconds=7, audio_mode='h3_native', script='A complete fixture story.',
            characters=[dict(id='A', name='Actor')],
            assets=[dict(id='ACTOR',kind='image',path='actor.png',role='identity'),
                    dict(id='BOARD',kind='image',path='board.png',role='six-panel planning'),
                    dict(id='ENV',kind='image',path='environment.png',role='environment')],
            segments=[dict(id='U01',mode='Ref2VA',edit_seconds=7,source_frames=175,
                shots=[dict(id=1,duration_seconds=3,action='First action.',camera='Fixed wide view.'),
                       dict(id='S2',duration_seconds=4,action='Next action.',camera='Follow the actor.')],
                storyboard_asset_id='BOARD',
                panels=[dict(index=i,time_seconds=t,shot='1' if i<=3 else 'S2',
                             action='Action <b>is text</b> & remains exact.',camera='Camera '+str(i))
                        for i,t in enumerate([0,.6,1.8,3.1,4.2,6.6],1)],
                references=[dict(label='Picture 1',asset_id='ACTOR'),
                            dict(label='Picture 2',asset_id='BOARD'),
                            dict(label='Picture 3',asset_id='ENV')],
                prompt_en='subject_definitions:\n<Subject 1> & "exact"\n[Shot 1]  keep  spacing\n',
                prompt_zh='中文原稿 <标签> & 符号\n换行。\n')])

    def cleanup_fixture(self):
        # Check the target before the recursive cleanup performed by tempfile.
        if not self.project.is_relative_to(TEST_ROOT.resolve()):
            raise RuntimeError('Fixture cleanup escaped the intended tests directory')
        self.temp.cleanup()

    def save_film(self, film=None):
        common.save(self.project / 'film.json', self.film if film is None else film)

    def test_valid_board_uses_numeric_and_string_shot_ids(self):
        self.assertEqual(common.ready_errors(self.project, self.film), [])

    def test_invalid_boards_block_approval(self):
        changes = [
            ('five panels', lambda s,f: s['panels'].pop()),
            ('unordered index', lambda s,f: s['panels'][2].update(index=4)),
            ('bool index', lambda s,f: s['panels'][0].update(index=True)),
            ('equal time', lambda s,f: s['panels'][2].update(time_seconds=.6)),
            ('nan time', lambda s,f: s['panels'][2].update(time_seconds=float('nan'))),
            ('infinite time', lambda s,f: s['panels'][2].update(time_seconds=float('inf'))),
            ('bool time', lambda s,f: s['panels'][0].update(time_seconds=False)),
            ('nonzero opening', lambda s,f: s['panels'][0].update(time_seconds=.1)),
            ('last outside edit', lambda s,f: s['panels'][-1].update(time_seconds=7)),
            ('unknown shot', lambda s,f: s['panels'][2].update(shot='S99')),
            ('empty action', lambda s,f: s['panels'][2].update(action='  ')),
            ('empty camera', lambda s,f: s['panels'][2].update(camera='')),
            ('unknown board', lambda s,f: s.update(storyboard_asset_id='MISSING')),
            ('empty board', lambda s,f: s.update(storyboard_asset_id='')),
            ('board not image', lambda s,f: f['assets'][1].update(kind='video')),
            ('missing actual board', lambda s,f: f['assets'][1].update(path='absent.png')),
            ('unbound board', lambda s,f: s['references'].pop(1)),
        ]
        for label, change in changes:
            with self.subTest(label=label):
                film = copy.deepcopy(self.film)
                change(film['segments'][0], film)
                self.assertTrue(common.ready_errors(self.project, film))
                self.save_film(film)
                with self.assertRaisesRegex(ValueError, 'Not approvable'):
                    report.approve(self.project, 'TEST_ONLY simulated fixture consent')
                self.assertFalse((self.project / 'approval.json').exists())

    def test_report_has_original_image_and_six_dynamic_mapping_rows(self):
        self.save_film()
        manifest = report.render(self.project)
        self.assertTrue(manifest['ready'])
        text = (self.project / 'review/index.html').read_text(encoding='utf-8')
        parsed = ReviewHTML()
        parsed.feed(text)
        self.assertEqual(len(parsed.figures), 1)
        self.assertEqual(parsed.figures[0]['href'], parsed.figures[0]['src'])
        board = next(a for a in manifest['assets'] if a['id']=='BOARD')
        self.assertEqual(parsed.figures[0]['src'], board['report_path'])
        self.assertTrue((self.project/'review'/board['report_path']).is_file())
        self.assertEqual(len(parsed.rows), 6)
        self.assertEqual([r[0] for r in parsed.rows], ['00:00.000','00:00.600','00:01.800','00:03.100','00:04.200','00:06.600'])
        self.assertEqual([r[1] for r in parsed.rows], [f'<Picture 2> 第{i}格' for i in range(1,7)])
        self.assertEqual([r[2] for r in parsed.rows], ['1','1','1','S2','S2','S2'])
        self.assertEqual(parsed.rows[0][3], self.film['segments'][0]['panels'][0]['action'])
        self.assertNotIn('<b>is text</b>', text)
        self.assertEqual(json.loads(parsed.prompt_data),
                         {'U01_prompt_en':self.film['segments'][0]['prompt_en'],
                          'U01_prompt_zh':self.film['segments'][0]['prompt_zh']})
        self.assertEqual(common.read(self.project/'film.json'), self.film)

    def test_invalid_panel_object_is_renderable_as_unapprovable_draft(self):
        self.film['segments'][0]['panels'][2] = 'broken entry'
        self.save_film()
        m = report.render(self.project)
        self.assertFalse(m['ready'])
        self.assertIn('故事板格记录格式有误', (self.project/'review/index.html').read_text(encoding='utf-8'))

    def test_legacy_without_mode_marker_remains_approvable(self):
        self.film['segments'][0].pop('storyboard_asset_id')
        # Older projects may carry their own advisory panel formats.
        self.film['segments'][0]['panels'] = 'legacy advisory data'
        self.save_film()
        self.assertEqual(common.ready_errors(self.project,self.film), [])
        self.assertTrue(report.render(self.project)['ready'])
        approval = report.approve(self.project, 'TEST_ONLY simulated fixture consent')
        self.assertEqual(common.require_approval(self.project,self.film), approval)
        parsed = ReviewHTML()
        parsed.feed((self.project/'review/index.html').read_text(encoding='utf-8'))
        self.assertEqual(parsed.figures, [])
        self.assertEqual(parsed.rows, [])

    def test_panel_revision_invalidates_only_its_segment_authorization(self):
        self.save_film()
        report.render(self.project)
        report.approve(self.project,'TEST_ONLY simulated fixture consent')
        self.film['segments'][0]['panels'][3]['action'] = 'Changed actual planned action.'
        self.save_film()
        with self.assertRaisesRegex(ValueError,'Approval is stale for U01'):
            common.require_approval(self.project,self.film)


if __name__ == '__main__':
    unittest.main(verbosity=2)
