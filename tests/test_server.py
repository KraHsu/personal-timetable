import copy
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        server.DATA = Path(cls.temp.name)
        server.initialize()
        cls.httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.password = (server.DATA / 'admin-password.txt').read_text().strip()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.temp.cleanup()

    def call(self, method='GET', path='/api/schedule', data=None, cookie=None, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port)
        headers = {'Content-Type': 'application/json'}
        if cookie:
            headers['Cookie'] = cookie
        if origin:
            headers['Origin'] = origin
        conn.request(method, path, body=json.dumps(data) if data is not None else None, headers=headers)
        res = conn.getresponse()
        raw = res.read()
        result = (res.status, dict(res.getheaders()), json.loads(raw) if 'json' in res.getheader('Content-Type', '') else raw)
        conn.close()
        return result

    def login(self):
        status, headers, _ = self.call('POST', '/api/login', {'password': self.password})
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        return headers['Set-Cookie'].split(';')[0]

    def test_public_read_private_write(self):
        status, _, result = self.call()
        self.assertEqual(status, 200)
        self.assertFalse(result['authenticated'])
        self.assertEqual(self.call('PUT', '/api/schedule', result)[0], 401)
        self.assertEqual(self.call('POST', '/api/login', {'password': 'wrong'})[0], 401)
        self.assertTrue(self.call(cookie=self.login())[2]['authenticated'])

    def test_save_reopen_conflict_validation_and_history(self):
        cookie = self.login()
        original = self.call()[2]
        data = copy.deepcopy(original['data'])
        data['courses'] = [{'id': 'test-course', 'name': '测试课程', 'teacher': '', 'location': 'A201', 'notes': '<script>not executed</script>', 'color': 'green', 'sessions': [{'day': 1, 'start': '08:00', 'end': '09:40', 'weeks': '1-16单'}]}]
        payload = {'revision': original['revision'], 'data': data}
        result = self.call('PUT', '/api/schedule', payload, cookie)
        self.assertEqual(result[0], 200)
        self.assertEqual(self.call()[2]['data'], data)
        server.initialize()  # Reopen the on-disk store, preserving credentials and course data.
        self.assertEqual(self.call()[2]['data'], data)
        self.assertEqual(self.call('PUT', '/api/schedule', payload, cookie)[0], 409)
        payload['revision'] += 1
        payload['data']['courses'][0]['sessions'][0]['weeks'] = '0-16'
        self.assertEqual(self.call('PUT', '/api/schedule', payload, cookie)[0], 400)
        self.assertEqual(self.call()[2]['revision'], original['revision'] + 1)
        with server.db() as con:
            self.assertEqual(json.loads(con.execute('SELECT body FROM history WHERE revision=?', (original['revision'],)).fetchone()[0]), original['data'])

    def test_origin_and_private_files(self):
        self.assertEqual(self.call('POST', '/api/login', {'password': self.password}, origin='https://evil.example')[0], 403)
        for path in ['/data/auth.json', '/data/admin-password.txt', '/server.py', '/../server.py']:
            self.assertEqual(self.call(path=path)[0], 404)
        self.assertIn("script-src 'self'", self.call(path='/')[1]['Content-Security-Policy'])

    def test_validation_boundaries(self):
        data = self.call()[2]['data']
        for key, value in [('totalWeeks', True), ('startDate', '2026-09-08'), ('dayStart', '25:00'), ('timezone', 'invalid')]:
            bad = copy.deepcopy(data)
            bad['settings'][key] = value
            with self.assertRaises(ValueError):
                server.validate(bad)

    def test_pending_course_and_session_location_round_trip(self):
        data = self.call()[2]['data']
        data['courses'] = [{'id': 'pending', 'name': '时间待定课程', 'location': '', 'teacher': '测试教师', 'notes': '等待通知', 'color': 'blue', 'sessions': []}]
        self.assertEqual(server.validate(data), data)
        session = {'day': 1, 'start': '08:00', 'end': '09:35', 'weeks': '1-2', 'location': '线上教室'}
        data['courses'][0]['sessions'] = [session]
        self.assertEqual(server.validate(data), data)
        session['location'] = {'invalid': True}
        with self.assertRaises(ValueError):
            server.validate(data)


if __name__ == '__main__':
    unittest.main()
