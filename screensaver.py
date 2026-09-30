#!/usr/bin/env python3
"""
Modern Clock Screensaver Controller
- Provides instant launch, countdown timer (e.g. 30 minutes), and background idle daemon.
"""

import os
import sys
import time
import subprocess
import argparse
import signal
import json
import hmac
import mimetypes
import shutil
import threading
import urllib.request
from urllib.parse import unquote, urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from maintenance import CacheMaintenance

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "dist"
PROFILE_DIR = Path("/tmp/screensaver-chrome-profile")
PID_FILE = Path("/tmp/screensaver-active.pid")
SERVER_URL = "http://127.0.0.1:8767"


class ResourceMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.previous_cpu = self.read_cpu()

    @staticmethod
    def read_cpu():
        with open("/proc/stat") as source:
            values = [int(value) for value in source.readline().split()[1:9]]
        return sum(values), values[3] + values[4]

    @staticmethod
    def disk_snapshot(path):
        if path != "/" and not os.path.ismount(path):
            return {"available": False, "percent": 0, "used": 0, "total": 0, "remaining": 0, "path": path}
        disk = shutil.disk_usage(path)
        # Match df: reserved blocks are excluded from available space.
        return {"available": True, "percent": round(100 * disk.used / (disk.used + disk.free), 1),
                "used": disk.used, "total": disk.total, "remaining": disk.free, "path": path}

    def snapshot(self):
        with self.lock:
            total, idle = self.read_cpu()
            previous_total, previous_idle = self.previous_cpu
            elapsed = total - previous_total
            cpu_percent = 100 * (1 - (idle - previous_idle) / elapsed) if elapsed > 0 else 0
            self.previous_cpu = (total, idle)

        memory = {}
        with open("/proc/meminfo") as source:
            for line in source:
                key, value = line.split(":", 1)
                memory[key] = int(value.split()[0]) * 1024
        ram_total = memory["MemTotal"]
        ram_used = ram_total - memory["MemAvailable"]
        return {
            "app": "clock-screensaver",
            "frontendVersion": str((WEB_DIR / "index.html").stat().st_mtime_ns),
            "cpu": {"percent": round(max(0, min(100, cpu_percent)), 1)},
            "ram": {"percent": round(100 * ram_used / ram_total, 1),
                    "used": ram_used, "total": ram_total, "remaining": memory["MemAvailable"]},
            "disk": self.disk_snapshot("/"),
            "hdd": self.disk_snapshot("/mnt/data"),
        }


