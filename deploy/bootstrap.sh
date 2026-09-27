#!/usr/bin/env bash
# Run once on rain after uploading server.py and deploy/ to .ci-setup/.
set -euo pipefail
base=/home/charles/apps/timetable
setup="$base/.ci-setup"
cd "$base"
test ! -e current
test -f data/schedule.sqlite3
mkdir -p releases/bootstrap backups
chmod 700 backups
cp -a public releases/bootstrap/
install -m 644 "$setup/server.py" releases/bootstrap/server.py
printf 'bootstrap\n' > releases/bootstrap/REVISION
cp -a /etc/systemd/system/timetable.service backups/timetable.service.before-ci
ln -s "$base/releases/bootstrap" current
sudo -n install -d -m 755 /usr/local/libexec
sudo -n install -o root -g root -m 755 "$setup/deploy/receive.py" /usr/local/libexec/timetable-receive.py
sudo -n install -m 644 "$setup/deploy/timetable.service" /etc/systemd/system/timetable.service
sudo -n systemctl daemon-reload
if ! sudo -n systemctl restart timetable.service; then
  sudo -n install -m 644 backups/timetable.service.before-ci /etc/systemd/system/timetable.service
  sudo -n systemctl daemon-reload
  sudo -n systemctl restart timetable.service
  exit 1
fi
python3 - <<'PY'
import json, time, urllib.request
for _ in range(20):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=2) as r:
            value = json.load(r)
        if value.get('revision') == 'bootstrap':
            print('Bootstrap release healthy')
            break
    except OSError:
        pass
    time.sleep(1)
else:
    raise SystemExit('Bootstrap health check failed')
PY
python3 - <<'PY'
from pathlib import Path
base = Path('/home/charles/apps/timetable')
key = (base / '.ci-setup/github-deploy.pub').read_text().strip()
assert key.startswith('ssh-ed25519 ')
line = 'restrict,command="/usr/bin/python3 /usr/local/libexec/timetable-receive.py" ' + key
authorized = Path.home() / '.ssh/authorized_keys'
existing = authorized.read_text() if authorized.exists() else ''
if key.split()[1] not in existing:
    with authorized.open('a') as f:
        f.write(('\n' if existing and not existing.endswith('\n') else '') + line + '\n')
authorized.chmod(0o600)
print('Dedicated timetable deployment key installed with a forced command')
PY
