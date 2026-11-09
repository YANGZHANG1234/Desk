"""Canonical literature entities/relations and disposable map projection."""
import hashlib,json,re,datetime,fcntl,shutil
from pathlib import Path
from urllib.parse import quote,unquote
from urllib.request import urlopen,Request

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def doi(v):
 v=unquote(str(v or '')).strip().lower();v=re.sub(r'^(?:https?://(?:dx\.)?doi.org/|doi:\s*)','',v)
 return v if re.fullmatch(r'10\.\d{4,9}/\S+',v) else ''
def key(kind,value):return kind+'-'+hashlib.sha256(value.encode()).hexdigest()[:20]
def paper(r):return r['type']=='knowledge' and bool(r.get('doi') or r.get('zotero') or r.get('kind') in ['Paper','Book','Chapter','Report'])
def library(r):return r.get('library') or ('vertiport' if 'evtol' in r.get('projects',[]) or re.search(r'vertiport|urban air mobility|heliport|helideck',r['title']+' '+' '.join(r.get('zotero',{}).get('collections',[])),re.I) else 'phd')
def evidence(url,method='source_metadata',**kw):return dict(source_url=url,retrieved_at=now(),method=method,**kw)
def save(m,meta,body,expected=None):
 p=m.ROOT/('Records/Relations' if meta['type']=='relations' else 'Records/Entities' if meta['type']=='entities' else 'Records/Knowledge')/(meta['id']+'.md')
 existing=next((r for r in m.records() if r['id']==meta['id']),None) if meta['type']=='knowledge' else None
 if existing:p=m.ROOT/existing['path']
 with (m.SYS/'index/write.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  if p.exists():
   digest=hashlib.sha256(p.read_bytes()).hexdigest()
   if expected is not None and expected!=digest:raise RuntimeError('Record changed; reload before updating')
   if expected is None:return m.read(p)[0]
   backup=m.SYS/'history'/meta['id']/(digest+'.md');backup.parent.mkdir(parents=True,exist_ok=True)
   if not backup.exists():shutil.copy2(p,backup)
  meta.setdefault('updated',str(datetime.date.today()));meta.setdefault('status','captured');meta.setdefault('domain','research');meta.setdefault('projects',[]);meta.setdefault('sources',[])
  m.atomic_write(p,m.serialize(meta,body))
 return meta

def entity(m,kind,identity,title,ev,**fields):
 id=key(kind,identity)
 return save(m,dict(id=id,type='entities',entity_kind=kind,title=title,sources=[ev['source_url']],evidence=[ev],**fields),'# '+title+'\n\nSource-backed graph entity.')['id']
def edge(m,a,t,b,ev,status='source_reported',reason=''):
 id=key('relation',a+'|'+t+'|'+b);p=m.W/'Relations'/(id+'.md')
 if p.exists():
  meta,body=m.read(p);stamp=hashlib.sha256(p.read_bytes()).hexdigest()
  if not any(x.get('source_url')==ev['source_url'] and x.get('method')==ev['method'] for x in meta['evidence']):
   meta['evidence'].append(ev);save(m,meta,body,stamp)
  return id
 save(m,dict(id=id,type='relations',title=t.replace('_',' '),source_id=a,target_id=b,relation_type=t,evidence=[ev],verification=status,reason=reason,sources=[ev['source_url']]),'# '+t.replace('_',' ')+'\n\n'+reason)
 return id

def validate(rs):
 ids={r['id'] for r in rs};types={'cites_paper','authored_by','affiliated_with','published_in','published_by','available_on','similar_content'}
 for r in rs:
  if r['type']=='relations':
   if r.get('source_id') not in ids or r.get('target_id') not in ids:raise ValueError('Dangling graph endpoint: '+r['id'])
   if r.get('relation_type') not in types:raise ValueError('Unknown graph relation')
   if r.get('verification') not in ['source_reported','verified','candidate','rejected','disputed']:raise ValueError('Invalid graph verification')
   if not r.get('evidence') or any(not e.get('source_url') or not e.get('retrieved_at') or not e.get('method') for e in r['evidence']):raise ValueError('Missing graph evidence')
  if r['type']=='entities' and r.get('entity_kind') not in ['paper','author','institution','journal','publisher','platform']:raise ValueError('Unknown graph entity')

def get_json(url):
 with urlopen(Request(url,headers={'User-Agent':'Desk-Literature/1.0 (personal research)'}),timeout=20) as r:return json.load(r)

def enrich(m,record_id,fetch=get_json):
 rs=m.records();r=next(x for x in rs if x['id']==record_id and not x.get('deleted_at'));d=doi(r.get('doi') or r.get('zotero',{}).get('doi'))
 if not d:raise ValueError('DOI missing; verify bibliography first')
 url='https://api.crossref.org/works/'+quote(d,safe='');x=fetch(url)['message'];ev=evidence(url)
 if doi(x.get('DOI'))!=d:raise ValueError('Provider DOI mismatch')
 # Reuse an existing paper DOI, never title-merge.
 bydoi={}
 for v in sorted(rs,key=lambda v:not paper(v)):
  if v.get('deleted_at'):continue
  vd=doi(v.get('doi') or v.get('zotero',{}).get('doi'))
  if vd and (paper(v) or v.get('entity_kind')=='paper'):bydoi.setdefault(vd,v['id'])
 collisions={}
 for v in rs:
  vd=doi(v.get('doi') or v.get('zotero',{}).get('doi'))
  if paper(v) and vd and not v.get('deleted_at'):collisions.setdefault(vd,[]).append(v['id'])
 for vd,items in collisions.items():
  if len(items)>1:bydoi.pop(vd,None)
 if x.get('container-title'):
  jid=entity(m,'journal',x.get('ISSN',['name:'+x['container-title'][0]])[0],x['container-title'][0],ev)
  edge(m,r['id'],'published_in',jid,ev)
  if x.get('publisher'):
   pub=entity(m,'publisher',x['publisher'],x['publisher'],ev);edge(m,jid,'published_by',pub,evidence(url,publication_doi=d))
 for i,a in enumerate(x.get('author',[])):
  name=a.get('name') or ' '.join(filter(None,[a.get('given'),a.get('family')]))
  if not name:continue
  identity=a.get('ORCID') or d+'#author-'+str(i)
  aid=entity(m,'author',identity,name,ev,orcid=a.get('ORCID',''),identity_status='orcid' if a.get('ORCID') else 'paper_scoped_unresolved')
  edge(m,r['id'],'authored_by',aid,ev)
  for aff in a.get('affiliation',[]):
   if aff.get('name'):
    inst=entity(m,'institution',aff['name'],aff['name'],ev);edge(m,aid,'affiliated_with',inst,evidence(url,publication_doi=d))
 landing=x.get('resource',{}).get('primary',{}).get('URL','')
 if landing.startswith('https://'):
  from urllib.parse import urlparse
  host=urlparse(landing).hostname
  platform=entity(m,'platform',host,host,evidence(url,landing_url=landing));edge(m,r['id'],'available_on',platform,evidence(url,landing_url=landing))
 refs=x.get('reference',[]);resolved=0;external=sum(v.get('entity_kind')=='paper' and not v.get('report_for') for v in rs)
 for ref in refs[:100]:
  rd=doi(ref.get('DOI'))
  if not rd or rd==d:continue
  target=bydoi.get(rd)
  if not target:
   if external>=600:continue
   external+=1
   target=entity(m,'paper',rd,ref.get('article-title') or rd,ev,doi=rd,library=library(r),collection_state='discovered');bydoi[rd]=target
  edge(m,r['id'],'cites_paper',target,ev);resolved+=1
 forward={'status':'not_queried','linked':0}
 try:
  work_url='https://api.openalex.org/works/https://doi.org/'+quote(d,safe='')
  work=fetch(work_url);wid=work['id'].rsplit('/',1)[-1]
  citing_url='https://api.openalex.org/works?filter=cites:'+quote(wid)+'&per-page=50'
  citing=fetch(citing_url);count=0
  for item in citing.get('results',[]):
   cd=doi(item.get('doi'))
   if not cd or cd==d:continue
   target=bydoi.get(cd)
   if not target:
    if external>=600:continue
    external+=1;target=entity(m,'paper',cd,item.get('display_name') or cd,evidence(citing_url),doi=cd,library=library(r),collection_state='discovered');bydoi[cd]=target
   edge(m,target,'cites_paper',r['id'],evidence(citing_url));count+=1
  forward={'status':'bounded','provider':'OpenAlex','reported':citing.get('meta',{}).get('count'),'checked':len(citing.get('results',[])),'linked':count,'complete':False}
 except Exception as err:forward={'status':'unavailable','linked':0,'error_type':type(err).__name__}
 # Canonical coverage on a source-report entity, not inferred from edge absence.
 eid=key('paper-source',d);meta=dict(id=eid,type='entities',entity_kind='paper',title='Source report: '+r['title'],report_for=r['id'],sources=[url],evidence=[ev],coverage=dict(provider='Crossref',references_reported=len(refs),references_checked=min(100,len(refs)),doi_references_linked=resolved,complete_reference_list=False,forward_citations=forward,external_node_limit=600,checked_at=now()))
 p=m.W/'Entities'/(eid+'.md');save(m,meta,'# Citation source report',hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None)
 return meta['coverage']

JOURNAL_SHORT={'journal of cleaner production':'JCP','resources, conservation and recycling':'RCR','resources conservation and recycling':'RCR','european journal of operational research':'EJOR','management science':'MS','operations research':'OR','american economic review':'AER','econometrica':'ECTA','journal of international economics':'JIE','journal of artificial societies and social simulation':'JASSS','computers & chemical engineering':'CCE','engineering applications of artificial intelligence':'EAAI','nature':'Nature','science':'Science','nature sustainability':'NatSust','acta astronautica':'ActaAstro'}
def short_label(r):
 b=r.get('graph_bibliography',{});authors=b.get('authors') or b.get('editors',[]);family=''
 if authors:family=authors[0].get('family') or authors[0].get('name','').split(' ')[-1]
 if not family:
  name=str(r.get('authors','')).split(';')[0].strip();family=name.split(',')[0] if ',' in name else name.split(' ')[-1]
 family=re.sub(r'[^\w-]','',family) or 'Unknown'
 year=str(b.get('year') or r.get('publication_date') or r.get('publication_year') or '')[:4]
 if not re.fullmatch(r'\d{4}',year):year='n.d.'
 journal=b.get('journal') or r.get('publication','');j=journal.lower().strip();abbr=JOURNAL_SHORT.get(j)
 if not abbr and j.startswith('transportation research part '):abbr='TR'+journal[len('transportation research part '):len('transportation research part ')+1].upper()
 if not abbr:abbr=''.join(w[0].upper() for w in re.findall(r'[A-Za-z]+',journal) if w.lower() not in ['of','the','and','in','for'])[:9]
 return family+('Ed' if not b.get('authors') and b.get('editors') else '')+year+(abbr or ('Book' if b.get('kind')=='monograph' else ''))

def projection(m):
 rs=[r for r in m.records() if not r.get('deleted_at') and not r.get('private')];lookup={r['id']:r for r in rs};nodes=[]
 for r in rs:
  if paper(r) or r['type']=='entities' and not r.get('report_for'):
   nodes.append(dict(id=r['id'],title=r.get('graph_bibliography',{}).get('title') or r['title'],label=short_label(r) if paper(r) or r.get('entity_kind')=='paper' else r['title'],authors=r.get('graph_bibliography',{}).get('authors') or [{'name':a.strip(),'family':''} for a in str(r.get('authors','')).split(';') if a.strip()],editors=r.get('graph_bibliography',{}).get('editors',[]),journal=r.get('graph_bibliography',{}).get('journal') or r.get('publication',''),kind='paper' if paper(r) else r['entity_kind'],collected=paper(r),updated=r.get('updated',''),library=library(r),human=r.get('human_reading','unknown'),agent=r.get('agent_reading','not_read'),year=r.get('publication_date') or r.get('publication_year',''),doi=doi(r.get('doi') or r.get('zotero',{}).get('doi')),path=r['path'],identity_status=r.get('identity_status','')))
 canonical={}
 for n in nodes:
  if n['collected'] and doi(n['doi']):canonical.setdefault(doi(n['doi']),[]).append(n['id'])
 aliases={n['id']:canonical[doi(n['doi'])][0] for n in nodes if not n['collected'] and doi(n['doi']) in canonical and len(canonical[doi(n['doi'])])==1}
 nodes=[n for n in nodes if n['id'] not in aliases]
 ids={n['id'] for n in nodes}|set(aliases);edges=[dict(id=r['id'],source=r['source_id'],target=r['target_id'],type=r['relation_type'],verification=r['verification'],reason=r.get('reason',''),evidence=r['evidence'],revision=r['revision']) for r in rs if r['type']=='relations' and r['source_id'] in ids and r['target_id'] in ids]
 for e in edges:e['source']=aliases.get(e['source'],e['source']);e['target']=aliases.get(e['target'],e['target'])
 edges=[e for e in edges if e['source']!=e['target']]
 unique={}
 for e in edges:
  identity=(e['source'],e['target'],e['type'],e['verification'])
  if identity not in unique:unique[identity]=e
  else:unique[identity]['evidence']+=e['evidence']
 edges=list(unique.values())
 labels={}
 for n in nodes:labels.setdefault(n['label'],[]).append(n)
 for values in labels.values():
  if len(values)>1:
   for i,n in enumerate(sorted(values,key=lambda n:n['id'])):n['label']+=chr(97+i) if i<26 else str(i+1)
 # Existing duplicate DOI notes remain untouched, but visibly report identity collisions.
 groups={}
 for n in nodes:
  if n['collected'] and doi(n['doi']):groups.setdefault(doi(n['doi']),[]).append(n['id'])
 return dict(nodes=nodes,edges=edges,coverage=[r['coverage']|{'paper_id':r['report_for']} for r in rs if r.get('report_for') in lookup],duplicate_dois={d:v for d,v in groups.items() if len(v)>1},generated_at=now())

def obsidian(m):
 rs=m.records();lookup={r['id']:r for r in rs};links={}
 for r in rs:
  if r['type']=='relations' and r['verification'] in ['source_reported','verified'] and not r.get('deleted_at'):
   a,b=lookup[r['source_id']],lookup[r['target_id']]
   if a.get('deleted_at') or b.get('deleted_at'):continue
   for src,dst,label in [(a,b,r['relation_type']),(b,a,'incoming '+r['relation_type'])]:
    import os
    target=os.path.relpath(m.ROOT/dst['path'],(m.ROOT/src['path']).parent)
    links.setdefault(src['id'],[]).append('- '+label.replace('_',' ')+': ['+dst['title'].replace('[','').replace(']','')+']('+quote(target,safe='/')+')')
 for r in rs:
  if '<!-- academic-links:start -->' in r['body'] and not r.get('deleted_at'):links.setdefault(r['id'],[])
 for id,lines in links.items():
  r=lookup[id];p=m.ROOT/r['path'];meta,body=m.read(p)
  clean=re.sub(r'\n?<!-- academic-links:start -->.*?<!-- academic-links:end -->','',body,flags=re.S).rstrip()
  new=clean+'\n\n<!-- academic-links:start -->\n## Academic links\n'+ '\n'.join(sorted(set(lines)))+'\n<!-- academic-links:end -->'
  if new!=body:save(m,meta,new,r['revision'])
 return len(links)

def matrix(m):
 import csv,io
 out=io.StringIO();cols=['id','title','doi','authors','year','journal','human_reading','agent_reading','access_level','problem','method','assumptions','findings','limitations','note_path','pdf_paths'];writer=csv.DictWriter(out,fieldnames=cols);writer.writeheader()
 for r in m.records():
  if not paper(r) or library(r)!='phd' or r.get('deleted_at'):continue
  z=r.get('zotero',{});row={k:r.get(k,'') for k in ['id','title','doi','authors','human_reading','agent_reading','access_level']};row.update(year=r.get('publication_date',''),journal=r.get('publication',''),note_path=r['path'],pdf_paths='; '.join(r.get('local_paths',[])))
  row.update({k:str(r.get('literature_matrix',{}).get(k,'')) for k in ['problem','method','assumptions','findings','limitations']})
  writer.writerow({k:("'"+str(v) if str(v).startswith(('=','+','-','@')) else v) for k,v in row.items()})
 return out.getvalue()