def start_resource_server(allow_reuse=True):
    """Serve the dashboard and Linux resource readings on loopback only."""
    if not (WEB_DIR / "index.html").is_file():
        raise RuntimeError(f"Dashboard build missing. Run npm run build in {BASE_DIR}")
    monitor = ResourceMonitor()
    maintenance = CacheMaintenance()

    class Handler(BaseHTTPRequestHandler):
        def json_response(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def trusted_host(self):
            return self.headers.get('Host') in ('127.0.0.1:8767', 'localhost:8767')

        def do_GET(self):
            if not self.trusted_host():
                self.json_response(403, {'error': 'Local requests only'})
                return
            route = unquote(urlsplit(self.path).path)
            if route == '/api/maintenance':
                try:
                    self.json_response(200, maintenance.info())
                except OSError:
                    self.json_response(503, {'error': '캐시 정보를 읽을 수 없습니다'})
                return
            if route == "/api/resources":
                try:
                    body = json.dumps(monitor.snapshot()).encode()
                except (OSError, ValueError, KeyError):
                    self.send_error(503, "Resource readings unavailable")
                    return
                content_type = "application/json"
            else:
                filename = "index.html" if route in ("/", "/clock.html") else route.lstrip("/")
                asset = (WEB_DIR / filename).resolve()
                if not asset.is_relative_to(WEB_DIR.resolve()) or not asset.is_file():
                    self.send_error(404)
                    return
                body = asset.read_bytes()
                content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            origins = ('http://127.0.0.1:8767', 'http://localhost:8767',
                       'http://127.0.0.1:5173', 'http://localhost:5173')
            if not self.trusted_host() or self.headers.get('Origin') not in origins:
                self.json_response(403, {'error': '허용되지 않은 요청입니다'})
                return
            if self.headers.get('Content-Type', '').split(';', 1)[0] != 'application/json':
                self.json_response(415, {'error': 'JSON 요청만 지원합니다'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 1 or length > 4096:
                    raise ValueError('잘못된 요청 크기입니다')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('잘못된 요청입니다')
                token = payload.get('token')
                if not isinstance(token, str) or not token.isascii() or not hmac.compare_digest(token, maintenance.token):
                    self.json_response(403, {'error': '요청을 새로 열고 다시 시도하세요'})
                    return
                route = urlsplit(self.path).path
                if route == '/api/maintenance/preview':
                    result = maintenance.preview(payload.get('target'), payload.get('path', ''), payload.get('days', 7))
                elif route == '/api/maintenance/execute':
                    if payload.get('confirmed') is not True or not isinstance(payload.get('previewId'), str):
                        raise ValueError('정리 대상 확인이 필요합니다')
                    result = maintenance.execute(payload['previewId'])
                else:
                    self.json_response(404, {'error': '지원하지 않는 요청입니다'})
                    return
                self.json_response(200, result)
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self.json_response(400, {'error': str(error)})
            except subprocess.TimeoutExpired:
                self.json_response(504, {'error': '정리 시간이 초과되었습니다'})
            except OSError:
                self.json_response(500, {'error': '캐시 폴더를 읽거나 정리할 수 없습니다'})

        def log_message(self, *_):
            pass

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 8767), Handler)
    except OSError:
        if not allow_reuse:
            # The daemon must own its server so an exiting launcher cannot stop it.
            raise
        # An immediate launch can reuse the idle daemon's dashboard server.
        with urllib.request.urlopen(f"{SERVER_URL}/api/resources", timeout=2) as response:
            if json.load(response).get("app") != "clock-screensaver":
                raise RuntimeError("Port 8767 is already used by another application")
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

def is_screensaver_running():
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return False

def launch_screensaver():
    """Launch the modern clock screensaver in Chrome Kiosk mode."""
    if is_screensaver_running():
        print("[Screensaver] Already running.")
        return

    cmd = [
        "google-chrome",
        "--kiosk",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-extensions",
        "--disable-component-update",
        "--hide-scrollbars",
        f"{SERVER_URL}/"
    ]

    print("[Screensaver] Launching modern clock screensaver...")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PID_FILE.write_text(str(proc.pid))

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
    finally:
        PID_FILE.unlink(missing_ok=True)
        print("[Screensaver] Exited.")

def get_gnome_idletime_ms():
    """Query GNOME Mutter IdleMonitor via gdbus."""
    try:
        res = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
             "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
             "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"],
            capture_output=True, text=True, check=True
        )
        # Output format: (uint64 12345,)
        output = res.stdout.strip()
        idle_ms = int(output.split()[1].rstrip(',)'))
        return idle_ms
    except Exception as e:
        return 0

def run_idle_daemon(idle_limit_sec=1800, check_interval_sec=5):
    """
    Monitor user idle time. When idle exceeds idle_limit_sec (default 30 mins),
    activate screensaver if not already running.
    """
    print(f"[Daemon] Screensaver idle monitor started (Threshold: {idle_limit_sec}s / {idle_limit_sec//60} mins)...")
    idle_limit_ms = idle_limit_sec * 1000

    while True:
        try:
            if not is_screensaver_running():
                idle_ms = get_gnome_idletime_ms()
                if idle_ms >= idle_limit_ms:
                    print(f"[Daemon] Idle reached ({idle_ms // 1000}s). Activating screensaver...")
                    launch_screensaver()
            time.sleep(check_interval_sec)
        except KeyboardInterrupt:
            print("[Daemon] Stopped.")
            break
        except Exception as e:
            time.sleep(check_interval_sec)

def run_timer(wait_sec):
    """Wait for wait_sec seconds, then trigger screensaver."""
    print(f"[Timer] Waiting {wait_sec} seconds ({wait_sec / 60:.1f} minutes) before launching screensaver...")
    time.sleep(wait_sec)
    launch_screensaver()

def main():
    parser = argparse.ArgumentParser(description="Modern Clock Screensaver")
    parser.add_argument("--now", action="store_true", help="Launch screensaver immediately")
    parser.add_argument("--timer", type=str, help="Launch after timer duration (e.g. 30m, 1800s, 30)")
    parser.add_argument("--daemon", action="store_true", help="Run background idle monitor")
    parser.add_argument("--idle", type=int, default=1800, help="Idle threshold in seconds for daemon (default: 1800)")

    args = parser.parse_args()

    start_resource_server(allow_reuse=not args.daemon)

    if args.daemon:
        run_idle_daemon(idle_limit_sec=args.idle)
    elif args.timer:
        val = args.timer.lower()
        if val.endswith('m'):
            sec = int(val[:-1]) * 60
        elif val.endswith('s'):
            sec = int(val[:-1])
        elif val.endswith('h'):
            sec = int(val[:-1]) * 3600
        else:
            sec = int(val)
        run_timer(sec)
    else:
        # Default: launch immediately if --now or no arg given
        launch_screensaver()

if __name__ == "__main__":
    main()
