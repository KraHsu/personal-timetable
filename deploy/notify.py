#!/usr/bin/env python3
"""Timetable Server3 worker. Run every 30s; all dates use the schedule timezone.

SQLite persists successes and retry backoff across restarts. No third-party modules.
"""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

UTC = timezone.utc


def local_time(value, zone):
    """Reject non-existent DST times; for a repeated time use its first occurrence."""
    local = datetime.strptime(value, '%Y-%m-%dT%H:%M').replace(tzinfo=zone)
    instant = local.astimezone(UTC)
    if instant.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
        raise ValueError('Time falls in a daylight-saving clock gap')
    return instant


def active_weeks(value):
    result = set()
    for part in re.sub(r'[\s周]', '', value).replace('，', ',').replace('、', ',').split(','):
        match = re.fullmatch(r'(\d+)(?:-(\d+))?([单双])?', part)
        if not match:
            raise ValueError('Invalid course weeks')
        start, end, parity = match.groups()
        result.update(w for w in range(int(start), int(end or start) + 1)
                      if not parity or w % 2 == (1 if parity == '单' else 0))
    return result


def job(key, title, body, at, expires):
    return {'key': hashlib.sha256(key.encode()).hexdigest(), 'title': title,
            'body': body, 'at': at, 'expires': expires}


def jobs(schedule, config, now):
    settings = schedule['settings']
    zone = ZoneInfo(settings['timezone'])
    if config.get('courseEnabled', True):
        first = datetime.strptime(settings['startDate'], '%Y-%m-%d').date()
        # Include tomorrow: a 00:10 class needs its reminder on the preceding date.
        today = now.astimezone(zone).date()
        for date in (today, today + timedelta(days=1)):
            week = (date - first).days // 7 + 1
            if not 1 <= week <= settings['totalWeeks']:
                continue
            for course in schedule['courses']:
                for session in course['sessions']:
                    if session['day'] != date.isoweekday() or week not in active_weeks(session['weeks']):
                        continue
                    try:
                        start = local_time(f'{date}T{session["start"]}', zone)
                    except ValueError:
                        print('Skipped course in daylight-saving clock gap', file=sys.stderr)
                        continue
                    at = start - timedelta(minutes=30)
                    if not at <= now < start:
                        continue
                    location = session.get('location') or course.get('location') or '地点待填写'
                    title = f'上课提醒 · {course["name"]}'
                    body = f'**{course["name"]}**\n\n{date} {session["start"]}–{session["end"]}（{settings["timezone"]}）\n\n地点：{location}\n\n第 {week} 周'
                    if course.get('teacher'):
                        body += f'\n\n教师：{course["teacher"]}'
                    if course.get('notes'):
                        body += f'\n\n{course["notes"]}'
                    body += '\n\n[打开课表](https://timetable.krahsu.top)'
                    yield job(f'course:{course["id"]}:{date}:{session["start"]}', title, body, at, start)
    if config.get('firstCourseEnabled', True):
        first = datetime.strptime(settings['startDate'], '%Y-%m-%d').date()
        for course in schedule['courses']:
            starts = []
            for session in course['sessions']:
                weeks = sorted(w for w in active_weeks(session['weeks']) if 1 <= w <= settings['totalWeeks'])
                if not weeks:
                    continue
                date = first + timedelta(days=(weeks[0] - 1) * 7 + session['day'] - 1)
                starts.append((f'{date}T{session["start"]}', session, date))
            if not starts:
                continue
            value, session, date = min(starts, key=lambda x: x[0])
            friday = date - timedelta(days=date.weekday() + 3)
            try:
                at = local_time(f'{friday}T{config.get("firstCourseTime", "18:00")}', zone)
                begins = local_time(value, zone)
            except ValueError:
                print('Skipped invalid first-course reminder time', file=sys.stderr)
                continue
            expires = min(at + timedelta(hours=24), begins)
            if not at <= now < expires:
                continue
            location = session.get('location') or course.get('location') or '地点待填写'
            title = f'下周新课 · {course["name"]}'
            body = f'**{course["name"]}** 将于下周首次开课。\n\n首次上课：{date} {session["start"]}–{session["end"]}（{settings["timezone"]}）\n\n地点：{location}'
            if course.get('teacher'):
                body += f'\n\n教师：{course["teacher"]}'
            if course.get('notes'):
                body += f'\n\n{course["notes"]}'
            body += '\n\n[打开课表](https://timetable.krahsu.top)'
            yield job(f'first-course:{course["id"]}:{value}', title, body, at, expires)
    kinds = {'homework': '作业', 'exam': '考试', 'other': '事项'}
    for item in config.get('items', []):
        if item.get('completed') or not item.get('enabled') or not item.get('remindAt'):
            continue
        try:
            at = local_time(item['remindAt'], zone)
        except ValueError:
            print('Skipped invalid item reminder time', file=sys.stderr)
            continue
        if not at <= now < at + timedelta(hours=24):
            continue
        title = f'{kinds.get(item["kind"], "事项")}提醒 · {item["title"]}'
        body = f'**{item["title"]}**\n\n提醒时间：{item["remindAt"].replace("T", " ")}（{settings["timezone"]}）'
        if item.get('dueAt'):
            body += f'\n\n事项时间：{item["dueAt"].replace("T", " ")}'
        if item.get('notes'):
            body += f'\n\n{item["notes"]}'
        body += '\n\n[打开课表](https://timetable.krahsu.top)'
        yield job(f'item:{item["id"]}:{item["remindAt"]}:{settings["timezone"]}', title, body, at, at + timedelta(hours=24))


