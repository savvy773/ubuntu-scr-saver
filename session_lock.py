#!/usr/bin/env python3
"""Lock the local desktop (seat0) outside work hours.

Only the GNOME screen on the monitor is locked: SSH logins, Docker and other
services keep running. `--auto` is run by screensaver-lock.timer and locks
after work hours once the desk has been idle for a while.
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(os.environ.get("SCR_SAVER_LOG_DIR", Path(__file__).resolve().parent / "logs"))
PID_FILE = Path("/tmp/screensaver-active.pid")
GNOME_SCREENSAVER = ["gdbus", "call", "--session", "--dest", "org.gnome.ScreenSaver",
                     "--object-path", "/org/gnome/ScreenSaver"]

log = logging.getLogger("scr-saver.lock")


def setup_logging(name):
    if log.handlers:
        return
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(LOG_DIR / name, maxBytes=512 * 1024, backupCount=3)
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.formatter.converter = time.gmtime  # UTC timestamps
    log.addHandler(handler)
    log.setLevel(logging.INFO)


HOLIDAYS_FILE = Path(os.environ.get("SCR_SAVER_HOLIDAYS_FILE",
                                    Path(__file__).resolve().parent / "holidays.txt"))


def holidays():
    """Dates from holidays.txt; weekend-only holidays are omitted there."""
    try:
        lines = HOLIDAYS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        log.warning("holidays file missing: %s", HOLIDAYS_FILE)
        return set()
    dates = set()
    for line in lines:
        token = line.split("#", 1)[0].split()[:1]
        if not token:
            continue
        try:
            dates.add(datetime.strptime(token[0], "%Y-%m-%d").date())
        except ValueError:
            log.warning("ignoring holidays.txt line: %r", line)
    return dates


def in_work_hours(now=None):
    """Weekdays (not holidays) inside SCR_SAVER_WORK_HOURS, local time, default 07:00-18:00."""
    spec = os.environ.get("SCR_SAVER_WORK_HOURS", "07:00-18:00").strip()
    if not spec:
        return False
    now = now or datetime.now()
    days = holidays()
    if not any(day.year == now.year for day in days) and now.month == 12:
        log.warning("holidays.txt has no %d dates yet; add next year's holidays", now.year + 1)
    if now.date() in days:
        return False
    try:
        start, end = (datetime.strptime(part, "%H:%M").time() for part in spec.split("-", 1))
    except ValueError:
        log.warning("invalid SCR_SAVER_WORK_HOURS=%r; treating as off hours", spec)
        return False
    return now.weekday() < 5 and start <= now.time() < end


def lock_enabled():
    return os.environ.get("SCR_SAVER_LOCK_ON_EXIT", "1") != "0"


def seat_session():
    """The monitor's graphical session; SSH sessions have no seat and are never touched."""
    try:
        rows = subprocess.run(["loginctl", "list-sessions", "--no-legend"],
                              capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    uid = str(os.getuid())
    return next((cols[0] for cols in map(str.split, rows.splitlines())
                 if len(cols) > 3 and cols[1] == uid and cols[3] == "seat0"), None)


def is_locked():
    try:
        out = subprocess.run(GNOME_SCREENSAVER + ["--method", "org.gnome.ScreenSaver.GetActive"],
                             capture_output=True, text=True, timeout=5, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "true" in out


def idle_seconds():
    try:
        out = subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
                              "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                              "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"],
                             capture_output=True, text=True, timeout=5, check=True).stdout
        return int(out.split()[1].rstrip(",)")) // 1000
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 0


def screensaver_running():
    try:
        os.kill(int(PID_FILE.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def lock_session(reason):
    commands = [GNOME_SCREENSAVER + ["--method", "org.gnome.ScreenSaver.Lock"]]
    session = seat_session()
    if session:
        commands.append(["loginctl", "lock-session", session])
    for command in commands:
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=5)
            log.info("locked (%s) via %s", reason, command[0])
            return True
        except (OSError, subprocess.SubprocessError) as error:
            log.warning("lock via %s failed: %s", command[0], error)
    log.error("could not lock the session")
    return False


def lock_after_exit():
    """Called when a key press closes the screensaver."""
    if not lock_enabled():
        return
    if in_work_hours():
        log.info("work hours: exit without locking")
        return
    lock_session("screensaver exit")


def auto_lock(min_idle):
    """Timer tick: lock an idle, unlocked desk outside work hours."""
    if not lock_enabled() or in_work_hours():
        return
    # An open screensaver shows the dashboard and locks itself on exit.
    if screensaver_running() or is_locked():
        return
    idle = idle_seconds()
    if idle >= min_idle:
        lock_session(f"off hours, idle {idle}s")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--auto", action="store_true", help="lock if idle outside work hours")
    parser.add_argument("--idle", type=int, default=int(os.environ.get("SCR_SAVER_AUTOLOCK_IDLE", 600)),
                        help="minimum idle seconds for --auto (default 600)")
    args = parser.parse_args()
    setup_logging("lock.log")
    if args.auto:
        auto_lock(args.idle)
    else:
        lock_session("manual")


if __name__ == "__main__":
    sys.exit(main())
