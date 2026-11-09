"""Read-only Zotero local API bridge. Desk owns notes, links and reading state."""
import datetime as dt
import fcntl
import hashlib
import json
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser

BASE = 'http://127.0.0.1:23119/api/'

def normalized(value):
    return re.sub(r'[^\w]', '', value.lower())

def doi(value):
    match = re.search(r'10\.\d{4,9}/[^\s<>"\]]+', value or '', re.I)
    return match.group(0).rstrip('.,;)').lower() if match else ''

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]
    def handle_data(self, value): self.parts.append(value)
    def handle_endtag(self, tag):
        if tag in ('p','div','li','br'): self.parts.append('\n')

def plain(value):
    parser=PlainText(); parser.feed(value); return ''.join(parser.parts).strip()

def fetch():
    def get(path, server=None):
        headers={'Zotero-API-Version':'3'}
        if server: headers['Zotero-Server-ID']=server
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE+path,headers=headers), timeout=15) as response:
                identity=response.headers.get('Zotero-Server-ID')
                if not identity or (server and identity!=server): raise RuntimeError('Zotero library changed. Refresh again.')
                return identity,json.load(response)
        except (urllib.error.URLError,TimeoutError) as exc:
            raise RuntimeError('Open Zotero and enable its local API in Settings → Advanced, then try again.') from exc
    server,items=get('users/0/items')
    _,collections=get('users/0/collections',server)
    return server,items,collections

def sync(app, snapshot=None):
    server,items,collections=snapshot or fetch()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',server): raise ValueError('Invalid Zotero library identity')
    raw={x['key']:x['data'] for x in items}
    names={x['key']:x['data']['name'] for x in collections}
    now=dt.datetime.now().astimezone().isoformat(timespec='seconds')
    added=linked=changed=0
    with (app.SYS/'index/write.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rs=app.records()
        for key,item in raw.items():
            if item.get('itemType') in ('note','attachment','annotation') or item.get('deleted') or not item.get('title'): continue
            if not re.fullmatch('[A-Z0-9]{8}',key): continue
            children=[dict(x,key=k) for k,x in raw.items() if x.get('parentItem')==key and not x.get('deleted')]
            attachments=[{'key':x['key'],'title':x.get('title','Attachment'),'content_type':x.get('contentType','')} for x in children if x.get('itemType')=='attachment']
            attachment_keys={x['key'] for x in attachments}
            annotations=[{'key':k,'attachment':x.get('parentItem'),'text':x.get('annotationText',''),'comment':x.get('annotationComment',''),'page':x.get('annotationPageLabel',''),'color':x.get('annotationColor','')} for k,x in raw.items() if x.get('itemType')=='annotation' and x.get('parentItem') in attachment_keys and not x.get('deleted')]
            notes=[{'key':x['key'],'text':plain(x.get('note',''))} for x in children if x.get('itemType')=='note' and not plain(x.get('note','')).startswith('Desk records:')]
            z={'server_id':server,'key':key,'title':item['title'],'item_type':item['itemType'],'doi':item.get('DOI',''),'date':item.get('date',''),'creators':item.get('creators',[]),'publication':(item.get('publicationTitle') or item.get('proceedingsTitle') or item.get('conferenceName') or item.get('bookTitle') or item.get('publisher') or item.get('institution') or ''),'collections':[names[c] for c in item.get('collections',[]) if c in names],'attachments':attachments,'annotations':annotations,'notes':notes}
            candidates=[r for r in rs if r['type']=='knowledge' and r.get('zotero',{}).get('server_id')==server and r.get('zotero',{}).get('key')==key]
            if not candidates:
                # Never remap a stable key or match a synthesis mentioning many papers.
                for r in rs:
                    if r['type']!='knowledge' or r.get('zotero'): continue
                    dois={doi(s) for s in r.get('sources',[]) if doi(s)}
                    if normalized(r['title'])==normalized(item['title']) or (doi(item.get('DOI')) and dois=={doi(item['DOI'])} and '## Citation' in r['body']): candidates.append(r)
            if candidates:
                for r in candidates:
                    # A Desk deletion stays deleted. Do not recreate it on the next sync.
                    if r.get('deleted_at'): continue
                    path=app.ROOT/r['path'];previous=path.read_bytes();meta,body=app.read(path)
                    if meta.get('zotero')==z: continue
                    if not meta.get('zotero'): linked+=1
                    meta['zotero']=z
                    if path.read_bytes()!=previous: raise RuntimeError('A note changed during refresh. Try again.')
                    app.atomic_write(app.SYS/'history'/r['id']/(hashlib.sha256(previous).hexdigest()+'.md'),previous.decode())
                    app.atomic_write(path,app.serialize(meta,body));changed+=1
            else:
                rid='zotero-'+hashlib.sha256(server.encode()).hexdigest()[:8]+'-'+key.lower()
                if any(r['id']==rid for r in rs): continue
                meta={'id':rid,'type':'knowledge','title':item['title'],'updated':dt.date.today().isoformat(),'status':'captured','domain':'research','projects':[],'work_packages':[],'sources':(['https://doi.org/'+item['DOI']] if item.get('DOI') else [item['url']] if item.get('url','').startswith(('http://','https://')) else []),'kind':'Paper' if item['itemType']=='journalArticle' else item['itemType'],'access_level':'metadata','agent_reading':'not_read','human_reading':'unknown','zotero':z}
                path=app.W/'Knowledge'/(rid+'.md')
                if path.exists(): raise RuntimeError('Record ID already exists')
                app.atomic_write(path,app.serialize(meta,''));added+=1
                rs.append(dict(meta,path=str(path.relative_to(app.ROOT)),body=''))
        config=app.registry()
        config['connections']['zotero']={'status':'connected','mode':'local_read_only','server_id':server,'last_sync':now,'items':sum(x.get('itemType') not in ('note','attachment','annotation') and not x.get('deleted') for x in raw.values())}
        app.atomic_write(app.SYS/'config/registry.json',json.dumps(config,ensure_ascii=False,indent=2)+'\n')
        app.atomic_write(app.SYS/'index/zotero'/server/'snapshot.json',json.dumps({'synced':now,'items':items,'collections':collections},ensure_ascii=False))
    return {'records':app.records(),'added':added,'linked':linked,'changed':changed,'connection':config['connections']['zotero']}
