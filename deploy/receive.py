#!/usr/bin/env python3
"""Root-installed forced SSH command: accept one timetable release via stdin.

The CI key cannot start a shell, forward ports, or write arbitrary server paths.
Install this file at /usr/local/libexec/timetable-receive.py (root:root 0755).
"""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

BASE = Path('/home/charles/apps/timetable')
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
PUBLIC = {'index.html', 'style.css', 'app.mjs', 'core.mjs', 'icon.svg', 'serif.woff2', 'font-license.txt'}


def release_id(command):
    match = re.fullmatch(r'deploy ([0-9a-f]{40})', command)
    if not match:
        raise ValueError('Only deploy <40-character commit SHA> is allowed')
    return match[1]


def extract(archive, target, revision):
    """Extract an allowlisted release; links and path traversal are rejected."""
    total, seen = 0, set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
        for item in bundle:
            name = item.name.removeprefix('./').rstrip('/')
            if item.isdir() and name in ('public', 'public/assets', ''):
                continue
            allowed = name in {'server.py', 'timetable-server', 'REVISION'} or (PurePosixPath(name).parent == PurePosixPath('public') and PurePosixPath(name).name in PUBLIC) or re.fullmatch(r'public/assets/[A-Za-z0-9_-]+\.(?:js|css)', name)
            if not allowed or not item.isfile() or name in seen:
                raise ValueError(f'Invalid release entry: {name}')
            seen.add(name)
            total += item.size
            if total > MAX_EXPANDED:
                raise ValueError('Release exceeds size limit')
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(item) as source, path.open('xb') as out:
                shutil.copyfileobj(source, out)
            path.chmod(0o644)
    if 'timetable-server' in seen:
        required = {'timetable-server', 'REVISION', 'public/index.html', 'public/icon.svg', 'public/serif.woff2', 'public/font-license.txt'}
        assets = {name for name in seen if name.startswith('public/assets/')}
        if seen != required | assets or not any(x.endswith('.js') for x in assets) or not any(x.endswith('.css') for x in assets):
            raise ValueError('Release is missing required Rust/Vue files')
        binary = target / 'timetable-server'
        with binary.open('rb') as stream:
            header = stream.read(20)
        if len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or header[18:20] != b'\x3e\x00':
            raise ValueError('Expected a Linux x86_64 ELF executable')
        binary.chmod(0o755)
    else:
        expected = {'server.py', 'REVISION'} | {'public/' + name for name in PUBLIC}
        if seen != expected:
            raise ValueError('Release is missing required application files')
        compile((target / 'server.py').read_text(), 'server.py', 'exec')
    if (target / 'REVISION').read_text().strip() != revision:
        raise ValueError('Release revision does not match requested commit')


def health(revision):
    for _ in range(20):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=2) as response:
                value = json.load(response)
            if value.get('ok') and value.get('revision') == revision:
                with urllib.request.urlopen('http://127.0.0.1:8765/api/schedule', timeout=2) as response:
                    schedule = json.load(response)
                if isinstance(schedule.get('data', {}).get('courses'), list):
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def switch(target):
    link = BASE / '.current-next'
    link.unlink(missing_ok=True)
    link.symlink_to(target)
    link.replace(BASE / 'current')


def restart():
    subprocess.run(['sudo', '-n', '/usr/bin/systemctl', 'restart', 'timetable.service'], check=True, timeout=40)


def deploy(archive, revision):
    releases = BASE / 'releases'
    releases.mkdir(exist_ok=True)
    current = BASE / 'current'
    if not current.is_symlink():
        raise ValueError('Server has not been bootstrapped with a current release')
    with (BASE / '.deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix='.incoming-', dir=releases) as temporary:
            staging = Path(temporary)
            extract(archive, staging, revision)
            release = releases / revision
            if release.exists():
                for file in staging.rglob('*'):
                    if file.is_file() and file.read_bytes() != (release / file.relative_to(staging)).read_bytes():
                        raise ValueError('A different artifact already exists for this commit')
            else:
                shutil.copytree(staging, release)
                release.chmod(0o755)
        previous = current.resolve()
        # SQLite backup includes committed WAL data; deployment never replaces live data.
        backups = BASE / 'backups'
        backups.mkdir(exist_ok=True, mode=0o700)
        backup = backups / (time.strftime('%Y%m%d-%H%M%S') + '-' + revision[:12] + '.sqlite3')
        with sqlite3.connect(BASE / 'data/schedule.sqlite3') as source, sqlite3.connect(backup) as destination:
            source.backup(destination)
        switch(release)
        try:
            restart()
            if not health(revision):
                raise RuntimeError('New release failed health check')
        except Exception:
            switch(previous)
            restart()
            old_revision = (previous / 'REVISION').read_text().strip()
            if not health(old_revision):
                raise RuntimeError('Rollback failed health check; inspect timetable.service')
            raise RuntimeError('Deployment failed; previous release restored')
        print(json.dumps({'deployed': revision, 'previous': previous.name, 'artifact_sha256': hashlib.sha256(archive).hexdigest()}), flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    try:
        revision = release_id(os.environ.get('SSH_ORIGINAL_COMMAND', ''))
        archive = sys.stdin.buffer.read(MAX_ARCHIVE + 1)
        if not archive or len(archive) > MAX_ARCHIVE:
            raise ValueError('Invalid release archive size')
        deploy(archive, revision)
    except Exception as error:
        print(f'Deployment error: {error}', file=sys.stderr)
        sys.exit(1)
