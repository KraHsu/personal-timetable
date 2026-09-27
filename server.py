#!/usr/bin/env python3
"""Personal timetable. Python 3.12 standard library, SQLite, no external services."""
import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from datetime import date, timedelta
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('TIMETABLE_DATA', str(ROOT / 'data')))
ORIGIN = os.environ.get('TIMETABLE_ORIGIN', 'http://127.0.0.1:8765').rstrip('/')
SECURE = ORIGIN.startswith('https://')
COOKIE = '__Host-timetable' if SECURE else 'timetable_session'
MAX_BODY = 512000
AUTH = {}
ATTEMPTS = {}
RATE_LOCK = threading.Lock()


def weeks(value, total):
    if not isinstance(value, str) or len(value) > 250:
        raise ValueError('周次格式无效')
    result = set()
    for token in re.sub(r'\s|周', '', value).replace('，', ',').replace('、', ',').split(','):
        match = re.fullmatch(r'(\d+)(?:-(\d+))?([单双])?', token)
        if not match:
            raise ValueError('周次格式应为 1-16、1-16单 或 1-8,10-16')
        start, end = int(match[1]), int(match[2] or match[1])
        if not 1 <= start <= end <= total:
            raise ValueError(f'上课周次须在 1–{total} 之间')
        result.update(w for w in range(start, end + 1) if not match[3] or w % 2 == (1 if match[3] == '单' else 0))
    if not result:
        raise ValueError('所选周次没有上课周')
    return result


def text_field(obj, key, maximum, required=False):
    value = obj.get(key, '')
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f'{key} 字段为空或过长')
    return value.strip()


def validate_time(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('时间格式应为 HH:MM')
    return value


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get('settings'), dict) or not isinstance(data.get('courses'), list):
        raise ValueError('课表数据格式无效')
    s = data['settings']
    total = s.get('totalWeeks')
    if type(total) is not int or not 1 <= total <= 60:
        raise ValueError('学期周数须在 1–60 之间')
    start = text_field(s, 'startDate', 10, True)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', start) or not 2000 <= date.fromisoformat(start).year <= 2100 or date.fromisoformat(start).weekday() != 0:
        raise ValueError('学期起始日期须为 2000–2100 年之间的周一')
    zone = s.get('timezone')
    if zone not in ('Asia/Shanghai', 'America/Los_Angeles', 'Europe/London', 'Asia/Tokyo', 'UTC'):
        raise ValueError('请选择支持的课表时区')
    begin, end = validate_time(s.get('dayStart')), validate_time(s.get('dayEnd'))
    if begin >= end:
        raise ValueError('课表结束时间须晚于起始时间')
    settings = dict(title=text_field(s, 'title', 80, True), startDate=start, totalWeeks=total, timezone=zone, dayStart=begin, dayEnd=end)
    if len(data['courses']) > 200:
        raise ValueError('最多支持 200 门课程')
    courses, ids = [], set()
    for c in data['courses']:
        if not isinstance(c, dict):
            raise ValueError('课程数据格式无效')
        cid = text_field(c, 'id', 80, True)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', cid) or cid in ids:
            raise ValueError('课程 ID 无效或重复')
        ids.add(cid)
        color = c.get('color')
        if color not in ('green', 'blue', 'mauve', 'peach', 'rose'):
            raise ValueError('课程标记颜色无效')
        if not isinstance(c.get('sessions'), list) or not 1 <= len(c['sessions']) <= 30:
            raise ValueError('每门课程须有 1–30 个上课时段')
        sessions = []
        for item in c['sessions']:
            if not isinstance(item, dict) or type(item.get('day')) is not int or not 1 <= item['day'] <= 7:
                raise ValueError('上课星期无效')
            a, b = validate_time(item.get('start')), validate_time(item.get('end'))
            if a >= b:
                raise ValueError('结束时间须晚于开始时间')
            weeks(item.get('weeks'), total)
            sessions.append(dict(day=item['day'], start=a, end=b, weeks=item['weeks'].strip()))
        courses.append(dict(id=cid, name=text_field(c, 'name', 80, True), location=text_field(c, 'location', 120), teacher=text_field(c, 'teacher', 80), notes=text_field(c, 'notes', 2000), color=color, sessions=sessions))
    return dict(settings=settings, courses=courses)


def db():
    con = sqlite3.connect(DATA / 'schedule.sqlite3', timeout=10)
    return con


def initialize():
    global AUTH
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    authfile = DATA / 'auth.json'
    if not authfile.exists():
        password = secrets.token_urlsafe(18)
        salt = secrets.token_hex(16)
        auth = dict(salt=salt, password_hash=hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex(), key=secrets.token_hex(32))
        for path, content in [(authfile, json.dumps(auth)), (DATA / 'admin-password.txt', password + '\n')]:
            with path.open('x') as f:
                os.chmod(path, 0o600)
                f.write(content)
    AUTH = json.loads(authfile.read_text())
    with db() as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('CREATE TABLE IF NOT EXISTS schedule (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, body TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS history (revision INTEGER PRIMARY KEY, saved_at TEXT DEFAULT CURRENT_TIMESTAMP, body TEXT NOT NULL)')
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        initial = dict(settings=dict(title='我的学期', startDate=monday.isoformat(), totalWeeks=20, timezone='Asia/Shanghai', dayStart='08:00', dayEnd='20:00'), courses=[])
        con.execute('INSERT OR IGNORE INTO schedule VALUES (1, 1, ?)', (json.dumps(initial, ensure_ascii=False),))


