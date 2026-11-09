import importlib.util,sys,json,tempfile,shutil,unittest
from pathlib import Path
APP=Path(__file__).parents[1]/'app'
sys.path.insert(0,str(APP))
import phd as app
import zotero_bridge as bridge

class IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=(app.ROOT,app.W,app.SYS)
  app.ROOT=Path(self.temp.name);app.W=app.ROOT/'Records';app.SYS=app.ROOT/'.system'
  (app.W/'Knowledge').mkdir(parents=True);(app.SYS/'index').mkdir(parents=True);(app.SYS/'config').mkdir()
  (app.SYS/'config/registry.json').write_text(json.dumps({'record_roots':['Records'],'paper_roots':[],'domains':['research'],'connections':{}}))
 def tearDown(self):
  app.ROOT,app.W,app.SYS=self.old;self.temp.cleanup()
 def snapshot(self):
  return ('server-one',[{'key':'ABCD1234','data':{'itemType':'journalArticle','title':'A Paper','DOI':'10.1234/example'}},{'key':'PDF12345','data':{'itemType':'attachment','parentItem':'ABCD1234','contentType':'application/pdf'}},{'key':'NOTE1234','data':{'itemType':'annotation','parentItem':'PDF12345','annotationText':'Actual highlight','annotationPageLabel':'3'}}],[])
 def note(self,**extra):
  meta=dict(id='existing',type='knowledge',title='A Paper',updated='2025-02-01',status='captured',domain='research',projects=[],sources=[],human_reading='abstract',**extra)
  app.atomic_write(app.W/'Knowledge/existing.md',app.serialize(meta,'My original notes'))
 def test_sync_preserves_notes_dates_and_is_idempotent(self):
  self.note();r=bridge.sync(app,self.snapshot());self.assertEqual(r['linked'],1)
  saved=app.records()[0];self.assertEqual(saved['body'],'My original notes');self.assertEqual(saved['updated'],'2025-02-01');self.assertEqual(saved['human_reading'],'abstract')
  self.assertEqual(saved['zotero']['annotations'][0]['text'],'Actual highlight')
  again=bridge.sync(app,self.snapshot());self.assertEqual(again['added'],0);self.assertEqual(again['changed'],0);self.assertEqual(app.records()[0]['revision'],saved['revision'])
 def test_reference_overrides_and_conference_venue(self):
  self.note(authors='Local Author',doi='10.1234/local',publication_date='2020',publication='Local venue',library='phd')
  server,items,collections=self.snapshot();items[0]['data'].update(itemType='conferencePaper',proceedingsTitle='Conference Proceedings')
  bridge.sync(app,(server,items,collections));r=app.records()[0]
  self.assertEqual(r['zotero']['publication'],'Conference Proceedings')
  self.assertEqual(r['authors'],'Local Author');self.assertEqual(r['doi'],'10.1234/local');self.assertEqual(r['library'],'phd')
 def test_deleted_note_is_not_resurrected(self):
  self.note(deleted_at='2026-09-01');r=bridge.sync(app,self.snapshot());self.assertEqual(r['added'],0);self.assertEqual(len(app.records()),1);self.assertTrue(app.records()[0]['deleted_at'])
 def test_new_entry_is_created_once_with_unknown_reading(self):
  bridge.sync(app,self.snapshot());bridge.sync(app,self.snapshot());self.assertEqual(len(app.records()),1);self.assertEqual(app.records()[0]['human_reading'],'unknown')
 def test_different_library_does_not_overwrite_old_key(self):
  bridge.sync(app,self.snapshot());server,items,collections=self.snapshot();bridge.sync(app,('different-server',items,collections));self.assertEqual(len(app.records()),2)
 def test_obsidian_yaml_and_duplicate_keys(self):
  p=app.W/'Knowledge/test.md';p.write_text('---\nid: sample\ntype: knowledge\ntitle: A note\nupdated: 2026-09-07\nstatus: draft\nprojects: []\nsources:\n  - https://example.org\n---\n\nEdited in Obsidian\n')
  r=app.records()[0];self.assertEqual(r['updated'],'2026-09-07');self.assertEqual(r['sources'],['https://example.org'])
  p.write_text('---\nid: a\nid: b\n---\nBody')
  with self.assertRaises(ValueError):app.read(p)
if __name__=='__main__':unittest.main()
