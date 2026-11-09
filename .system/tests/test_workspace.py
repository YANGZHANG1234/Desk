import importlib.util,json,tempfile,shutil,unittest,hashlib
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('phd',Path(__file__).parents[1]/'app/phd.py')
app=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(app)
LIVE=app.ROOT
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        for name in ['config','templates','context','app']:
            shutil.copytree(LIVE/'.system'/name,self.root/'.system'/name,ignore=shutil.ignore_patterns('__pycache__'))
        (self.root/'.system/index').mkdir();(self.root/'Materials/Research/Papers').mkdir(parents=True)
        app.ROOT=self.root;app.W=self.root/'Records';app.SYS=self.root/'.system'
    def tearDown(self):
        app.ROOT=LIVE;app.W=LIVE/'Records';app.SYS=LIVE/'.system';self.tmp.cleanup()
    def test_ui_workflow_persists_links_schedule_and_completion(self):
        wp=app.browser_action({'action':'create','type':'work-packages','fields':{'title':'Prepare research discussion','status':'proposed'}})['id']
        result=app.browser_action({'action':'create','type':'tasks','fields':{'title':'Read evidence','status':'todo','work_packages':[wp],'do_date':'2026-09-08'}})
        r=next(r for r in result['records'] if r['id']==result['id'])
        app.browser_action({'action':'update','id':r['id'],'revision':r['revision'],'fields':{'status':'done'}})
        saved=next(x for x in app.records() if x['id']==r['id'])
        self.assertEqual(saved['status'],'done');self.assertEqual(saved['work_packages'],[wp]);self.assertEqual(saved['do_date'],'2026-09-08')
        with self.assertRaises(RuntimeError):app.browser_action({'action':'update','id':r['id'],'revision':r['revision'],'fields':{'status':'todo'}})
    def test_ui_rejects_invalid_links_and_remote_calendar_without_mutation(self):
        before=len(app.records())
        for fields in [{'title':'Bad link','projects':['missing']},{'title':'Private','private':True,'calendar_target':'outlook'}]:
            with self.assertRaises(ValueError):app.browser_action({'action':'create','type':'planning','fields':fields})
        self.assertEqual(len(app.records()),before)
    def test_meeting_followup_and_short_title_persist(self):
        meeting=app.browser_action({'action':'create','type':'meetings','fields':{'title':'Research meeting','kind':'1:1'}})['id']
        response=app.browser_action({'action':'create','type':'tasks','fields':{'title':'Read the discussed evidence','display_title':'Read evidence','meetings':[meeting],'tags':['Reading']}})
        saved=next(r for r in app.records() if r['id']==response['id'])
        self.assertEqual(saved['meetings'],[meeting]);self.assertEqual(saved['display_title'],'Read evidence')
        self.assertEqual(saved['tags'],['Reading'])
    def test_partial_calendar_change_cannot_invert_time_range(self):
        response=app.browser_action({'action':'create','type':'planning','fields':{'title':'Reading','start_time':'2026-09-08T10:00','end_time':'2026-09-08T11:00'}})
        r=next(r for r in app.records() if r['id']==response['id'])
        with self.assertRaises(ValueError):
            app.browser_action({'action':'update','id':r['id'],'revision':r['revision'],'fields':{'start_time':'2026-09-08T12:00'}})
        self.assertEqual(next(x for x in app.records() if x['id']==r['id'])['revision'],r['revision'])
    def test_editing_completed_record_preserves_completion_date(self):
        response=app.browser_action({'action':'create','type':'tasks','fields':{'title':'Completed yesterday','status':'done'}})
        r=next(r for r in app.records() if r['id']==response['id']);p=app.ROOT/r['path']
        meta,body=app.read(p);meta['completed_date']='2026-09-01';p.write_text(app.serialize(meta,body))
        r=next(r for r in app.records() if r['id']==response['id'])
        app.browser_action({'action':'update','id':r['id'],'revision':r['revision'],'fields':{'body':'Additional notes'}})
        self.assertEqual(next(x for x in app.records() if x['id']==r['id'])['completed_date'],'2026-09-01')
    def test_delete_restore_preserves_linked_records_and_rejects_stale_edits(self):
        result=app.browser_action({'action':'create','type':'projects','fields':{'title':'Temporary project'}})
        project=next(r for r in result['records'] if r['id']==result['id'])
        task_result=app.browser_action({'action':'create','type':'tasks','fields':{'title':'Linked task','projects':[project['id']]}})
        app.browser_action({'action':'delete','id':project['id'],'revision':project['revision']})
        deleted=next(r for r in app.records() if r['id']==project['id'])
        self.assertTrue(deleted['deleted_at'])
        self.assertEqual(next(r for r in app.records() if r['id']==task_result['id'])['projects'],[project['id']])
        with self.assertRaises(RuntimeError):app.browser_action({'action':'restore','id':project['id'],'revision':project['revision']})
        with self.assertRaises(ValueError):app.browser_action({'action':'update','id':deleted['id'],'revision':deleted['revision'],'fields':{'title':'Accidental edit'}})
        app.browser_action({'action':'restore','id':deleted['id'],'revision':deleted['revision']})
        restored=next(r for r in app.records() if r['id']==project['id'])
        self.assertNotIn('deleted_at',restored);self.assertEqual(restored['title'],project['title'])
    def test_historical_completion_is_not_dated_by_edit_or_restore(self):
        response=app.browser_action({'action':'create','type':'tasks','fields':{'title':'Historical completion','status':'done'}})
        r=next(r for r in app.records() if r['id']==response['id']);p=app.ROOT/r['path']
        meta,body=app.read(p);meta.pop('completed_date');meta['completion_period']='historical';p.write_text(app.serialize(meta,body))
        for action,fields in [('update',{'body':'Clarification'}),('delete',{}),('restore',{})]:
            r=next(r for r in app.records() if r['id']==response['id'])
            app.browser_action({'action':action,'id':r['id'],'revision':r['revision'],'fields':fields})
            saved=next(r for r in app.records() if r['id']==response['id'])
            self.assertNotIn('completed_date',saved);self.assertEqual(saved['completion_period'],'historical')
    def test_project_hub_fields_and_nested_creation(self):
        response=app.browser_action({'action':'create','type':'projects','fields':{'title':'Hub','objective':'Compare methods'}})
        project=response['id']
        package=app.browser_action({'action':'create','type':'work-packages','fields':{'title':'Paper','deliverable':'Submitted manuscript','projects':[project]}})['id']
        result=app.browser_action({'action':'create','type':'meetings','fields':{'title':'Discussion','projects':[project],'work_packages':[package],'body':'## Agenda\nCompare methods\n\n## Decisions\n'}})
        meeting=next(r for r in app.records() if r['id']==result['id'])
        self.assertEqual(meeting['work_packages'],[package])
        self.assertEqual(next(r for r in app.records() if r['id']==package)['deliverable'],'Submitted manuscript')
        self.assertEqual(next(r for r in app.records() if r['id']==project)['objective'],'Compare methods')
    def test_paper_is_discovered_once(self):
        app.paper('test-paper','Test paper')
        rs=app.records();self.assertEqual(sum(r['id']=='paper-test-paper' for r in rs),1)
        app.new('journal','A useful discussion','paper-test-paper')
        self.assertTrue(any(r['projects']==['paper-test-paper'] for r in app.records()))
        with self.assertRaises(ValueError):app.paper('test-paper','Duplicate')
    def test_snapshot_provenance_and_source_preservation(self):
        src=self.root/'Materials/source.txt';src.write_text('original evidence')
        manifest=self.root/'selection.json';manifest.write_text(json.dumps({'items':[{'source':'Materials/source.txt','destination':'data/evidence.txt'}]}))
        app.snapshot(manifest,self.root/'Exports/test')
        m=json.loads((self.root/'Exports/test/PROVENANCE.json').read_text())
        self.assertEqual(m['files'][0]['sha256'],hashlib.sha256(src.read_bytes()).hexdigest())
        self.assertEqual(src.read_text(),'original evidence')
        with self.assertRaises(ValueError):app.snapshot(manifest,self.root/'Exports/test')
    def test_snapshot_rejects_traversal_and_symlink(self):
        src=self.root/'Materials/a';src.write_text('a')
        m=self.root/'selection.json';m.write_text(json.dumps({'items':[{'source':'Materials/a','destination':'../escape'}]}))
        with self.assertRaises(ValueError):app.snapshot(m,self.root/'export')
        (self.root/'Materials/link').symlink_to(src)
        m.write_text(json.dumps({'items':[{'source':'Materials/link','destination':'copy'}]}))
        with self.assertRaises(ValueError):app.snapshot(m,self.root/'export')
        self.assertFalse((self.root/'export').exists())
    def test_revision_conflict_and_history(self):
        app.new('journal','Fixture',None)
        r=app.records()[0];path=self.root/r['path'];body=self.root/'replacement.txt';body.write_text('Updated discussion')
        with self.assertRaises(ValueError):app.update(r['id'],'stale',body)
        app.update(r['id'],r['revision'],body)
        self.assertEqual(app.read(path)[1],'Updated discussion')
        self.assertTrue((self.root/'.system/history'/r['id']/(r['revision']+'.md')).exists())
    def test_invalid_relationship_and_private_calendar(self):
        result=app.browser_action({'action':'create','type':'tasks','fields':{'title':'Fixture'}})
        p=self.root/result['records'][0]['path'];meta,body=app.read(p)
        meta['projects']=['missing'];p.write_text(app.serialize(meta,body))
        with self.assertRaises(ValueError):app.records()
        meta['projects']=[];meta['private']=True;meta['calendar_target']='outlook';p.write_text(app.serialize(meta,body))
        with self.assertRaises(ValueError):app.records()
if __name__=='__main__':unittest.main()
