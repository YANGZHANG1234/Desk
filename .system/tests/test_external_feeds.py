"""Read-only PAICC/FIC export integration. All sample data below is fabricated."""
import ast, hashlib, hmac, http.client, json, os, shutil, stat, sys, tempfile, threading, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

APP = Path(__file__).parents[1] / 'app'
sys.path.insert(0, str(APP))
import phd, external_feeds as feeds, literature_graph as g, literature_jobs as jobs

SENTINEL = 'ZZ-EXPORT-SENTINEL-7f3a'


def record(folder, name, **meta):
    body = meta.pop('body', f'Fabricated body {SENTINEL}')
    meta.setdefault('read_only', True)
    meta.setdefault('updated_at', '2026-11-10T08:00:00+00:00')
    head = '\n'.join(f'{k}: {json.dumps(v, ensure_ascii=False)}' for k, v in meta.items())
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(f'---\n{head}\n---\n\n{body}\n')
    path.chmod(0o600)
    return path


def fixture(root, schema=1):
    paicc, fic = root / 'paicc', root / 'fic'
    for folder in (paicc, fic): folder.mkdir(parents=True, mode=0o700)
    record(paicc, 'meeting-1.md', source='paicc', source_id='m1', kind='meeting', title=f'Supervisor sync {SENTINEL}',
           start_at='2026-11-10T14:00:00+00:00', end_at='2026-11-10T15:00:00+00:00', link='ical://event/abc')
    record(paicc, 'task-1.md', source='paicc', source_id='t1', kind='task', title='Reply to reviewer', status='todo', priority='high',
           deadline_at='2026-11-12T17:00:00+00:00', deadline_kind='hard', sender_name='A. Example',
           summary_zh='示例摘要', summary_en='Example summary', link='message://%3Cfake-id@example.invalid%3E')
    record(paicc, 'briefing-1.md', source='paicc', source_id='b1', kind='briefing', title='Daily briefing')
    record(paicc, 'sub/milestone-1.md', source='paicc', source_id='ms1', kind='milestone', title='Chapter 3 draft', deadline_at='2026-12-01T00:00:00+00:00')
    record(paicc, 'bad-link.md', source='paicc', source_id='x1', kind='task', title='Unsafe link', link='javascript:alert(1)')
    record(fic, 'daily.md', source='fic', source_id='f1', kind='finance_daily', title='演示 Finance daily', demo=True)
    record(fic, 'alert.md', source='fic', source_id='f2', kind='finance_alert', title='Alert', tags=['demo'])
    record(fic, 'learn.md', source='fic', source_id='l1', kind='learning', title='Bond duration basics')
    (paicc / '.tmp-partial.md').write_text('---\nkind: task\n')  # in-progress atomic write: ignored
    (paicc / 'broken.md').write_text('no frontmatter')
    for folder, count in ((paicc, 5), (fic, 3)):
        (folder / 'manifest.json').write_text(json.dumps({'exported_at': '2026-11-10T08:00:00+00:00', 'record_count': count, 'schema_version': schema}))
    return root


def tree_state(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else 'dir', p.stat().st_mtime_ns, p.stat().st_mode)
            for p in sorted(root.rglob('*'))} | {'.': root.stat().st_mtime_ns}


class ExternalFeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.export = fixture(self.root / 'desk-export')
        self.old_root = feeds.EXPORT_ROOT; feeds.EXPORT_ROOT = self.export

    def tearDown(self):
        feeds.EXPORT_ROOT = self.old_root; self.tmp.cleanup()

    def all(self, snap=None):
        snap = snap or feeds.snapshot()
        return {r['source_id']: r for s in snap['sources'] for r in s['records']}

    def test_reads_every_kind_read_only_with_source(self):
        rs = self.all()
        self.assertEqual({r['kind'] for r in rs.values()}, {'meeting', 'task', 'briefing', 'milestone', 'finance_daily', 'finance_alert', 'learning'})
        self.assertTrue(all(r['read_only'] is True for r in rs.values()))
        self.assertEqual(rs['t1']['source_label'], 'PAICC'); self.assertEqual(rs['f1']['source_label'], 'FIC')
        self.assertEqual(rs['t1']['link'], 'message://%3Cfake-id@example.invalid%3E')
        self.assertEqual(rs['x1']['link'], '', 'unsafe link schemes are dropped')
        self.assertTrue(rs['f1']['demo'] and rs['f2']['demo']); self.assertFalse(rs['l1']['demo'])
        self.assertEqual(rs['ms1']['file'], 'sub/milestone-1.md')
        paicc = feeds.snapshot()['sources'][0]
        self.assertTrue(paicc['schema_ok']); self.assertTrue(any('skipped' in w for w in paicc['warnings']))

    def test_finance_review_kind_is_recognised_and_not_demo(self):
        record(self.export / 'fic', 'review-2026-11-10.md', source='fic', source_id='r1', kind='finance_review', status='confirmed', demo=False, tags=['review'], title='Sample review', body='| a | b |\n|---|---|\n| 1 | 2 |')
        r = self.all()['r1']
        self.assertEqual(r['kind'], 'finance_review'); self.assertFalse(r['demo']); self.assertIn('| 1 | 2 |', r['body'])

    def test_missing_and_empty_folders(self):
        snap = feeds.snapshot(self.root / 'nowhere')
        self.assertEqual([s['exists'] for s in snap['sources']], [False, False])
        self.assertEqual(sum(len(s['records']) for s in snap['sources']), 0)
        empty = self.root / 'empty'; (empty / 'paicc').mkdir(parents=True)
        snap = feeds.snapshot(empty)
        self.assertTrue(snap['sources'][0]['exists']); self.assertEqual(snap['sources'][0]['records'], []); self.assertEqual(snap['sources'][0]['warnings'], [])

    def test_unknown_schema_version_warns_without_crashing(self):
        other = fixture(self.root / 'v2', schema=2)
        snap = feeds.snapshot(other)
        self.assertFalse(snap['sources'][0]['schema_ok'])
        self.assertTrue(any('schema_version' in w for w in snap['sources'][0]['warnings']))
        self.assertTrue(snap['sources'][0]['records'])
        (other / 'fic/manifest.json').write_text('{not json')
        self.assertTrue(any('manifest' in w for w in feeds.snapshot(other)['sources'][1]['warnings']))

    def test_symlinks_are_not_followed(self):
        outside = self.root / 'outside.md'; outside.write_text('---\nkind: task\ntitle: secret\n---\n')
        (self.export / 'paicc/link.md').symlink_to(outside)
        self.assertNotIn('secret', json.dumps(feeds.snapshot()))

    def test_reader_never_modifies_exports(self):
        before = tree_state(self.export)
        feeds.snapshot(); feeds.snapshot(self.export)
        self.assertEqual(tree_state(self.export), before)

    def test_module_has_no_write_network_or_process_operations(self):
        tree = ast.parse((APP / 'external_feeds.py').read_text())
        banned_modules = {'socket', 'urllib', 'http', 'subprocess', 'shutil', 'requests', 'ssl', 'ftplib', 'smtplib', 'tempfile', 'sqlite3'}
        banned_calls = {'write', 'write_text', 'write_bytes', 'unlink', 'rename', 'replace', 'mkdir', 'makedirs', 'rmdir', 'remove',
                        'removedirs', 'rmtree', 'touch', 'chmod', 'chown', 'symlink_to', 'link', 'truncate', 'system', 'popen',
                        'urlopen', 'atomic_write', 'utime', 'open'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse({a.name.split('.')[0] for a in node.names} & banned_modules)
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or '').split('.')[0], banned_modules)
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
                if name == 'open' and isinstance(node.func, ast.Attribute) and getattr(node.func.value, 'id', '') == 'os':
                    flags = {n.attr for n in ast.walk(node.args[1]) if isinstance(n, ast.Attribute)}
                    self.assertLessEqual(flags, {'O_RDONLY', 'O_NOFOLLOW'}); continue
                self.assertNotIn(name, banned_calls, f'external_feeds.py line {node.lineno} calls {name}')
        self.assertNotIn('__import__', (APP / 'external_feeds.py').read_text())

    def test_agent_network_and_index_code_cannot_reach_exports(self):
        # Static guard: only phd.py's GET handler may import the export reader.
        for path in APP.glob('*.py'):
            if path.name in ('external_feeds.py', 'phd.py'): continue
            text = path.read_text()
            for needle in ('external_feeds', 'desk-export', 'PAICC', 'EXPORT_ROOT'):
                self.assertNotIn(needle, text, f'{path.name} must not reference {needle}')
        source = (APP / 'phd.py').read_text(); tree = ast.parse(source)
        users = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and 'external_feeds' in ast.get_source_segment(source, n)]
        self.assertEqual(sorted(n.name for n in users), ['do_GET', 'finance_post', 'finance_token'])
        post = ast.get_source_segment(source, next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'finance_post'))
        for call in ('snapshot', 'load_source', 'guarded_snapshot'):
            self.assertNotIn(call, post, 'unlock/lock handlers never return records')
        self.assertNotIn('/api/external', ast.get_source_segment(source, next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'do_POST')))
        js = (APP / 'desk.js').read_text()
        self.assertEqual(js.count("'/api/external'"), 1, 'the UI only fetches exports with a plain GET')
        self.assertNotIn('externalData', js[js.index('async function mutate('):js.index('let zoteroSyncing')])

    def test_exports_never_enter_records_index_or_agent_prompts(self):
        ws = self.root / 'ws'
        for name in ('config', 'templates', 'context'):
            shutil.copytree(APP.parent / name, ws / '.system' / name)
        (ws / '.system/index').mkdir(parents=True)
        old = (phd.ROOT, phd.W, phd.SYS); phd.ROOT, phd.W, phd.SYS = ws, ws / 'Records', ws / '.system'
        try:
            m = SimpleNamespace(ROOT=phd.ROOT, W=phd.W, SYS=phd.SYS, read=phd.read, serialize=phd.serialize, atomic_write=phd.atomic_write, records=phd.records, build=phd.build)
            for i in ('a', 'b'):
                g.save(m, dict(id='paper-' + i, type='knowledge', title='Sample paper ' + i, doi='10.1234/' + i, kind='Paper', status='captured',
                               updated='2026-11-10', projects=[], sources=[]), 'Fake note ' + i)
            prompts = []
            def fake_agent(_m, prompt, _folder):
                prompts.append(prompt); return {'comparison': 'ok'}
            with patch.object(jobs, 'agent', fake_agent):
                jobs.run(m, {'id': 'job1', 'kind': 'compare', 'payload': json.dumps({'ids': ['paper-a', 'paper-b']})})
            self.assertTrue(prompts)
            phd.build()
            haystack = '\n'.join(prompts) + json.dumps(phd.records()) + (ws / '.system/index/dashboard.html').read_text() + (ws / '.system/index/records.json').read_text() + (ws / 'Home.md').read_text()
            self.assertIn('Supervisor sync', json.dumps(feeds.snapshot()))
            self.assertNotIn(SENTINEL, haystack)
            self.assertNotIn('Reply to reviewer', haystack)
        finally:
            phd.ROOT, phd.W, phd.SYS = old

    def test_http_endpoint_is_get_only_and_same_origin(self):
        server = phd.LocalServer(('127.0.0.1', 0), phd.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def request(method, headers=None):
                c = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                c.request(method, '/api/external', body='{}' if method == 'POST' else None, headers=headers or {})
                r = c.getresponse(); return r.status, r.read()
            status, body = request('GET')
            self.assertEqual(status, 200)
            self.assertEqual(len(self.all(json.loads(body))), 5, 'FIC withheld while locked')
            self.assertEqual(request('GET', {'Sec-Fetch-Site': 'cross-site'})[0], 403)
            origin = f'http://127.0.0.1:{server.server_port}'
            self.assertEqual(request('POST', {'Origin': origin, 'X-PhD-Action': '1', 'Content-Type': 'application/json'})[0], 404)
            before = tree_state(self.export); request('GET'); self.assertEqual(tree_state(self.export), before)
        finally:
            server.shutdown(); server.server_close()


PASSWORD = '482916'  # fabricated test password


def write_lock(path, password=PASSWORD, mode=0o600):
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    path.write_text(json.dumps({'version': 1, 'scope': ['fic'], 'algo': 'scrypt', 'n': 2 ** 14, 'r': 8, 'p': 1, 'dklen': 32,
                                'salt': salt.hex(), 'hash': digest.hex()}))
    path.chmod(mode)


class FinanceLockTests(unittest.TestCase):
    FIC_TITLES = ('演示 Finance daily', 'Alert', 'Bond duration basics')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.export = fixture(self.root / 'desk-export')
        record(self.export / 'fic', 'holdings-2026-11-11.md', source='fic', source_id='h1', kind='finance_holdings', title='Holdings', body='| 账户 | CNY |\n|---|---|\n| A | 1 |')
        self.lock = self.root / 'desk-lock.json'; write_lock(self.lock)
        self.old = (feeds.EXPORT_ROOT, os.environ.get('DESK_LOCK_FILE'))
        feeds.EXPORT_ROOT = self.export; os.environ.pop('DESK_LOCK_FILE', None)
        feeds.relock(); feeds._failures.update(count=0, until=0.0)
        self.clock = [1000.0]; self.patch = patch.object(feeds, '_now', lambda: self.clock[0]); self.patch.start()
        self.server = phd.LocalServer(('127.0.0.1', 0), phd.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.patch.stop()
        feeds.EXPORT_ROOT = self.old[0]; feeds.relock(); feeds._failures.update(count=0, until=0.0)
        if self.old[1] is not None: os.environ['DESK_LOCK_FILE'] = self.old[1]
        self.tmp.cleanup()

    def call(self, method, path, body=None, cookie=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        h = {'Host': f'127.0.0.1:{self.server.server_port}'} | (headers or {})
        if method == 'POST': h.update({'Origin': self.origin, 'X-PhD-Action': '1', 'Content-Type': 'application/json'})
        if cookie: h['Cookie'] = cookie
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse(); data = r.read()
        return r.status, data.decode(), r.getheader('Set-Cookie')

    def unlock(self, password=PASSWORD):
        return self.call('POST', '/api/finance/unlock', {'password': password})

    def assert_no_fic(self, text):
        for title in self.FIC_TITLES + ('Holdings', 'holdings-2026', 'waiting_for_lock', 'lock_required', '| A | 1 |', '/fic'):
            self.assertNotIn(title, text)

    def test_locked_by_default_everywhere(self):
        status, body, _ = self.call('GET', '/api/external')
        self.assertEqual(status, 200); data = json.loads(body)
        self.assertTrue(data['finance_locked'])
        fic = next(s for s in data['sources'] if s['source'] == 'fic')
        self.assertEqual(fic['records'], []); self.assertIsNone(fic['manifest']); self.assertIsNone(fic['exists'])
        self.assert_no_fic(body)
        status, body, _ = self.call('GET', '/api/external/fic')
        self.assertEqual((status, json.loads(body)), (401, {'locked': True}))
        self.assertTrue(json.loads(self.call('GET', '/api/finance/status')[1])['locked'])

    def test_finance_shaped_records_in_other_folders_are_withheld(self):
        record(self.export / 'paicc', 'odd.md', source='fic', source_id='odd', kind='finance_daily', title='Leaked via paicc folder')
        record(self.export / 'paicc', 'odd2.md', source='paicc', source_id='odd2', kind='finance_alert', title='Alert via paicc')
        body = self.call('GET', '/api/external')[1]
        self.assertNotIn('Leaked via paicc folder', body); self.assertNotIn('Alert via paicc', body)

    def test_unlock_sets_strict_httponly_cookie_and_reveals_fic(self):
        status, body, cookie = self.unlock()
        self.assertEqual(status, 200); self.assertNotIn(PASSWORD, body)
        self.assertIn('HttpOnly', cookie); self.assertIn('SameSite=Strict', cookie); self.assertIn('Path=/', cookie)
        jar = cookie.split(';')[0]
        data = json.loads(self.call('GET', '/api/external', cookie=jar)[1])
        self.assertFalse(data['finance_locked'])
        titles = {r['title'] for s in data['sources'] for r in s['records']}
        self.assertTrue(set(self.FIC_TITLES) | {'Holdings'} <= titles)
        self.assertIn('finance_holdings', {r['kind'] for s in data['sources'] for r in s['records']})
        status, body, _ = self.call('GET', '/api/external/fic', cookie=jar)
        self.assertEqual(status, 200); self.assertEqual(json.loads(body)['source'], 'fic')
        # A forged or old token stays locked.
        self.assertTrue(json.loads(self.call('GET', '/api/external', cookie='desk_finance=forged')[1])['finance_locked'])

    def test_wrong_password_and_bruteforce_lockout(self):
        for left in (4, 3, 2, 1):
            status, body, cookie = self.unlock('000000')
            self.assertEqual(status, 401); self.assertEqual(json.loads(body)['attempts_left'], left); self.assertIsNone(cookie)
        status, body, _ = self.unlock('000000'); self.assertEqual(status, 429)
        status, _, cookie = self.unlock(); self.assertEqual(status, 429, 'correct password refused during lockout'); self.assertIsNone(cookie)
        self.clock[0] += feeds.LOCKOUT_SECONDS + 1
        self.assertEqual(self.unlock()[0], 200)

    def test_idle_timeout_and_manual_lock(self):
        jar = self.unlock()[2].split(';')[0]
        self.clock[0] += feeds.IDLE_SECONDS - 5
        self.assertFalse(json.loads(self.call('GET', '/api/external', cookie=jar)[1])['finance_locked'], 'use renews the session')
        self.clock[0] += feeds.IDLE_SECONDS + 1
        self.assertEqual(self.call('GET', '/api/external/fic', cookie=jar)[0], 401)
        jar = self.unlock()[2].split(';')[0]
        status, _, cookie = self.call('POST', '/api/finance/lock', {}, cookie=jar)
        self.assertEqual(status, 200); self.assertIn('Max-Age=0', cookie)
        self.assertEqual(self.call('GET', '/api/external/fic', cookie=jar)[0], 401)

    def test_restart_relocks(self):
        jar = self.unlock()[2].split(';')[0]
        feeds._tokens.clear()  # what a server restart does: the in-memory token store is empty
        self.assertEqual(self.call('GET', '/api/external/fic', cookie=jar)[0], 401)

    def test_lock_file_is_reread_and_missing_or_unsafe_file_stays_locked(self):
        write_lock(self.lock, '135790')
        self.assertEqual(self.unlock()[0], 401); self.assertEqual(self.unlock('135790')[0], 200)
        feeds.relock(); self.lock.chmod(0o666)
        self.assertEqual(self.unlock('135790')[0], 503, 'group/world-writable lock file is ignored')
        self.lock.unlink()
        status, body, _ = self.unlock('135790')
        self.assertEqual(status, 503); self.assertIn('desk lock set', json.loads(body)['reset_hint'])
        self.assertFalse(json.loads(self.call('GET', '/api/finance/status')[1])['configured'])

    def test_unlock_requires_same_origin_action_header(self):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST', '/api/finance/unlock', body=json.dumps({'password': PASSWORD}), headers={'Content-Type': 'application/json'})
        r = c.getresponse(); r.read(); self.assertEqual(r.status, 403); self.assertIsNone(r.getheader('Set-Cookie'))
        self.assertEqual(self.call('GET', '/api/external', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_password_is_not_kept_or_logged(self):
        self.unlock(); self.unlock('999999')
        state = repr(feeds._tokens) + repr(feeds._failures) + repr(vars(feeds))
        self.assertNotIn(PASSWORD, state); self.assertNotIn('999999', state)
        js = (APP / 'desk.js').read_text()
        self.assertNotIn('localStorage.setItem(\'desk.finance', js); self.assertNotIn('sessionStorage', js[js.index('let financeStatus'):js.index('async function loadExternal(')])


if __name__ == '__main__':
    unittest.main()


class TaskMarkTests(unittest.TestCase):
    """Ticking a task writes only its id to Desk's own marks file, never into the exports."""
    def setUp(self):
        FinanceLockTests.setUp(self)
        self.marks = self.root / 'state/task-marks.json'
        self.old_marks = os.environ.get('DESK_TASK_MARKS'); os.environ['DESK_TASK_MARKS'] = str(self.marks)

    def tearDown(self):
        if self.old_marks is None: os.environ.pop('DESK_TASK_MARKS', None)
        else: os.environ['DESK_TASK_MARKS'] = self.old_marks
        FinanceLockTests.tearDown(self)

    call = FinanceLockTests.call

    def test_tick_and_untick_store_only_ids_outside_exports(self):
        before = tree_state(self.export)
        status, body, _ = self.call('POST', '/api/task-marks', {'ids': ['task-1', 'task-2'], 'done': True})
        self.assertEqual(status, 200); self.assertEqual(sorted(json.loads(body)['done']), ['task-1', 'task-2'])
        self.assertEqual(tree_state(self.export), before, 'exports untouched')
        self.assertEqual(stat.S_IMODE(self.marks.stat().st_mode), 0o600)
        saved = json.loads(self.marks.read_text())
        self.assertEqual(set(saved), {'schema_version', 'source', 'kind', 'updated_at', 'done'})
        self.assertEqual(sorted(saved['done']), ['task-1', 'task-2'])
        status, body, _ = self.call('POST', '/api/task-marks', {'ids': ['task-1'], 'done': False})
        self.assertEqual(list(json.loads(body)['done']), ['task-2'])
        status, body, _ = self.call('GET', '/api/task-marks')
        self.assertEqual(list(json.loads(body)['done']), ['task-2'])

    def test_rejects_bad_requests(self):
        for payload in ({'ids': ['../x'], 'done': True}, {'ids': [], 'done': True}, {'ids': ['a'], 'done': 'yes'}, {'ids': 'a', 'done': True}):
            self.assertEqual(self.call('POST', '/api/task-marks', payload)[0], 400, payload)
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        c.request('POST', '/api/task-marks', body='{"ids":["a"],"done":true}', headers={'Host': f'127.0.0.1:{self.server.server_port}', 'Content-Type': 'application/json'})
        self.assertEqual(c.getresponse().status, 403, 'needs the Desk origin and action header')
        self.assertFalse(self.marks.exists())

    def test_marks_module_never_touches_exports(self):
        text = (APP / 'task_marks.py').read_text()
        for needle in ('external_feeds', 'desk-export', 'PAICC', 'EXPORT_ROOT', 'urllib', 'socket', 'subprocess'):
            self.assertNotIn(needle, text)
