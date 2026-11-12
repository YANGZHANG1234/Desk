#!/usr/bin/env python3
"""Desk research workspace. Create, validate, build, and serve local records."""
import argparse, datetime as dt, html, json, mimetypes, re, secrets, hashlib, os, shutil, tempfile, subprocess, fcntl
from pathlib import Path
import sys
if str(Path(__file__).parent) not in sys.path:sys.path.insert(0,str(Path(__file__).parent))
from urllib.parse import quote, unquote, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP = Path(__file__).resolve().parent
ASSETS = APP.parent
ROOT = ASSETS.parent
W = ROOT / 'Records'
SYS = ROOT / '.system'
TYPES = {'projects':'Projects','work-packages':'Work packages','tasks':'Tasks','planning':'Planning & calendar','knowledge':'Knowledge & reading','journal':'Journal','meetings':'Meetings','reviews':'Reviews','inbox':'Inbox'}
FOLDERS = dict(zip(TYPES,['Projects','Work-Packages','Tasks','Planning','Knowledge','Journal','Meetings','Reviews','Inbox']))
TYPES.update(entities='Graph entities', relations='Graph relations')
FOLDERS.update(entities='Entities', relations='Relations')

STATUS = {'needs_review':'Needs review','proposed':'Proposed','todo':'To do','doing':'In progress','done':'Done','blocked':'Blocked','cancelled':'Cancelled','captured':'Captured','active':'In progress','draft':'Draft','archived':'Archived','exploring':'Exploring','completed':'Completed','routine':'Routine'}

def read(path):
    text = path.read_text()
    if not text.startswith('---\n'): raise ValueError(f'{path}: Missing record fields')
    head, body = text[4:].split('\n---\n', 1)
    # Obsidian rewrites JSON-style frontmatter as YAML. Read both safely.
    import sys
    vendor=str(Path(__file__).parent/'vendor')
    if vendor not in sys.path: sys.path.insert(0,vendor)
    import yaml
    class RecordLoader(yaml.SafeLoader):
        pass
    RecordLoader.yaml_implicit_resolvers={k:[(tag,pattern) for tag,pattern in values if tag!='tag:yaml.org,2002:timestamp'] for k,values in yaml.SafeLoader.yaml_implicit_resolvers.items()}
    def mapping(loader,node,deep=False):
        result={}
        for key_node,value_node in node.value:
            key=loader.construct_object(key_node,deep=deep)
            if key in result: raise ValueError(f'{path}: Duplicate field {key}')
            result[key]=loader.construct_object(value_node,deep=deep)
        return result
    RecordLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
    try: meta=yaml.load(head,Loader=RecordLoader)
    except yaml.YAMLError as exc: raise ValueError(f'{path}: Invalid record fields') from exc
    if not isinstance(meta,dict): raise ValueError(f'{path}: Record fields must be a mapping')
    return meta, body.strip()

def registry():
    path = SYS / 'config/registry.json'
    if not path.exists():
        path = ASSETS / 'config/registry.example.json'
    return json.loads(path.read_text())

def record_paths():
    config=registry()
    paths=[]
    for root in config['record_roots']:
        paths.extend((ROOT/root).rglob('*.md'))
    for root in config['paper_roots']:
        paper_root = ROOT / root
        if not paper_root.exists():
            continue
        for paper in paper_root.iterdir():
            if not paper.is_dir(): continue
            paths.extend([paper/'Project.md'])
            for part in ['records','literature']:
                if (paper/part).exists(): paths.extend((paper/part).rglob('*.md'))
    return sorted({p for p in paths if p.is_file() and not p.is_symlink()})

