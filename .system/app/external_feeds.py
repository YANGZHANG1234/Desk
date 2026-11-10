"""Read-only view of records exported by local companion systems (PAICC, FIC).

Shared export contract v1: ~/Library/Application Support/PAICC/desk-export/<source>/
holds Markdown records with YAML frontmatter plus a manifest.json. Desk only reads
these folders. This module must never write, rename or delete files, never open
network connections and never start processes; tests enforce this with an AST check.

Isolation: these records are served only by GET /api/external. They are not part
of phd.records(), the generated dashboard/index files, or any Codex/agent prompt.
"""
import datetime as dt, json, os, stat, sys
from pathlib import Path

EXPORT_ROOT = Path(os.environ.get('DESK_EXPORT_ROOT') or Path.home() / 'Library/Application Support/PAICC/desk-export')
SOURCES = {'paicc': 'PAICC', 'fic': 'FIC'}
KINDS = ['meeting', 'task', 'briefing', 'milestone', 'finance_daily', 'finance_alert', 'finance_review', 'learning']
SCHEMA_VERSION = 1
MAX_FILE_BYTES = 512 * 1024
MAX_RECORDS = 2000
MAX_DEPTH = 3
LINK_SCHEMES = ('message:', 'https:', 'http:', 'ical:', 'x-apple-reminderkit:', 'obsidian:')


def _yaml():
    vendor = str(Path(__file__).resolve().parent / 'vendor')
    if vendor not in sys.path: sys.path.insert(0, vendor)
    import yaml
    return yaml


def _read_bytes(path):
    """Open without following symlinks, regular files only, bounded size."""
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode): raise ValueError('not a regular file')
        if info.st_size > MAX_FILE_BYTES: raise ValueError('file too large')
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk: break
            chunks.append(chunk)
        return b''.join(chunks)
    finally:
        os.close(fd)


def _plain(value):
    """Make YAML values JSON-safe (dates become ISO strings)."""
    if isinstance(value, (dt.date, dt.datetime)): return value.isoformat()
    if isinstance(value, dict): return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_plain(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)): return value
    return str(value)


def _parse(text):
    if not text.startswith('---\n'): raise ValueError('missing frontmatter')
    head, sep, body = text[4:].partition('\n---')
    if not sep: raise ValueError('unterminated frontmatter')
    meta = _yaml().safe_load(head)
    if not isinstance(meta, dict): raise ValueError('frontmatter must be a mapping')
    return _plain(meta), body.lstrip('-').strip()


def safe_link(value):
    if not isinstance(value, str): return ''
    link = value.strip()
    if any(c in link for c in '\n\r\t<>"\'`') or len(link) > 2000: return ''
    return link if link.lower().startswith(LINK_SCHEMES) else ''


def is_demo(meta):
    tags = meta.get('tags') if isinstance(meta.get('tags'), list) else []
    return bool(meta.get('demo') is True or meta.get('is_demo') is True or str(meta.get('data_mode', '')).lower() == 'demo'
                or any(str(t).lower() in ('demo', '演示') for t in tags) or '演示' in str(meta.get('title', '')))


def _manifest(folder):
    path = folder / 'manifest.json'
    if not path.exists() and not path.is_symlink(): return None, None
    try:
        data = json.loads(_read_bytes(path).decode('utf-8'))
        if not isinstance(data, dict): raise ValueError('manifest must be an object')
        return _plain(data), None
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return None, f'manifest.json unreadable: {exc}'


def _files(folder):
    out = []
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        depth = len(Path(dirpath).relative_to(folder).parts)
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.')) if depth < MAX_DEPTH else []
        for name in sorted(filenames):
            if name.startswith('.') or not name.endswith('.md') or name.endswith('.tmp.md'): continue
            out.append(Path(dirpath) / name)
    return out


def load_source(key, root=None):
    root = Path(root or EXPORT_ROOT)
    folder = root / key
    result = {'source': key, 'label': SOURCES[key], 'path': str(folder), 'exists': False, 'manifest': None,
              'schema_ok': True, 'warnings': [], 'records': []}
    if folder.is_symlink() or not folder.is_dir():
        if folder.is_symlink(): result['warnings'].append('Export folder is a symlink; ignored.')
        return result
    result['exists'] = True
    manifest, error = _manifest(folder)
    if error: result['warnings'].append(error)
    result['manifest'] = manifest
    if manifest is not None and manifest.get('schema_version') != SCHEMA_VERSION:
        result['schema_ok'] = False
        result['warnings'].append(f"Unsupported schema_version {manifest.get('schema_version')!r}; Desk understands version {SCHEMA_VERSION}. Records are shown best-effort.")
    skipped = 0
    for path in _files(folder)[:MAX_RECORDS]:
        try:
            meta, body = _parse(_read_bytes(path).decode('utf-8'))
        except Exception:  # OSError, decode and YAML errors: skip the file, keep the view working
            skipped += 1
            continue
        kind = meta.get('kind') if meta.get('kind') in KINDS else 'other'
        declared = meta.get('source')
        rel = str(path.relative_to(folder))
        result['records'].append(dict(meta,
            source=key, source_label=SOURCES[key], declared_source=declared,
            source_mismatch=bool(declared) and declared != key,
            source_id=str(meta.get('source_id') or rel), kind=kind,
            read_only=True, demo=is_demo(meta), link=safe_link(meta.get('link')),
            body=body, file=rel))
    if skipped: result['warnings'].append(f'{skipped} file(s) could not be read and were skipped.')
    return result


def snapshot(root=None):
    sources = [load_source(key, root) for key in SOURCES]
    return {'export_root': str(Path(root or EXPORT_ROOT)), 'schema_version': SCHEMA_VERSION, 'kinds': KINDS,
            'generated_at': dt.datetime.now().astimezone().isoformat(timespec='seconds'), 'sources': sources}
