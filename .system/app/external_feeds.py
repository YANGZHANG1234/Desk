"""Read-only view of records exported by local companion systems (PAICC, FIC).

Shared export contract v1: ~/Library/Application Support/PAICC/desk-export/<source>/
holds Markdown records with YAML frontmatter plus a manifest.json. Desk only reads
these folders. This module must never write, rename or delete files, never open
network connections and never start processes; tests enforce this with an AST check.

Isolation: these records are served only by GET /api/external. They are not part
of phd.records(), the generated dashboard/index files, or any Codex/agent prompt.
"""
import datetime as dt, hashlib, hmac, json, os, secrets, stat, sys, threading, time
from pathlib import Path

EXPORT_ROOT = Path(os.environ.get('DESK_EXPORT_ROOT') or Path.home() / 'Library/Application Support/PAICC/desk-export')
SOURCES = {'paicc': 'PAICC', 'fic': 'FIC'}
KINDS = ['meeting', 'task', 'briefing', 'milestone', 'finance_daily', 'finance_alert', 'finance_review', 'finance_holdings', 'learning']
LOCKED_SOURCES = ('fic',)
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


# ---------------------------------------------------------------------------
# Finance lock (FD-043). Enforced on the server: while locked, no FIC record,
# title, count or manifest field leaves this process. The password hash lives
# in ~/Library/Application Support/PAICC/desk-lock.json (written by FIC's
# `desk lock set`) and is re-read on every attempt, so a reset applies at once.
# Unlock state is an in-memory token: it is lost on restart and expires after
# IDLE_SECONDS without use. Passwords are never stored, logged or echoed.
IDLE_SECONDS = 15 * 60
MAX_FAILURES = 5
LOCKOUT_SECONDS = 5 * 60
COOKIE = 'desk_finance'
RESET_HINT = 'uv run python -m app.finance.cli desk lock set  (in pacc-fic/backend)'
_lock = threading.Lock()
_tokens = {}
_failures = {'count': 0, 'until': 0.0}


def lock_file():
    return Path(os.environ.get('DESK_LOCK_FILE') or Path(EXPORT_ROOT).parent / 'desk-lock.json')


def _lock_config():
    """Return validated scrypt parameters, or None when missing or unsafe."""
    try:
        path = lock_file()
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_uid != os.getuid(): return None
        data = json.loads(_read_bytes(path).decode('utf-8'))
        if data.get('algo') != 'scrypt': return None
        n, r, p, dklen = (int(data[k]) for k in ('n', 'r', 'p', 'dklen'))
        salt, digest = bytes.fromhex(data['salt']), bytes.fromhex(data['hash'])
        if not (2 <= n <= 2 ** 18 and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4 and 16 <= dklen <= 128): return None
        if len(salt) < 16 or len(digest) != dklen: return None
        return {'n': n, 'r': r, 'p': p, 'dklen': dklen, 'salt': salt, 'hash': digest}
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError):
        return None


def _now():
    return time.monotonic()


def _valid(token):
    if not isinstance(token, str) or not token: return False
    now = _now()
    with _lock:
        for key, seen in list(_tokens.items()):
            if now - seen > IDLE_SECONDS: del _tokens[key]
        match = next((key for key in _tokens if hmac.compare_digest(key, token)), None)
        if match: _tokens[match] = now
        return bool(match)


def lock_status(token=None):
    now = _now()
    with _lock: wait = max(0, int(_failures['until'] - now + 0.999))
    return {'locked': not _valid(token), 'configured': _lock_config() is not None,
            'retry_after': wait, 'idle_minutes': IDLE_SECONDS // 60, 'reset_hint': RESET_HINT}


def unlock(password):
    """Return (status, body, token). Token is None unless the password matched."""
    now = _now()
    with _lock:
        if now < _failures['until']:
            return 429, {'locked': True, 'error': 'Too many attempts. Try again later.', 'retry_after': int(_failures['until'] - now + 0.999)}, None
    config = _lock_config()
    if config is None:
        return 503, {'locked': True, 'configured': False, 'error': 'No finance password is set.', 'reset_hint': RESET_HINT}, None
    ok = isinstance(password, str) and 0 < len(password) <= 128
    try:
        derived = hashlib.scrypt(password.encode('utf-8'), salt=config['salt'], n=config['n'], r=config['r'], p=config['p'],
                                 dklen=config['dklen'], maxmem=256 * 1024 * 1024) if ok else b''
    except (ValueError, MemoryError):
        derived = b''
    with _lock:
        if derived and hmac.compare_digest(derived, config['hash']):
            _failures.update(count=0, until=0.0)
            token = secrets.token_urlsafe(32); _tokens[token] = _now()
            return 200, {'locked': False, 'idle_minutes': IDLE_SECONDS // 60}, token
        _failures['count'] += 1
        if _failures['count'] >= MAX_FAILURES:
            _failures.update(count=0, until=_now() + LOCKOUT_SECONDS)
            return 429, {'locked': True, 'error': 'Too many attempts. Try again later.', 'retry_after': LOCKOUT_SECONDS}, None
        return 401, {'locked': True, 'error': 'Wrong password.', 'attempts_left': MAX_FAILURES - _failures['count']}, None


def relock(token=None):
    with _lock:
        if token: _tokens.pop(token, None)
        else: _tokens.clear()


def locked_stub(key):
    """What a locked source reveals: its name and that it is locked. Nothing else."""
    return {'source': key, 'label': SOURCES[key], 'locked': True, 'exists': None, 'manifest': None,
            'schema_ok': True, 'warnings': [], 'records': []}


def guarded_snapshot(token=None, root=None):
    unlocked = _valid(token)
    snap = snapshot(root) if unlocked else dict(snapshot_sources(['paicc'], root))
    if not unlocked:
        # Defence in depth: nothing finance-shaped leaks through another source's folder.
        for source in snap['sources']:
            source['records'] = [r for r in source['records'] if r.get('declared_source') not in LOCKED_SOURCES
                                 and not str(r.get('kind', '')).startswith('finance_') and r.get('kind') != 'learning']
        snap['sources'].append(locked_stub('fic'))
    snap['finance_locked'] = not unlocked
    return snap


def snapshot_sources(keys, root=None):
    sources = [load_source(key, root) for key in keys]
    return {'export_root': str(Path(root or EXPORT_ROOT)), 'schema_version': SCHEMA_VERSION, 'kinds': KINDS,
            'generated_at': dt.datetime.now().astimezone().isoformat(timespec='seconds'), 'sources': sources}

