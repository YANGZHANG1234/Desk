"""Desk's own "done" marks for exported mail tasks.

The export folders stay read-only: ticking an exported task in Desk records the task's
id here, in Desk's own state folder, and nowhere else. The file holds only opaque
task ids and the time they were ticked: no titles, senders or email text. The mail assistant may
read it to stop listing tasks the user has finished.
"""
import datetime as dt, json, os, re, tempfile, threading
from pathlib import Path

SCHEMA_VERSION = 1
MAX_MARKS = 5000
ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}')
_lock = threading.Lock()


def marks_file():
    return Path(os.environ.get('DESK_TASK_MARKS') or Path.home() / 'Library/Application Support/Desk/task-marks.json')


def load():
    """Return {task_id: done_at}. A missing or damaged file means no marks."""
    try:
        path = marks_file()
        if path.is_symlink(): return {}
        data = json.loads(path.read_text(encoding='utf-8'))
        done = data.get('done') if isinstance(data, dict) else None
        if not isinstance(done, dict): return {}
        return {k: str(v) for k, v in done.items() if isinstance(k, str) and ID_PATTERN.fullmatch(k)}
    except (OSError, ValueError):
        return {}


def _save(done):
    path = marks_file()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink(): raise ValueError('Marks file is a symlink')
    data = {'schema_version': SCHEMA_VERSION, 'source': 'desk', 'kind': 'task_marks',
            'updated_at': dt.datetime.now().astimezone().isoformat(timespec='seconds'), 'done': done}
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.task-marks.', suffix='.tmp')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def set_done(ids, done):
    """Mark (or unmark) task ids. Returns the full mark map."""
    if not isinstance(ids, list) or not 0 < len(ids) <= 50: raise ValueError('Give 1-50 task ids')
    if not all(isinstance(i, str) and ID_PATTERN.fullmatch(i) for i in ids): raise ValueError('Invalid task id')
    if not isinstance(done, bool): raise ValueError('done must be true or false')
    with _lock:
        marks = load()
        now = dt.datetime.now().astimezone().isoformat(timespec='seconds')
        for i in ids:
            if done: marks.setdefault(i, now)
            else: marks.pop(i, None)
        if len(marks) > MAX_MARKS:
            marks = dict(sorted(marks.items(), key=lambda kv: kv[1])[-MAX_MARKS:])
        _save(marks)
        return marks