def records():
    result=[]
    for path in record_paths():
        if not path.read_text().startswith('---\n'): continue
        meta, body=read(path)
        for key in ['id','type','title','updated','status','projects','sources']:
            if key not in meta: raise ValueError(f'{path}: Missing {key}')
        if meta['type'] not in TYPES: raise ValueError(f'{path}: Unknown type')
        for key in ['id','title','updated','status']:
            if not isinstance(meta[key],str) or not meta[key]: raise ValueError(f'{path}: {key} must be a string')
        dt.date.fromisoformat(meta['updated'])
        for key in ['projects','sources','local_paths','work_packages','tasks','journal','reviews','cites','meetings','depends_on']:
            if key in meta and (not isinstance(meta[key],list) or any(not isinstance(x,str) for x in meta[key])): raise ValueError(f'{path}: {key} must be an array')
        if meta.get('domain','research') not in registry()['domains']: raise ValueError(f'{path}: Unknown domain')
        for name in meta.get('local_paths',[]):
            if not (ROOT/name).exists(): raise ValueError(f'{path}: Missing path {name}')
        if meta.get('private') and meta.get('calendar_target')=='outlook': raise ValueError('Private events cannot target the school calendar')
        result.append(dict(meta,body=body,path=str(path.relative_to(ROOT)),modified_at=path.stat().st_mtime,revision=hashlib.sha256(path.read_bytes()).hexdigest()))
    lookup={r['id']:r for r in result}
    if len(lookup)!=len(result): raise ValueError('Duplicate record ID')
    for r in result:
        for key,typ in [('projects','projects'),('work_packages','work-packages'),('tasks','tasks'),('journal','journal'),('reviews','reviews'),('cites',None),('meetings','meetings'),('depends_on','tasks')]:
            for id in r.get(key,[]):
                if id not in lookup or (typ and lookup[id]['type']!=typ): raise ValueError(f'{r["id"]}: Invalid {key} reference {id}')
    import literature_graph
    literature_graph.validate(result)
    return result

def serialize(meta,body):
    return '---\n'+'\n'.join(k+': '+json.dumps(v,ensure_ascii=False) for k,v in meta.items())+'\n---\n\n'+body.strip()+'\n'

