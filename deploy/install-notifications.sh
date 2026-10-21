#!/usr/bin/env bash
# Install independently of application releases, after the reminders DB migration.
set -euo pipefail
cd -- "$(dirname -- "$0")"
base=/home/charles/apps/timetable
backup="$base/backups/notifications-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
chmod 700 "$backup"
for file in /usr/local/libexec/timetable-notify.py /etc/systemd/system/timetable-notify.service /etc/systemd/system/timetable-notify.timer; do
    if sudo -n test -f "$file"; then sudo -n cp -p "$file" "$backup/"; fi
done
# Only copy the Server3 key; never grant the worker access to certificate secrets.
sudo -n python3 - <<'PY'
from pathlib import Path
import re
import shlex
path = Path('/etc/timetable-notify.env')
if not path.exists():
    for line in Path('/etc/cert-monitor.env').read_text().splitlines():
        if line.startswith('SERVERCHAN3_SENDKEY='):
            values = shlex.split(line.split('=', 1)[1])
            if len(values) != 1 or not re.fullmatch(r'sctp[0-9]+t[A-Za-z0-9_-]+', values[0]):
                raise SystemExit('Invalid Server3 key')
            path.touch(mode=0o600)
            path.write_text('SERVERCHAN3_SENDKEY=' + values[0] + '\n')
            break
    else:
        raise SystemExit('Configure SERVERCHAN3_SENDKEY in /etc/timetable-notify.env')
path.chmod(0o600)
PY
sudo -n install -o root -g root -m 755 notify.py /usr/local/libexec/timetable-notify.py
sudo -n install -o root -g root -m 644 timetable-notify.service /etc/systemd/system/timetable-notify.service
sudo -n install -o root -g root -m 644 timetable-notify.timer /etc/systemd/system/timetable-notify.timer
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now timetable-notify.timer
sudo -n systemctl start timetable-notify.service
sudo -n systemctl status timetable-notify.timer --no-pager