def send(sendkey, title, body):
    match = re.fullmatch(r'sctp(\d+)t[A-Za-z0-9_-]+', sendkey)
    if not match:
        raise ValueError('Server3 SendKey missing or invalid')
    url = f'https://{match[1]}.push.ft07.com/send/{sendkey}.send'
    data = urllib.parse.urlencode({'title': title, 'desp': body, 'tags': 'timetable'}).encode()
    request = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.load(response)
    if result.get('code') != 0 or result.get('errno', 0) != 0:
        # Do not print the request URL, key, or full provider response.
        raise RuntimeError('Server3 rejected notification')


def run(db, sendkey, now, sender=send, dry_run=False):
    schedule = json.loads(db.execute('SELECT body FROM schedule WHERE id=1').fetchone()[0])
    config = json.loads(db.execute('SELECT body FROM reminders WHERE id=1').fetchone()[0])
    count = 0
    # Build jobs independently so an invalid DST time does not block other reminders.
    for task in jobs(schedule, config, now):
        record = db.execute('SELECT status,attempts,next_attempt FROM notification_deliveries WHERE key=?', (task['key'],)).fetchone()
        if record and (record[0] == 'sent' or record[2] > now.timestamp()):
            continue
        if dry_run:
            print(json.dumps({'title': task['title'], 'at': task['at'].isoformat()}, ensure_ascii=False))
            count += 1
            continue
        attempts = (record[1] if record else 0) + 1
        with db:
            db.execute("INSERT INTO notification_deliveries(key,status,attempts,next_attempt,title) VALUES(?,'pending',?,?,?) ON CONFLICT(key) DO UPDATE SET attempts=excluded.attempts,next_attempt=excluded.next_attempt", (task['key'], attempts, int(now.timestamp()) + 120, task['title']))
        try:
            sender(sendkey, task['title'], task['body'])
        except Exception as error:
            delay = min(900, 30 * 2 ** min(attempts, 5))
            with db:
                db.execute('UPDATE notification_deliveries SET next_attempt=? WHERE key=?', (int(now.timestamp()) + delay, task['key']))
            print(f'Notification failed ({type(error).__name__}); retry scheduled', file=sys.stderr)
            continue
        with db:
            db.execute("UPDATE notification_deliveries SET status='sent',sent_at=? WHERE key=?", (now.isoformat(), task['key']))
        print(f'Notification delivered: {task["key"][:12]}', flush=True)
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()
    key = os.environ.get('SERVERCHAN3_SENDKEY', '')
    if args.test:
        send(key, '课间 · Server3 已接入', '课程将在开始前 30 分钟提醒。\n\n作业、考试和其他事项可在「事项与提醒」中设置任意提醒时间。\n\n[打开课表](https://timetable.krahsu.top)')
        print('Server3 test notification delivered')
        return
    data = Path(os.environ.get('TIMETABLE_DATA', '/home/charles/apps/timetable/data'))
    with (data / '.notify.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        with sqlite3.connect(data / 'schedule.sqlite3', timeout=10) as db:
            run(db, key, datetime.now(UTC), dry_run=args.dry_run)


if __name__ == '__main__':
    main()