def atomic_write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name)
    try:
        with os.fdopen(fd,'w') as f: f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def update(id,expected,body_file):
    # Cooperating agents share a lock; external editors are checked again before replace.
    with (SYS/'index/write.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        r=next(x for x in records() if x['id']==id)
        path=ROOT/r['path']
        if r['revision']!=expected: raise ValueError('Record changed; reload and merge before writing.')
        meta,old=read(path);body=Path(body_file).read_text();meta['updated']=dt.date.today().isoformat()
        backup=SYS/'history'/id/(expected+'.md');backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists():shutil.copy2(path,backup)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected: raise ValueError('External edit conflict; nothing overwritten')
        atomic_write(path,serialize(meta,body))
    build()


def new(typ,title,project,domain=None,work_package=None):
    rs=records()
    if project and project not in {r['id'] for r in rs if r['type']=='projects'}: raise ValueError('Unknown project ID')
    if work_package and not any(r['id']==work_package and r['type']=='work-packages' for r in rs): raise ValueError('Unknown work package ID')
    inferred=next((r.get('domain','research') for r in rs if r['id']==project),'research')
    domain=domain or inferred
    if domain not in registry()['domains']: raise ValueError('Unknown domain')
    date=dt.date.today().isoformat()
    id=typ+'-'+date+'-'+secrets.token_hex(3)
    meta=dict(id=id,type=typ,title=title,updated=date,status='draft',domain=domain,projects=[project] if project else [],sources=[],summary='',work_packages=[work_package] if work_package else [])
    if typ in ['journal','meetings','reviews','planning']: meta['date']=date
    if typ=='tasks': meta.update(status='proposed',do_date='',due_date='')
    if typ=='knowledge': meta.update(access_level='metadata',agent_reading='not_read',human_reading='unknown')
    template=(ASSETS/'templates'/f'{typ}.md').read_text()
    p=W/FOLDERS[typ]/f'{id}.md'
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        f.write('---\n'+'\n'.join(k+': '+json.dumps(v,ensure_ascii=False) for k,v in meta.items())+'\n---\n\n# '+title+'\n\n'+template)
    build()
    print(p)

def mdlink(r): return '['+r['title'].replace('|',' / ')+']('+quote(r['path'],safe='/')+')'

def build():
    rs=records()
    now=dt.datetime.now().astimezone().isoformat(timespec='seconds')
    context = SYS / 'context/current.md'
    if not context.exists():
        context = ASSETS / 'context/default.md'
    current = context.read_text()
    lines=['# Desk Workspace','',f'Generated: {now}. Local workspace index.','', '[Guide](README.md)','',current.replace('# Current context','## Current context',1),'']
    for typ,label in TYPES.items():
        lines += ['## '+label,'','| Record | Status | Summary |','|---|---|---|']
        items=[r for r in rs if r['type']==typ and not r.get('deleted_at')]
        for r in sorted(items,key=lambda r:r.get('date',r['updated']),reverse=True):
            lines += [f"| {mdlink(r)} | {STATUS.get(r['status'],r['status'])} | {r.get('summary','').replace('|',' / ').replace(chr(10),' ')} |"]
        if not items: lines += ['| No records yet | — | — |']
        lines += ['']
    atomic_write(ROOT/'Home.md','\n'.join(lines))
    data=json.dumps(dict(records=rs,workspace_root=str(ROOT),registry=registry(),presentation=json.loads((SYS/'config/presentation.json').read_text()) if (SYS/'config/presentation.json').exists() else {},updated=now,current=current),ensure_ascii=False).replace('<','\\u003c')
    template=(APP/'dashboard.template.html').read_text()
    atomic_write(SYS/'index/dashboard.html',template.replace('__CSS__',(APP/'desk.css').read_text(),1).replace('__JS__',(APP/'desk.js').read_text()+'\n'+(APP/'literature_map.js').read_text(),1).replace('__DATA__',data,1))
    atomic_write(SYS/'index/records.json',json.dumps(rs,ensure_ascii=False,indent=2))
    return rs

# Read-only local file access. Only records/memory and explicitly linked research paths.
def permitted(path,rs):
    try: p=path.resolve(strict=True)
    except (OSError,RuntimeError): return False
    if not p.is_relative_to(ROOT): return False
    if p in [ROOT/'README.md',ROOT/'Home.md']: return True
    if any(x.startswith('.') for x in p.relative_to(ROOT).parts): return False
    if p.is_relative_to(W):
        if p.is_file() and p.suffix=='.md': return True
        assets=W/'Knowledge/assets'
        return (p.is_file() and p.suffix.lower() in {'.png','.jpg','.jpeg','.gif','.webp'}
                and p.parent.parent==assets and any(r['id']==p.parent.name and r['type']=='knowledge' for r in rs))
    for m in registry()['materials']:
        base=(ROOT/m['path']).resolve()
        if m['access']=='linked' and (p==base or p.is_relative_to(base)): return True
    for r in rs:
        if p==ROOT/r['path']: return True
        for s in r.get('local_paths',[]):
            base=(ROOT/s).resolve()
            if p==base or (base.is_dir() and p.is_relative_to(base)): return True
    return False

def browser_action(payload):
    """Validated local UI mutations; canonical Markdown remains authoritative."""
    action=payload.get('action')
    allowed_fields={'title','body','summary','status','domain','projects','work_packages','tasks','sources','date','do_date','due_date','kind','start_time','end_time','private','calendar_state','calendar_target','access_level','agent_reading','human_reading','date_from','date_to','journal','reviews','cites','display_title','tags','meetings','depends_on','objective','deliverable','authors','doi','publication_date','publication','library'}
    statuses={'draft','proposed','todo','doing','blocked','done','cancelled','captured','active','archived','completed','needs_review','exploring','routine'}
    with (SYS/'index/write.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rs=records();lookup={r['id']:r for r in rs}
        fields=payload.get('fields',{})
        if not isinstance(fields,dict) or set(fields)-allowed_fields:raise ValueError('Unsupported record fields')
        for key,value in fields.items():
            if key in ['private']:
                if not isinstance(value,bool):raise ValueError('Private must be boolean')
            elif key in ['projects','work_packages','tasks','sources','journal','reviews','cites','tags','meetings','depends_on']:
                if not isinstance(value,list) or any(not isinstance(x,str) for x in value):raise ValueError('Links must be lists')
            elif not isinstance(value,str):raise ValueError('Text fields must be strings')
        if 'status' in fields and fields['status'] not in statuses:raise ValueError('Invalid status')
        for key in ['date','do_date','due_date','date_from','date_to']:
            if fields.get(key):dt.date.fromisoformat(fields[key])
        for key in ['start_time','end_time']:
            if fields.get(key):dt.datetime.fromisoformat(fields[key])
        if fields.get('start_time') and fields.get('end_time') and fields['end_time']<=fields['start_time']:raise ValueError('End must be after start')
        if fields.get('calendar_target') not in [None,'','local']:
            raise ValueError('This workspace currently saves local plans only')
        previous=None
        if action=='create':
            typ=payload.get('type')
            if typ not in TYPES:raise ValueError('Unknown record type')
            id=typ+'-'+dt.date.today().isoformat()+'-'+secrets.token_hex(4)
            meta=dict(id=id,type=typ,title='',updated=dt.date.today().isoformat(),status='draft',domain='research',projects=[],work_packages=[],sources=[])
            body='';path=W/FOLDERS[typ]/(id+'.md')
        elif action in ['update','delete','restore']:
            r=lookup.get(payload.get('id'))
            if not r:raise ValueError('Record not found')
            if r['revision']!=payload.get('revision'):raise RuntimeError('This record changed. Reload before editing; your draft has not been saved.')
            path=ROOT/r['path'];previous=path.read_bytes();meta,body=read(path)
        else:raise ValueError('Unknown action')
        if action in ['delete','restore']:
            if fields:raise ValueError('Delete and restore do not accept edits')
            if action=='delete':meta['deleted_at']=dt.datetime.now().astimezone().isoformat()
            else:meta.pop('deleted_at',None)
        elif meta.get('deleted_at'):raise ValueError('Restore this record before editing')
        old_status=meta.get('status')
        changes=dict(fields)
        body=changes.pop('body',body);meta.update(changes)
        if meta.get('start_time') and meta.get('end_time') and meta['end_time']<=meta['start_time']:raise ValueError('End must be after start')
        if not meta['title'].strip():raise ValueError('A title is required')
        meta['updated']=dt.date.today().isoformat()
        if meta.get('domain') not in registry()['domains']:raise ValueError('Unknown domain')
        for field,typ in [('projects','projects'),('work_packages','work-packages'),('tasks','tasks'),('journal','journal'),('reviews','reviews'),('cites',None),('meetings','meetings'),('depends_on','tasks')]:
            for id in meta.get(field,[]):
                if id not in lookup or (typ and lookup[id]['type']!=typ):raise ValueError('Invalid '+field+' link')
        if meta.get('private') and meta.get('calendar_target')=='outlook':raise ValueError('Private events cannot target Outlook')
        if meta['status'] in ['done','completed']:
            if fields.get('status') in ['done','completed'] and (action=='create' or old_status not in ['done','completed']):
                meta['completed_date']=dt.date.today().isoformat()
                meta.pop('completion_period',None)
        else:
            meta.pop('completed_date',None)
            meta.pop('completion_period',None)
        if previous is not None:
            if path.read_bytes()!=previous:raise RuntimeError('External edit conflict; nothing saved')
            backup=SYS/'history'/meta['id']/(hashlib.sha256(previous).hexdigest()+'.md')
            if not backup.exists():atomic_write(backup,previous.decode())
        atomic_write(path,serialize(meta,body))
        try:records()
        except Exception:
            if previous is None:path.unlink()
            else:atomic_write(path,previous.decode())
            raise
    return {'id':meta['id'],'records':records()}

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin','')
        if host.split(':')[0] not in ['127.0.0.1','localhost'] or origin!='http://'+host or self.headers.get('X-PhD-Action')!='1':
            return self.send_error(403)
        if self.path in ['/api/finance/unlock','/api/finance/lock']:return self.finance_post()
        if self.path=='/api/task-marks':return self.task_marks_post()
        if self.path not in ['/api/actions','/api/zotero/sync','/api/literature/jobs','/api/literature/control','/api/literature/relation','/api/literature/links']:return self.send_error(404)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>(36000000 if self.path=='/api/literature/jobs' else 1000000):raise ValueError('Invalid request size')
            payload=json.loads(self.rfile.read(length))
            if self.path.startswith('/api/literature/'):
                import literature_jobs as jobs, literature_graph as graph, sys
                mod=sys.modules[__name__]
                if self.path.endswith('/jobs'):result=jobs.enqueue(mod,payload['kind'],payload.get('payload',{}))
                elif self.path.endswith('/control'):result=jobs.control(mod,payload['id'],payload['action'])
                elif self.path.endswith('/links'):result={'linked':graph.obsidian(mod)}
                else:
                    r=next(r for r in records() if r['id']==payload['id'] and r['type']=='relations')
                    if payload.get('verification') not in ['verified','rejected']:raise ValueError('Invalid decision')
                    if not payload.get('reason','').strip():raise ValueError('Give an evidence-based reason')
                    meta,body=read(ROOT/r['path']);meta['verification']=payload['verification'];meta['reason']=payload['reason']
                    meta.setdefault('decisions',[]).append({'at':graph.now(),'verification':payload['verification'],'reason':payload['reason']})
                    graph.save(mod,meta,body,payload.get('revision',''));result={'id':r['id']}
            elif self.path=='/api/zotero/sync':
                import zotero_bridge
                import sys
                result=zotero_bridge.sync(sys.modules[__name__])
            else: result=browser_action(payload)
            self.send_bytes(json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8')
        except (ValueError,KeyError,TypeError) as e:self.json_error(400,str(e))
        except RuntimeError as e:self.json_error(409,str(e))
        except Exception:self.json_error(500,'Could not save. Your draft is still in the form.')
    def json_error(self,status,message,body=None,cookie=None):
        data=json.dumps(body if body is not None else {'error':message}).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(data)
    def task_marks_post(self):
        # Ticking a PAICC task stores only its id in Desk's own state file; exports stay untouched.
        import task_marks
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>8192:raise ValueError('Invalid request size')
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):raise ValueError('Invalid request')
            marks=task_marks.set_done(payload.get('ids'),payload.get('done'))
        except (ValueError,TypeError) as e:return self.json_error(400,str(e))
        except OSError:return self.json_error(500,'Could not save the mark.')
        self.send_bytes(json.dumps({'done':marks}).encode(),'application/json')
    def finance_token(self):
        from http.cookies import SimpleCookie
        import external_feeds
        try:jar=SimpleCookie(self.headers.get('Cookie',''))
        except Exception:return None
        return jar[external_feeds.COOKIE].value if external_feeds.COOKIE in jar else None
    def finance_post(self):
        # Finance lock (FD-043). The password is only hashed and compared; it is never logged or stored.
        import external_feeds
        base=external_feeds.COOKIE+'={}; Path=/; HttpOnly; SameSite=Strict'
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>4096:raise ValueError
            payload=json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(payload,dict):raise ValueError
        except (ValueError,TypeError):return self.json_error(400,'Invalid request')
        if self.path.endswith('/lock'):
            external_feeds.relock(self.finance_token())
            return self.json_error(200,None,{'locked':True},base.format('')+'; Max-Age=0')
        status,body,token=external_feeds.unlock(payload.get('password'))
        return self.json_error(status,None,body,base.format(token) if token else None)

    def do_GET(self):
        if self.headers.get('Host','').split(':')[0] not in ['127.0.0.1','localhost']: return self.send_error(403)
        try:
            url=urlparse(self.path)
            rs=None
            if url.path=='/api/health':
                return self.send_bytes(json.dumps({'service':'Desk','workspace':str(ROOT)}).encode(),'application/json')
            if url.path in ['/','/index.html']:
                build()
                return self.send_bytes((SYS/'index/dashboard.html').read_bytes(),'text/html; charset=utf-8')
            if url.path.startswith('/assets/'):
                name=url.path.removeprefix('/assets/')
                if not re.fullmatch(r'[a-f0-9]{24}\.png',name):return self.send_error(404)
                asset=SYS/'index/thumbnails'/name
                if not asset.is_file():return self.send_error(404)
                return self.send_bytes(asset.read_bytes(),'image/png')
            if url.path=='/api/literature/matrix.csv':
                import literature_graph,sys
                return self.send_bytes(literature_graph.matrix(sys.modules[__name__]).encode('utf-8-sig'),'text/csv; charset=utf-8')
            if url.path in ['/api/literature/graph','/api/literature/jobs']:
                import literature_graph as graph, literature_jobs as jobs, sys
                mod=sys.modules[__name__]
                result=graph.projection(mod) if url.path.endswith('/graph') else jobs.jobs(mod)
                return self.send_bytes(json.dumps(result,ensure_ascii=False).encode(),'application/json')
            if url.path in ['/api/external','/api/external/fic','/api/finance/status']:
                # Read-only companion exports (PAICC/FIC). Served only here: never merged into
                # records(), generated index files or literature agent prompts. FIC is locked
                # server-side until a valid finance session cookie is presented.
                if self.headers.get('Sec-Fetch-Site','same-origin') not in ['same-origin','none']:return self.send_error(403)
                import external_feeds
                token=self.finance_token()
                if url.path=='/api/finance/status':result=external_feeds.lock_status(token)
                elif url.path=='/api/external/fic':
                    if external_feeds.lock_status(token)['locked']:return self.json_error(401,None,{'locked':True})
                    result=external_feeds.load_source('fic')
                else:result=external_feeds.guarded_snapshot(token)
                return self.send_bytes(json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8')
            if url.path=='/api/task-marks':
                import task_marks
                return self.send_bytes(json.dumps({'done':task_marks.load()}).encode(),'application/json')
            if url.path=='/api/records':
                rs=records()
                return self.send_bytes(json.dumps(rs,ensure_ascii=False).encode(),'application/json; charset=utf-8')
            if url.path=='/file':
                rs=records()
                name=parse_qs(url.query).get('path',[''])[0]
                p=ROOT/name
                if not permitted(p,rs): return self.send_error(403,'Path is not in the research workspace allowlist')
                p=p.resolve()
                if p.is_dir():
                    links=[]
                    for child in sorted(p.iterdir()):
                        if permitted(child,rs):
                            rel=str(child.relative_to(ROOT))
                            links.append('<li><a href="/file?path='+quote(rel,safe='')+'">'+html.escape(child.name)+('</a> /' if child.is_dir() else '</a>')+'</li>')
                    return self.send_bytes(('<meta charset="utf-8"><h1>'+html.escape(p.name)+'</h1><ul>'+''.join(links)+'</ul>').encode(),'text/html; charset=utf-8')
                if p.suffix in ['.md','.py','.yaml','.json','.txt','.csv','.html','.js','.css']:
                    return self.send_bytes(p.read_bytes(),'text/plain; charset=utf-8')
                return self.send_bytes(p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
            self.send_error(404)
        except Exception as e:
            self.send_error(500,str(e))
    def send_bytes(self,data,kind):
        self.send_response(200)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Access-Control-Allow-Origin','http://127.0.0.1:'+str(self.server.server_port))
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(data)
    def log_message(self,*args): pass

class LocalServer(ThreadingHTTPServer):
    def server_bind(self):
        from socketserver import TCPServer
        TCPServer.server_bind(self)
        self.server_name='localhost';self.server_port=self.server_address[1]

def paper(slug,title):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug): raise ValueError('Use lowercase letters, numbers and hyphens for the slug')
    target=ROOT/'Materials/Research/Papers'/slug
    if target.exists(): raise ValueError('Paper package already exists')
    if any(r['id']=='paper-'+slug for r in records()): raise ValueError('Project ID already exists')
    target.mkdir(parents=True)
    for name in ['manuscript','code','experiments','data','literature','records']:(target/name).mkdir()
    meta=dict(id='paper-'+slug,type='projects',title=title,updated=dt.date.today().isoformat(),status='draft',domain='research',projects=[],sources=[],local_paths=[str(target.relative_to(ROOT))],summary='New paper package; define the research question and completion criteria.')
    atomic_write(target/'Project.md',serialize(meta,'# '+title+'\n\n## Research question\nTo be defined.\n\n## Completion criteria and milestones\nTo be defined.\n\n## Shared assets and versions\nLink shared code, references and data; pin versions when packaging.'))
    atomic_write(target/'README.md','# Paper research package\n\nProject.md is the canonical project record. Place paper-specific files in their respective folders. Structured Markdown in records/ and literature/ is indexed automatically. IDs must be unique across the workspace.\n\nLink shared knowledge and meetings. Use an explicit snapshot manifest to make a fixed, attributable copy; nothing is copied automatically.')
    atomic_write(target/'snapshot.example.json',json.dumps({'purpose':'internal-research-snapshot','items':[{'source':str((target/'Project.md').relative_to(ROOT)),'destination':'Project.md'}]},ensure_ascii=False,indent=2))
    build();print(target)

def snapshot(manifest,output):
    config=json.loads(Path(manifest).read_text())
    target=Path(output).resolve()
    if target.exists(): raise ValueError('Output already exists')
    selected=[];used=set()
    for item in config['items']:
        raw_source=ROOT/item['source']
        if raw_source.is_symlink():raise ValueError('Select the real source of a symlink explicitly')
        source=raw_source.resolve(strict=True)
        dest=Path(item['destination'])
        if not source.is_relative_to(ROOT) or source.is_relative_to(SYS): raise ValueError('Sources must be workspace materials, excluding system files')
        if source.is_symlink() or dest.is_absolute() or '..' in dest.parts:raise ValueError('Invalid path')
        paths=sorted(source.rglob('*')) if source.is_dir() else [source]
        for src in paths:
            relative=src.relative_to(ROOT)
            if src.is_symlink():raise ValueError('Select the real source of a symlink explicitly')
            if any(x.startswith('.') or x in ['node_modules','__pycache__','venv'] for x in relative.parts):continue
            if not src.is_file():continue
            if src.suffix in ['.pem','.key'] or src.name.startswith(('~$','credentials','token.')):raise ValueError('Manifest includes credentials or temporary files')
            d=dest/src.relative_to(source) if source.is_dir() else dest
            if str(d) in used or str(d)=='PROVENANCE.json':raise ValueError('Duplicate destination path')
            used.add(str(d));selected.append((src,d))
    if not selected:raise ValueError('Snapshot cannot be empty')
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.snapshot-',dir=target.parent))
    provenance=[]
    try:
        for src,d in selected:
            sha=hashlib.sha256(src.read_bytes()).hexdigest()
            out=stage/d;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,out)
            if hashlib.sha256(out.read_bytes()).hexdigest()!=sha or hashlib.sha256(src.read_bytes()).hexdigest()!=sha:raise ValueError('Source changed during copying')
            git={}
            try:
                commit=subprocess.check_output(['git','-C',str(src.parent),'rev-parse','HEAD'],stderr=subprocess.DEVNULL,text=True).strip()
                dirty=bool(subprocess.check_output(['git','-C',str(src.parent),'status','--porcelain'],stderr=subprocess.DEVNULL,text=True).strip())
                git={'commit':commit,'working_tree_dirty':dirty}
            except subprocess.CalledProcessError:pass
            provenance.append({'source':str(src.relative_to(ROOT)),'destination':str(d),'sha256':sha,'git':git})
        atomic_write(stage/'PROVENANCE.json',json.dumps({'created':dt.datetime.now().astimezone().isoformat(),'purpose':config.get('purpose','internal-research-snapshot'),'mode':'fixed-snapshot','files':provenance},ensure_ascii=False,indent=2))
        # Rename is on the same filesystem; cooperating commands must not overwrite a target.
        if target.exists():raise ValueError('Output was created by another operation')
        stage.rename(target)
    finally:
        if stage.exists():shutil.rmtree(stage)
    print(f'Created snapshot: {target} ({len(provenance)} files)')

def create_server(port):
    import literature_jobs

    build()
    server = LocalServer(('127.0.0.1', port), Handler)
    literature_jobs.start(sys.modules[__name__])
    return server

def main():
    p=argparse.ArgumentParser(description=__doc__)
    s=p.add_subparsers(dest='cmd',required=True)
    s.add_parser('check');s.add_parser('build');s.add_parser('zotero-sync')
    paper_parser=s.add_parser('paper');paper_parser.add_argument('--slug',required=True);paper_parser.add_argument('--title',required=True)
    pack=s.add_parser('snapshot');pack.add_argument('--manifest',required=True);pack.add_argument('--output',required=True)
    updater=s.add_parser('update');updater.add_argument('id');updater.add_argument('--expected',required=True);updater.add_argument('--body-file',required=True)
    launcher=s.add_parser('launch');launcher.add_argument('--port',type=int,default=8766)
    n=s.add_parser('new');n.add_argument('type',choices=[typ for typ in TYPES if typ not in {'entities', 'relations'}]);n.add_argument('--title',required=True);n.add_argument('--project');n.add_argument('--domain',choices=['research','teaching','collaboration-admin']);n.add_argument('--work-package')
    server=s.add_parser('serve');server.add_argument('--port',type=int,default=8766)
    args=p.parse_args()
    if args.cmd=='zotero-sync':
        import zotero_bridge,sys
        result=zotero_bridge.sync(sys.modules[__name__]);build()
        print(json.dumps({k:v for k,v in result.items() if k!='records'}))
    elif args.cmd=='paper':paper(args.slug,args.title)
    elif args.cmd=='snapshot':snapshot(args.manifest,args.output)
    elif args.cmd=='update':update(args.id,args.expected,args.body_file)
    elif args.cmd=='new':new(args.type,args.title,args.project,args.domain,args.work_package)
    elif args.cmd=='check': print(f'Validated {len(records())} records')
    elif args.cmd=='build': print(f'Built dashboard from {len(build())} records')
    else:
        if args.cmd=='launch':
            import urllib.request, webbrowser, threading
            address=f'http://127.0.0.1:{args.port}'
            try:
                with urllib.request.urlopen(address+'/api/health',timeout=2) as response:
                    existing=json.load(response)
                if isinstance(existing,dict) and existing.get('service')=='Desk' and existing.get('workspace')==str(ROOT):
                    webbrowser.open(address)
                    return
                raise ValueError('Port is in use by a different application')
            except (OSError,TimeoutError):
                pass
        srv=create_server(args.port)
        print(f'Desk: http://127.0.0.1:{srv.server_port}',flush=True)
        if args.cmd=='launch':
            threading.Timer(0.2,lambda:webbrowser.open(address)).start()
        srv.serve_forever()
if __name__=='__main__': main()
