"""Run on rain after deployment; never prints credentials or user course data."""
import json
from pathlib import Path
import urllib.request
import urllib.error
import http.cookiejar

base = 'https://timetable.krahsu.top'
cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))


def request(path, data=None, method=None, auth=False):
    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, method=method, headers={'Content-Type': 'application/json', 'Origin': base})
    with (client.open(req, timeout=20) if auth else urllib.request.urlopen(req, timeout=20)) as response:
        return json.load(response)


initial = request('/api/schedule')
assert not initial['authenticated']
password = Path('/home/charles/apps/timetable/data/admin-password.txt').read_text().strip()
assert request('/api/login', {'password': password}, auth=True)['ok']
assert request('/api/schedule', auth=True)['authenticated']
assert cookies and all(c.secure and c.has_nonstandard_attr('HttpOnly') for c in cookies)
# Save the exact existing data to verify the production service's write permissions.
saved = request('/api/schedule', {'revision': initial['revision'], 'data': initial['data']}, 'PUT', auth=True)
assert saved['data'] == initial['data']
assert saved['revision'] == initial['revision'] + 1
assert request('/api/schedule')['data'] == initial['data']
try:
    request('/api/schedule', {'revision': saved['revision'], 'data': initial['data']}, 'PUT')
except urllib.error.HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError('Unauthenticated write accepted')
assert request('/api/logout', {}, auth=True)['ok']
assert not request('/api/schedule', auth=True)['authenticated']
print('PASS: public HTTPS read, password login, Secure/HttpOnly cookie, persistent save, second-client read, write protection, logout')
