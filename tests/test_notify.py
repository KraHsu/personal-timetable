import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location('notify', Path(__file__).resolve().parents[1] / 'deploy/notify.py')
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)
UTC = timezone.utc


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.schedule = {'settings': {'startDate': '2026-10-19', 'totalWeeks': 20, 'timezone': 'Asia/Shanghai'}, 'courses': [{'id': 'math', 'name': '数学', 'location': '默认教室', 'teacher': '老师', 'notes': '', 'sessions': [{'day': 1, 'start': '08:00', 'end': '09:30', 'weeks': '1-20单', 'location': 'A201'}]}]}
        self.config = {'courseEnabled': True, 'items': []}
        self.now = datetime(2026, 10, 18, 23, 30, tzinfo=UTC)

    def test_course_half_hour_weeks_override_and_expiry(self):
        self.assertEqual(list(notify.jobs(self.schedule, self.config, self.now - timedelta(seconds=1))), [])
        jobs = list(notify.jobs(self.schedule, self.config, self.now))
        self.assertEqual(len(jobs), 1)
        self.assertIn('A201', jobs[0]['body'])
        self.assertEqual(list(notify.jobs(self.schedule, self.config, self.now + timedelta(minutes=30))), [])
        self.assertEqual(list(notify.jobs(self.schedule, self.config, self.now + timedelta(days=7))), [])
        self.assertEqual(len(list(notify.jobs(self.schedule, self.config, self.now + timedelta(days=14)))), 1)
        self.config['courseEnabled'] = False
        self.assertEqual(list(notify.jobs(self.schedule, self.config, self.now)), [])

    def test_midnight_and_timezone_independent(self):
        self.schedule['courses'][0]['sessions'][0]['start'] = '00:10'
        now = datetime(2026, 10, 18, 15, 40, tzinfo=UTC)
        self.assertEqual(len(list(notify.jobs(self.schedule, self.config, now))), 1)
        self.schedule['settings']['timezone'] = 'America/Los_Angeles'
        now = datetime(2026, 10, 19, 6, 40, tzinfo=UTC)
        self.assertEqual(len(list(notify.jobs(self.schedule, self.config, now))), 1)
        with self.assertRaises(ValueError):
            notify.local_time('2026-03-08T02:30', ZoneInfo('America/Los_Angeles'))

    def test_items_arbitrary_time_disabled_completed_and_catchup(self):
        item = {'id': 'hw', 'kind': 'homework', 'title': '作业', 'remindAt': '2026-10-19T07:30', 'dueAt': '2026-10-22T23:59', 'notes': '第二章', 'enabled': True, 'completed': False}
        self.config = {'courseEnabled': False, 'items': [item]}
        jobs = list(notify.jobs(self.schedule, self.config, self.now + timedelta(hours=23)))
        self.assertEqual(len(jobs), 1)
        self.assertIn('2026-10-22 23:59', jobs[0]['body'])
        self.assertEqual(list(notify.jobs(self.schedule, self.config, self.now + timedelta(hours=24))), [])
        for field in ('enabled', 'completed'):
            config = copy.deepcopy(self.config)
            config['items'][0][field] = field == 'completed'
            self.assertEqual(list(notify.jobs(self.schedule, config, self.now)), [])

    def test_first_course_previous_friday_earliest_session_and_custom_time(self):
        # The earliest listed session starts in week 2; another starts in week 1.
        course = self.schedule['courses'][0]
        course['sessions'][0]['weeks'] = '2-20双'
        course['sessions'].append({'day': 4, 'start': '10:00', 'end': '11:00', 'weeks': '1-19单'})
        self.config.update(courseEnabled=False, firstCourseEnabled=True, firstCourseTime='17:30')
        friday = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)
        self.assertEqual(list(notify.jobs(self.schedule, self.config, friday - timedelta(seconds=1))), [])
        jobs = list(notify.jobs(self.schedule, self.config, friday))
        self.assertEqual(len(jobs), 1)
        self.assertIn('下周新课', jobs[0]['title'])
        self.assertIn('2026-10-22 10:00', jobs[0]['body'])
        self.assertEqual(list(notify.jobs(self.schedule, self.config, friday + timedelta(days=7))), [])
        self.config['firstCourseEnabled'] = False
        self.assertEqual(list(notify.jobs(self.schedule, self.config, friday)), [])
        self.config['firstCourseEnabled'] = True
        course['sessions'] = []
        self.assertEqual(list(notify.jobs(self.schedule, self.config, friday)), [])

    def database(self):
        db = sqlite3.connect(':memory:')
        db.executescript('CREATE TABLE schedule(id INTEGER,body TEXT); CREATE TABLE reminders(id INTEGER,body TEXT); CREATE TABLE notification_deliveries(key TEXT PRIMARY KEY,status TEXT,attempts INTEGER,next_attempt INTEGER,sent_at TEXT,title TEXT);')
        db.execute('INSERT INTO schedule VALUES(1,?)', (json.dumps(self.schedule),))
        db.execute('INSERT INTO reminders VALUES(1,?)', (json.dumps(self.config),))
        return db

    def test_persisted_deduplication_and_retry(self):
        db = self.database()
        calls = []
        def failing(*args):
            calls.append(args)
            raise OSError('network unavailable')
        self.assertEqual(notify.run(db, 'secret', self.now, sender=failing), 0)
        self.assertEqual(notify.run(db, 'secret', self.now + timedelta(seconds=30), sender=failing), 0)
        self.assertEqual(len(calls), 1)
        def success(*args): calls.append(args)
        self.assertEqual(notify.run(db, 'secret', self.now + timedelta(seconds=60), sender=success), 1)
        self.assertEqual(notify.run(db, 'secret', self.now + timedelta(seconds=120), sender=success), 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(db.execute('SELECT status,attempts FROM notification_deliveries').fetchone(), ('sent', 2))
        # Editing location must not notify again for the same class occurrence.
        self.schedule['courses'][0]['location'] = '新地点'
        db.execute('UPDATE schedule SET body=?', (json.dumps(self.schedule),))
        self.assertEqual(notify.run(db, 'secret', self.now + timedelta(seconds=180), sender=success), 0)
        db.close()

    def test_server3_route_and_provider_rejection(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"code":0,"errno":0}'
        with patch.object(notify.urllib.request, 'urlopen', return_value=Response()) as request:
            notify.send('sctp123tabcdef', '测试', '内容')
            self.assertEqual(request.call_args.args[0].full_url, 'https://123.push.ft07.com/send/sctp123tabcdef.send')
            self.assertIn('title=', request.call_args.args[0].data.decode())
        with self.assertRaises(ValueError): notify.send('old-key', '测试', '')
        with patch.object(notify.urllib.request, 'urlopen', return_value=Response()), patch.object(notify.json, 'load', return_value={'code': 1}):
            with self.assertRaises(RuntimeError): notify.send('sctp123tabcdef', '测试', '')


if __name__ == '__main__':
    unittest.main()
