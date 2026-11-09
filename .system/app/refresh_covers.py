"""Refresh cached first-page previews. Requires Poppler's pdftoppm."""
import concurrent.futures, hashlib, json, shutil, subprocess
from pathlib import Path
import phd

def main():
    if not shutil.which('pdftoppm'):
        raise SystemExit('Install Poppler to generate PDF covers.')
    target=phd.SYS/'index/thumbnails';target.mkdir(parents=True,exist_ok=True)
    config_path=phd.SYS/'config/presentation.json'
    config=json.loads(config_path.read_text()) if config_path.exists() else {}
    pdfs={p for r in phd.records() for p in r.get('local_paths',[]) if p.lower().endswith('.pdf') and (phd.ROOT/p).is_file()}
    def render(path):
        key=hashlib.sha256(path.encode()).hexdigest()[:24]
        output=target/(key+'.png')
        if not output.exists():
            result=subprocess.run(['pdftoppm','-f','1','-singlefile','-scale-to','600','-png',str(phd.ROOT/path),str(target/key)],capture_output=True)
            if result.returncode: return path,None
        return path,output.name
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results=dict(pool.map(render,sorted(pdfs)))
    config.setdefault('thumbnails',{}).update({p:v for p,v in results.items() if v})
    phd.atomic_write(config_path,json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    phd.build()
    print(f'{sum(bool(v) for v in results.values())} PDF previews available; {sum(v is None for v in results.values())} failed.')
if __name__=='__main__':main()
