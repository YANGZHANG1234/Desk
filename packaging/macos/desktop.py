"""Start the bundled Desk server in the user's writable workspace."""
import sys
from pathlib import Path

resources = Path(__file__).resolve().parent
sys.path.insert(0, str(resources / '.system/app'))
import phd


def main():
    root = Path.home() / 'Library/Application Support/Desk'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    phd.ROOT = root.resolve()
    phd.W = phd.ROOT / 'Records'
    phd.SYS = phd.ROOT / '.system'
    guide = phd.ROOT / 'README.md'
    if not guide.exists():
        phd.atomic_write(guide, (resources / 'README.md').read_text())

    with phd.create_server(0) as server:
        print(f'http://127.0.0.1:{server.server_port}/', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
