"""HTTP contract tests against the compiled Rust server and Python-era data."""
import copy
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('TIMETABLE_TEST_BINARY', ROOT / 'target/release/timetable-server')).resolve()


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.temp.name)
        cls.password = 'legacy-password-for-tests'
        cls.key = 'ab' * 32
        salt = 'cd' * 16
        cls.auth = json.dumps({'salt': salt, 'key': cls.key, 'password_hash': hashlib.pbkdf2_hmac('sha256', cls.password.encode(), salt.encode(), 600000).hex()}).encode()
        (cls.data / 'auth.json').write_bytes(cls.auth)
        cls.fixture = {'settings': {'title': '旧版学期', 'startDate': '2026-09-21', 'totalWeeks': 20, 'timezone': 'Asia/Shanghai', 'dayStart': '08:00', 'dayEnd': '21:00'}, 'courses': [{'id': 'legacy-course', 'name': '原有课程', 'location': 'A201', 'teacher': '', 'notes': '旧版数据保持原样', 'color': 'blue', 'sessions': []}]}
        with sqlite3.connect(cls.data / 'schedule.sqlite3') as con:
            con.executescript('CREATE TABLE schedule(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, body TEXT NOT NULL); CREATE TABLE history(revision INTEGER PRIMARY KEY, saved_at TEXT DEFAULT CURRENT_TIMESTAMP, body TEXT NOT NULL);')
            con.execute('INSERT INTO schedule VALUES(1,3,?)', (json.dumps(cls.fixture, ensure_ascii=False),))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.start_server()

    @classmethod
    def start_server(cls):
        cls.process = subprocess.Popen([str(BINARY), '--port', str(cls.port)], env={**os.environ, 'TIMETABLE_DATA': str(cls.data), 'TIMETABLE_PUBLIC': str(ROOT / 'dist'), 'TIMETABLE_ORIGIN': 'https://timetable.example', 'TIMETABLE_REVISION': 'test-rust'}, stdout=subprocess.DEVNULL)
        for _ in range(100):
            try:
                con = http.client.HTTPConnection('127.0.0.1', cls.port, timeout=1)
                con.request('GET', '/healthz')
                res = con.getresponse()
                health = json.loads(res.read())
                con.close()
                if health.get('backend') == 'rust':
                    return
            except OSError:
                pass
            if cls.process.poll() is not None:
                raise RuntimeError('Rust server exited during startup')
            time.sleep(0.05)
        raise RuntimeError('Rust server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.temp.cleanup()

    def call(self, method='GET', path='/api/schedule', data=None, cookie=None, origin=None, extra=None, raw=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        headers = {'Content-Type': 'application/json', **(extra or {})}
        if cookie:
            headers['Cookie'] = cookie
        if origin:
            headers['Origin'] = origin
        conn.request(method, path, body=raw if raw is not None else json.dumps(data) if data is not None else None, headers=headers)
        res = conn.getresponse()
        body = res.read()
        result = (res.status, {k.lower(): v for k, v in res.getheaders()}, json.loads(body) if 'json' in res.getheader('Content-Type', '') else body)
        conn.close()
        return result

    def legacy_cookie(self, expiry=None):
        body = f'{expiry or int(time.time()) + 3600}.legacy-nonce'
        signature = hmac.new(self.key.encode(), body.encode(), hashlib.sha256).hexdigest()
        return f'__Host-timetable={body}.{signature}'

    def login(self):
        status, headers, _ = self.call('POST', '/api/login', {'password': self.password})
        self.assertEqual(status, 200)
        for flag in ['HttpOnly', 'SameSite=Strict', 'Secure', 'Path=/']:
            self.assertIn(flag, headers['set-cookie'])
        return headers['set-cookie'].split(';')[0]

    def test_00_legacy_store_password_and_cookie(self):
        result = self.call()[2]
        self.assertEqual(result['data'], self.fixture)
        self.assertEqual(result['revision'], 3)
        self.assertEqual((self.data / 'auth.json').read_bytes(), self.auth)
        self.assertFalse((self.data / 'admin-password.txt').exists())
        self.assertTrue(self.call(cookie=self.legacy_cookie())[2]['authenticated'])
        self.assertFalse(self.call(cookie=self.legacy_cookie(1))[2]['authenticated'])
        self.assertFalse(self.call(cookie=self.legacy_cookie() + 'bad')[2]['authenticated'])
        self.assertTrue(self.call(cookie=self.login())[2]['authenticated'])

    def test_public_read_private_write(self):
        status, _, result = self.call()
        self.assertEqual(status, 200)
        self.assertFalse(result['authenticated'])
        self.assertEqual(self.call('PUT', '/api/schedule', result)[0], 401)
        self.assertEqual(self.call('POST', '/api/login', {'password': 'wrong'})[0], 401)
        cookie = self.login()
        self.assertTrue(self.call(cookie=cookie)[2]['authenticated'])
        response = self.call('POST', '/api/logout', {}, cookie)
        self.assertIn('Max-Age=0', response[1]['set-cookie'])

    def test_save_restart_conflict_validation_and_history(self):
        cookie = self.login()
        original = self.call()[2]
        data = copy.deepcopy(original['data'])
        data['courses'] = [{'id': 'test-course', 'name': '测试课程', 'teacher': '', 'location': 'A201', 'notes': '<script>not executed</script>', 'color': 'green', 'sessions': [{'day': 1, 'start': '08:00', 'end': '09:35', 'weeks': '1-16单', 'location': '线上教室'}]}, {'id': 'pending', 'name': '时间待定', 'teacher': '', 'location': '', 'notes': '', 'color': 'blue', 'sessions': []}]
        payload = {'revision': original['revision'], 'data': data}
        self.assertEqual(self.call('PUT', '/api/schedule', payload, cookie)[0], 200)
        self.assertEqual(self.call()[2]['data'], data)
        self.process.terminate()
        self.process.wait(timeout=10)
        self.start_server()
        self.assertEqual(self.call()[2]['data'], data)
        self.assertTrue(self.call(cookie=cookie)[2]['authenticated'])
        self.assertEqual(self.call('PUT', '/api/schedule', payload, cookie)[0], 409)
        payload['revision'] += 1
        payload['data']['courses'][0]['sessions'][0]['weeks'] = '0-16'
        self.assertEqual(self.call('PUT', '/api/schedule', payload, cookie)[0], 400)
        self.assertEqual(self.call()[2]['revision'], original['revision'] + 1)
        with sqlite3.connect(self.data / 'schedule.sqlite3') as con:
            self.assertEqual(json.loads(con.execute('SELECT body FROM history WHERE revision=?', (original['revision'],)).fetchone()[0]), original['data'])
        self.assertEqual((self.data / 'auth.json').read_bytes(), self.auth)

    def test_origin_and_private_files(self):
        self.assertEqual(self.call('POST', '/api/login', {'password': self.password}, origin='https://evil.example')[0], 403)
        self.assertEqual(self.call('POST', '/api/login', {'password': self.password}, extra={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        for path in ['/data/auth.json', '/data/admin-password.txt', '/server.py', '/../server.py', '/timetable-server']:
            self.assertEqual(self.call(path=path)[0], 404)
        response = self.call(path='/')
        self.assertEqual(response[0], 200)
        self.assertIn("script-src 'self'", response[1]['content-security-policy'])
        self.assertIn(b'/assets/', response[2])

    def test_validation_boundaries(self):
        original = self.call()[2]
        for key, value in [('totalWeeks', True), ('startDate', '2026-09-08'), ('dayStart', '25:00'), ('timezone', 'invalid')]:
            bad = copy.deepcopy(original)
            bad['data']['settings'][key] = value
            self.assertIn(self.call('PUT', '/api/schedule', bad, self.legacy_cookie())[0], [400, 422])
        self.assertEqual(self.call('POST', '/api/login', raw='x' * 512001)[0], 413)
        self.assertEqual(self.call('POST', '/api/login', raw='{}', extra={'Content-Type': 'text/plain'})[0], 415)

    def test_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.call('POST', '/api/login', {'password': 'wrong'}, extra={'X-Real-IP': '192.0.2.1'})[0], 401)
        self.assertEqual(self.call('POST', '/api/login', {'password': 'wrong'}, extra={'X-Real-IP': '192.0.2.1'})[0], 429)


if __name__ == '__main__':
    unittest.main()