def sign(value):
    return hmac.new(AUTH['key'].encode(), value.encode(), hashlib.sha256).hexdigest()


class Handler(BaseHTTPRequestHandler):
    server_version = 'Timetable'

    def send(self, status, value, headers=None, content_type='application/json; charset=utf-8'):
        raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Cache-Control', 'no-store' if self.path.startswith('/api/') else 'no-cache')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def authenticated(self):
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            value = cookies[COOKIE].value
            expiry, nonce, mac = value.split('.')
            return int(expiry) > time.time() and hmac.compare_digest(sign(expiry + '.' + nonce), mac)
        except (KeyError, ValueError, CookieError):
            return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/schedule':
            with db() as con:
                revision, body = con.execute('SELECT revision, body FROM schedule WHERE id=1').fetchone()
            return self.send(200, dict(data=json.loads(body), revision=revision, authenticated=self.authenticated()))
        files = {'/': 'index.html', '/index.html': 'index.html', '/style.css': 'style.css', '/app.mjs': 'app.mjs', '/core.mjs': 'core.mjs', '/icon.svg': 'icon.svg', '/serif.woff2': 'serif.woff2', '/font-license.txt': 'font-license.txt'}
        if path == '/healthz':
            release = ROOT / 'REVISION'
            return self.send(200, {'ok': True, 'revision': release.read_text().strip() if release.exists() else 'local'})
        if path not in files:
            return self.send(404, {'error': '页面不存在'})
        file = ROOT / 'public' / files[path]
        if not file.is_file():
            return self.send(404, {'error': '文件不存在'})
        content_type = 'text/javascript' if file.suffix == '.mjs' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        return self.send(200, file.read_bytes(), content_type=content_type)

    def body(self):
        if self.headers.get('Origin') not in (None, ORIGIN):
            self.send(403, {'error': '请求来源无效'})
            return None
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.send(403, {'error': '不接受跨站写入'})
            return None
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.send(415, {'error': '请求须为 JSON'})
            return None
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= MAX_BODY:
                self.send(413, {'error': '请求大小无效或超过 500 KB'})
                return None
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeDecodeError):
            self.send(400, {'error': 'JSON 格式无效'})
            return None

    def do_POST(self):
        value = self.body()
        if value is None:
            return
        path = urlsplit(self.path).path
        if path == '/api/login':
            ip = self.headers.get('X-Real-IP', self.client_address[0])
            now = time.time()
            with RATE_LOCK:
                for old in list(ATTEMPTS):
                    if ATTEMPTS[old][-1] < now - 900:
                        del ATTEMPTS[old]
                attempts = ATTEMPTS.setdefault(ip, [])
                attempts[:] = [t for t in attempts if t > now - 900]
                if len(attempts) >= 10:
                    return self.send(429, {'error': '尝试次数过多，请 15 分钟后重试'})
                attempts.append(now)
            password = value.get('password')
            if not isinstance(password, str) or len(password) > 256:
                return self.send(400, {'error': '密码格式无效'})
            hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), AUTH['salt'].encode(), 600000).hex()
            if not hmac.compare_digest(hashed, AUTH['password_hash']):
                return self.send(401, {'error': '密码不正确'})
            with RATE_LOCK:
                ATTEMPTS.pop(ip, None)
            token = str(int(now + 30 * 86400)) + '.' + secrets.token_hex(12)
            return self.send(200, {'ok': True}, {'Set-Cookie': f'{COOKIE}={token}.{sign(token)}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000' + ('; Secure' if SECURE else '')})
        if path == '/api/logout':
            return self.send(200, {'ok': True}, {'Set-Cookie': f'{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0' + ('; Secure' if SECURE else '')})
        self.send(404, {'error': '接口不存在'})

    def do_PUT(self):
        if urlsplit(self.path).path != '/api/schedule':
            return self.send(404, {'error': '接口不存在'})
        if not self.authenticated():
            return self.send(401, {'error': '编辑登录已过期，请关闭弹窗后重新进入编辑'})
        value = self.body()
        if value is None:
            return
        try:
            clean = validate(value.get('data'))
        except (ValueError, TypeError, OverflowError) as error:
            return self.send(400, {'error': str(error)})
        with db() as con:
            con.execute('BEGIN IMMEDIATE')
            revision, old = con.execute('SELECT revision, body FROM schedule WHERE id=1').fetchone()
            if value.get('revision') != revision:
                return self.send(409, {'error': '另一台设备已更新课表。请先复制未保存的内容，再刷新页面后编辑，避免覆盖更新。'})
            con.execute('INSERT INTO history (revision, body) VALUES (?, ?)', (revision, old))
            con.execute('UPDATE schedule SET revision=?, body=? WHERE id=1', (revision + 1, json.dumps(clean, ensure_ascii=False)))
            con.execute('DELETE FROM history WHERE revision < ?', (revision - 49,))
        self.send(200, dict(data=clean, revision=revision + 1))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--init-only', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    initialize()
    if not args.init_only:
        httpd = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
        httpd.daemon_threads = True
        print(f'Timetable listening on 127.0.0.1:{args.port}', flush=True)
        httpd.serve_forever()
