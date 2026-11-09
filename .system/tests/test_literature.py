import sys,unittest,tempfile,hashlib,json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parents[1]/'app'))
import phd, literature_graph as g, literature_jobs as j
class LiteratureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=(phd.ROOT,phd.W,phd.SYS);phd.ROOT=self.root;phd.W=self.root/'Records';phd.SYS=self.root/'.system';(phd.SYS/'index').mkdir(parents=True)
  self.m=SimpleNamespace(ROOT=phd.ROOT,W=phd.W,SYS=phd.SYS,read=phd.read,serialize=phd.serialize,atomic_write=phd.atomic_write,records=self.records)
 def records(self):
  out=[]
  for p in self.root.glob('Records/**/*.md'):
   m,b=phd.read(p);out.append(m|{'body':b,'path':str(p.relative_to(self.root)),'revision':hashlib.sha256(p.read_bytes()).hexdigest()})
  g.validate(out);return out
 def tearDown(self):phd.ROOT,phd.W,phd.SYS=self.old;self.tmp.cleanup()
 def paper(self,id='p',doi='10.1234/a'):
  g.save(self.m,dict(id=id,type='knowledge',title='Transport flexibility',doi=doi,kind='Paper',human_reading='full_text',agent_reading='not_read'),'User note')
 def fetch(self,url):
  if 'crossref' in url:return {'message':{'DOI':'10.1234/a','container-title':['Journal'],'publisher':'Publisher','author':[{'given':'Jane','family':'Smith'}],'reference':[{'DOI':'10.1234/b'}]}}
  raise OSError('offline')
 def test_doi_normalization(self):self.assertEqual(g.doi('https://doi.org/10.1234/ABC'),'10.1234/abc');self.assertEqual(g.doi('garbage'),'')
 def test_enrichment_is_idempotent_and_outage_explicit(self):
  self.paper();a=g.enrich(self.m,'p',self.fetch);count=len(self.records());g.enrich(self.m,'p',self.fetch);self.assertEqual(count,len(self.records()));self.assertEqual(a['forward_citations']['status'],'unavailable');self.assertEqual(next(r for r in self.records() if r['id']=='p')['human_reading'],'full_text')
 def test_conflict_preserves_body(self):
  self.paper();r=self.records()[0]
  with self.assertRaises(RuntimeError):g.save(self.m,r,'Wrong','stale')
  self.assertEqual(self.records()[0]['body'],'User note')
 def test_external_promotes_in_projection_without_duplicate_node(self):
  self.paper();g.enrich(self.m,'p',self.fetch);self.paper('new','10.1234/b');graph=g.projection(self.m);self.assertEqual(len([n for n in graph['nodes'] if n['doi']=='10.1234/b']),1);self.assertTrue(any(e['target']=='new' for e in graph['edges']))
 def test_rejected_edges_removed_from_obisidian(self):
  self.paper();self.paper('b','10.1234/b');eid=g.edge(self.m,'p','similar_content','b',g.evidence('test'),'verified');g.obsidian(self.m)
  r=next(r for r in self.records() if r['id']==eid);meta,body=phd.read(self.root/r['path']);meta['verification']='rejected';g.save(self.m,meta,body,r['revision']);g.obsidian(self.m)
  self.assertNotIn('similar content:',next(r for r in self.records() if r['id']=='p')['body'])
 def test_exact_duplicate_no_agent_and_reading_unchanged(self):
  self.paper();p=self.root/'paper.pdf';p.write_bytes(b'%PDF-test');r=self.records()[0];meta,body=phd.read(self.root/r['path']);meta['local_paths']=['paper.pdf'];g.save(self.m,meta,body,r['revision']);result=j.upload(self.m,{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()},self.root);self.assertEqual(result['paper_id'],'p');self.assertEqual(self.records()[0]['agent_reading'],'not_read')
 def test_job_repeat_and_running_cancel(self):
  from unittest.mock import patch
  self.paper()
  with patch.object(j,'start'):
   a=j.enqueue(self.m,'enrich',{'id':'p'})['id'];self.assertEqual(a,j.enqueue(self.m,'enrich',{'id':'p'})['id'])
   with j.db(self.m) as c:c.execute("UPDATE jobs SET state='completed' WHERE id=?",(a,))
   b=j.enqueue(self.m,'enrich',{'id':'p'})['id'];self.assertNotEqual(a,b);self.assertEqual(b,j.enqueue(self.m,'enrich',{'id':'p'})['id'])
   with j.db(self.m) as c:c.execute("UPDATE jobs SET state='running' WHERE id=?",(b,))
   j.control(self.m,b,'cancel');self.assertEqual(next(x for x in j.jobs(self.m) if x['id']==b)['state'],'running')
 def test_matrix_escapes_formulas_and_leaves_unknowns_blank(self):
  self.paper();r=self.records()[0];meta,body=phd.read(self.root/r['path']);meta['title']='=HYPERLINK("unsafe")';g.save(self.m,meta,body,r['revision']);self.assertIn("'=HYPERLINK",g.matrix(self.m));self.assertNotIn('Invented method',g.matrix(self.m))
 def test_missing_evidence_and_dangling_endpoint_rejected(self):
  with self.assertRaises(ValueError):g.validate([{'id':'r','type':'relations','source_id':'missing','target_id':'missing'}])
 def test_user_short_label_and_missing_metadata(self):
  r={'graph_bibliography':{'authors':[{'family':'Rivera','name':'Alex Rivera'}],'year':'2026','journal':'Journal of Cleaner Production'}}
  self.assertEqual(g.short_label(r),'Rivera2026JCP')
  self.assertEqual(g.short_label({'title':'Unverified paper'}),'Unknownn.d.')
 def test_projected_parallel_evidence_does_not_duplicate_edges(self):
  self.paper();self.paper('b','10.1234/b');ev=g.evidence('test');external=g.entity(self.m,'paper','10.1234/b','Paper B',ev,doi='10.1234/b')
  g.edge(self.m,'p','cites_paper','b',ev);g.edge(self.m,'p','cites_paper',external,g.evidence('second-source'))
  edges=g.projection(self.m)['edges'];self.assertEqual(len(edges),1);self.assertEqual(len(edges[0]['evidence']),2)
if __name__=='__main__':unittest.main()
