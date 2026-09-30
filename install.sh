#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$project_dir"
for dependency in python3 npm google-chrome systemctl; do
  command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; exit 1; }
done
npm ci
npm run build

python3 - "$project_dir" <<'PY'
import os
import subprocess
import sys
from pathlib import Path

project = Path(sys.argv[1])
home = Path.home()

def desktop_quote(value):
    value = str(value)
    for character in ('\\', '"', '`', '$'):
        value = value.replace(character, '\\' + character)
    return '"' + value.replace('%', '%%') + '"'

unit_dir = home / '.config/systemd/user'
unit_dir.mkdir(parents=True, exist_ok=True)
# Escape percent specifiers and systemd's quoted command syntax.
script = str(project / 'screensaver.py').replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
(unit_dir / 'screensaver.service').write_text(f'''[Unit]
Description=scr-saver clock and resource dashboard
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -u "{script}" --daemon --idle 1800
Restart=always
RestartSec=5
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_CURRENT_DESKTOP=ubuntu:GNOME

[Install]
WantedBy=default.target
''')

try:
    desktop = Path(subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True).strip())
except (FileNotFoundError, subprocess.CalledProcessError):
    desktop = home / 'Desktop'
desktop.mkdir(parents=True, exist_ok=True)
app_dir = home / '.local/share/applications'
app_dir.mkdir(parents=True, exist_ok=True)
entry = f'''[Desktop Entry]
Version=1.0
Type=Application
Name=scr-saver
Name[ko]=scr-saver 화면보호기
Comment=Open the clock and resource dashboard
Exec={desktop_quote(project / 'launch.sh')}
Icon={project / 'assets/scr-saver.svg'}
Terminal=false
StartupNotify=false
Categories=Utility;
'''
for destination in (desktop / 'scr-saver.desktop', app_dir / 'scr-saver.desktop'):
    destination.write_text(entry)
    destination.chmod(0o755)
    subprocess.run(['gio', 'set', str(destination), 'metadata::trusted', 'true'],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f'Desktop shortcut: {desktop / "scr-saver.desktop"}')
PY

systemctl --user daemon-reload
systemctl --user enable screensaver.service
systemctl --user restart screensaver.service
echo 'Installed: desktop shortcut and 30-minute idle screensaver.'
