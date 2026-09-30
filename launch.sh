#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

export DISPLAY="${DISPLAY:-:0}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

# Give the persistent service ownership of the API before opening the screen.
systemctl --user start screensaver.service
/usr/bin/python3 - <<'PY'
import json
import time
import urllib.request
for attempt in range(100):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8767/api/resources', timeout=1) as response:
            if json.load(response).get('app') == 'clock-screensaver':
                break
    except (OSError, ValueError):
        pass
    time.sleep(0.1)
else:
    raise SystemExit('scr-saver resource service did not start')
PY
exec /usr/bin/python3 "$project_dir/screensaver.py" --now
