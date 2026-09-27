#!/usr/bin/env bash
# Run from an uploaded copy of deploy/ on rain; never changes application data.
set -euo pipefail
cd -- "$(dirname -- "$0")"
base=/home/charles/apps/timetable
test -L "$base/current"
test -f "$base/data/schedule.sqlite3"
backup="$base/backups/runtime-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
chmod 700 "$backup"
cp /etc/systemd/system/timetable.service "$backup/timetable.service"
cp /usr/local/libexec/timetable-receive.py "$backup/timetable-receive.py"
if test -f /usr/local/libexec/timetable-launch; then
    cp /usr/local/libexec/timetable-launch "$backup/timetable-launch"
fi
sudo -n install -o root -g root -m 755 receive.py /usr/local/libexec/timetable-receive.py
sudo -n install -o root -g root -m 755 timetable-launch /usr/local/libexec/timetable-launch
sudo -n install -o root -g root -m 644 timetable.service /etc/systemd/system/timetable.service
sudo -n systemctl daemon-reload
if ! sudo -n systemctl restart timetable.service; then
    sudo -n install -m 644 "$backup/timetable.service" /etc/systemd/system/timetable.service
    sudo -n install -m 755 "$backup/timetable-receive.py" /usr/local/libexec/timetable-receive.py
    sudo -n systemctl daemon-reload
    sudo -n systemctl restart timetable.service
    exit 1
fi
curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8765/healthz
