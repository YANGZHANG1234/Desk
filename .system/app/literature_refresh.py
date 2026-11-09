"""One bounded metadata/citation pass over the existing PhD graph. Never fetch PDFs."""
import json,hashlib,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import quote
from urllib.error import HTTPError
import phd,literature_graph as g

def fetch(d,openalex_only=False):
 url='https://api.crossref.org/works/'+quote(d,safe='')
 try:
  if openalex_only:raise ValueError('Fallback requested')
  x=g.get_json(url)['message']
  if g.doi(x.get('DOI'))!=d:raise ValueError('DOI mismatch')
  dates=x.get('published',x.get('issued',{})).get('date-parts',[[]])[0]
  return {'doi':d,'title':next(iter(x.get('title',[])),d),'authors':[{'name':a.get('name') or ' '.join(filter(None,[a.get('given'),a.get('family')])),'family':a.get('family',''),'orcid':a.get('ORCID','')} for a in x.get('author',[])],'year':str(dates[0]) if dates else '', 'journal':next(iter(x.get('container-title',[])),''),'source':url,'retrieved_at':g.now(),'references':[g.doi(r.get('DOI')) for r in x.get('reference',[]) if g.doi(r.get('DOI'))],'reference_count':len(x.get('reference',[]))}
 except HTTPError as e:
  if e.code==429:
   wait=min(10,int(e.headers.get('Retry-After','5')));time.sleep(wait)
   return {'doi':d,'error':'Crossref rate limited; skipped after bounded wait','source':url}
 except Exception:pass
 url='https://api.openalex.org/works/https://doi.org/'+quote(d,safe='')
 try:
  x=g.get_json(url)
  if g.doi(x.get('doi'))!=d:raise ValueError('DOI mismatch')
  return {'doi':d,'title':x.get('display_name') or d,'authors':[{'name':a['author']['display_name'],'family':'','orcid':a['author'].get('orcid','')} for a in x.get('authorships',[])],'year':str(x.get('publication_year') or ''),'journal':((x.get('primary_location') or {}).get('source') or {}).get('display_name',''),'source':url,'retrieved_at':g.now(),'references':[],'reference_count':None,'reference_limitation':'OpenAlex fallback metadata only; DOI references unavailable in this pass'}
 except Exception as e:return {'doi':d,'source':url,'error':type(e).__name__}

def main():
 rs=phd.records();papers=[r for r in rs if not r.get('deleted_at') and not r.get('private') and (g.paper(r) and g.library(r)=='phd' or r.get('entity_kind')=='paper' and not r.get('report_for'))];groups={}
 for r in papers:
  d=g.doi(r.get('doi') or r.get('zotero',{}).get('doi'))
  if d:groups.setdefault(d,[]).append(r)
 cache=phd.SYS/'literature/metadata-round';cache.mkdir(parents=True,exist_ok=True)
 results=[]
 with ThreadPoolExecutor(max_workers=3) as pool:
  futures={pool.submit(fetch,d):d for d in groups}
  for future in as_completed(futures):
   x=future.result();results.append(x);(cache/(g.key('doi',x['doi'])+'.json')).write_text(json.dumps(x,ensure_ascii=False,indent=2))
   if len(results)%25==0:print('Fetched',len(results),'/',len(groups),flush=True)
 # Commit sequentially with revision checks; bibliographic snapshots do not overwrite Zotero-owned fields.
 linked=0;updated=0;errors=[]
 for x in results:
  if x.get('error'):errors.append(x);continue
  for r in groups[x['doi']]:
   p=phd.ROOT/r['path'];meta,body=phd.read(p);stamp=hashlib.sha256(p.read_bytes()).hexdigest();meta['graph_bibliography']={k:v for k,v in x.items() if k not in ['references','reference_count']}
   if r['type']=='entities':meta['title']=x['title']
   g.save(phd,meta,body,stamp);updated+=1
  # Connect only exact DOI endpoints already in the graph. Never invent a relation from similarity.
  for rd in x['references']:
   if rd not in groups or rd==x['doi']:continue
   targets=groups[rd];collected=[r for r in targets if g.paper(r)];targets=collected or targets
   if len(targets)!=1:continue
   for r in groups[x['doi']]:
    ev={'source_url':x['source'],'retrieved_at':x['retrieved_at'],'method':'provider_reference_doi','citing_doi':x['doi'],'cited_doi':rd}
    g.edge(phd,r['id'],'cites_paper',targets[0]['id'],ev);linked+=1
 report={'attempted':len(groups),'metadata_updated':updated,'errors':errors,'reference_links_observed':linked,'scope':'Existing PhD records and existing external paper nodes; no PDF retrieval; no new external nodes','at':g.now()}
 (cache/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True);phd.build()
if __name__=='__main__':main()
