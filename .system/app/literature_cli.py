#!/usr/bin/env python3
"""Desk literature jobs. Open Desk first; jobs continue while its service runs."""
import argparse,json,base64,urllib.request
from pathlib import Path
URL='http://127.0.0.1:8766'
def call(path,data=None):
 req=urllib.request.Request(URL+'/api/literature/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Origin':URL,'X-PhD-Action':'1'})
 with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8-sig')
def main():
 p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='cmd',required=True)
 a=s.add_parser('upload');a.add_argument('files',nargs='+')
 for kind in ['enrich','read']:
  a=s.add_parser(kind);a.add_argument('id')
 a=s.add_parser('compare');a.add_argument('ids',nargs='+')
 for kind in ['candidates','jobs','links','matrix']:s.add_parser(kind)
 a=s.add_parser('retry');a.add_argument('id')
 args=p.parse_args()
 if args.cmd=='upload':
  for name in args.files:
   file=Path(name)
   if file.stat().st_size>25*1024*1024:raise ValueError('PDF exceeds 25 MB')
   print(call('jobs',{'kind':'upload','payload':{'name':file.name,'data':base64.b64encode(file.read_bytes()).decode()}}))
 elif args.cmd=='jobs':print(call('jobs'))
 elif args.cmd=='matrix':print(call('matrix.csv'),end='')
 elif args.cmd=='links':print(call('links',{}))
 elif args.cmd=='retry':print(call('control',{'id':args.id,'action':'retry'}))
 else:print(call('jobs',{'kind':args.cmd,'payload':{'id':args.id} if hasattr(args,'id') else {'ids':args.ids} if hasattr(args,'ids') else {}}))
if __name__=='__main__':main()
