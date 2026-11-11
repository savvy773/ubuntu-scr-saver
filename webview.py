#!/usr/bin/env python3
"""Fullscreen WebKitGTK window for the dashboard (lighter than a Chrome kiosk).

Exit code 3 means WebKitGTK is not installed, so the caller can fall back.
"""

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import session_lock

# Native Wayland repaints cost ~10% CPU here; XWayland measured 0.7% (same as Chrome).
if os.environ.get("DISPLAY"):
    os.environ.setdefault("GDK_BACKEND", "x11")

try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gdk, GLib, Gtk, WebKit2
except (ImportError, ValueError) as error:
    print(f"[Webview] WebKitGTK unavailable: {error}", file=sys.stderr)
    sys.exit(3)

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "scr-saver/webkit"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "scr-saver/webkit"
LOG_DIR = Path(os.environ.get("SCR_SAVER_LOG_DIR", Path(__file__).resolve().parent / "logs"))
RETRY_MS = 2000

log = logging.getLogger("scr-saver.webview")


def setup_logging():
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(LOG_DIR / "webview.log", maxBytes=512 * 1024, backupCount=3)
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.formatter.converter = time.gmtime  # UTC timestamps
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def main(url):
    setup_logging()
    closed_by_key = False
    # Persistent storage keeps localStorage (quote order, HDD cache path).
    manager = WebKit2.WebsiteDataManager(base_data_directory=str(DATA_DIR),
                                         base_cache_directory=str(CACHE_DIR))
    context = WebKit2.WebContext.new_with_website_data_manager(manager)
    # Single local page: smallest memory/cache footprint.
    context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)

    view = WebKit2.WebView.new_with_context(context)
    settings = view.get_settings()
    settings.set_enable_page_cache(False)
    # GL compositing under XWayland flickers now and then; this small page
    # paints in software for ~1% CPU without GL buffer swaps.
    settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
    settings.set_enable_developer_extras(False)
    view.set_background_color(Gdk.RGBA(0, 0, 0, 1))

    window = Gtk.Window(title="scr-saver")
    window.add(view)
    window.connect("destroy", Gtk.main_quit)
    # The page calls window.close() on a key press (see src/screen-mode.ts).
    def on_close(*_):
        nonlocal closed_by_key
        closed_by_key = True
        window.destroy()

    view.connect("close", on_close)
    # Disable the right-click menu (reload/inspect) like a kiosk.
    view.connect("context-menu", lambda *_: True)

    # A crashed web process or a failed load leaves only the black background;
    # reload instead of sitting on a black screen until a key is pressed.
    def reload_later(reason):
        log.warning("reloading in %d ms: %s", RETRY_MS, reason)
        GLib.timeout_add(RETRY_MS, lambda: (view.load_uri(url), False)[1])

    view.connect("web-process-terminated",
                 lambda _view, why: reload_later(f"web process terminated ({why.value_nick})"))

    def on_load_failed(_view, _event, failing_uri, error):
        # A page-initiated reload cancels the old load; that is not a failure.
        cancelled = error.matches(WebKit2.network_error_quark(), WebKit2.NetworkError.CANCELLED)
        if not cancelled and failing_uri.rstrip("/") == url.rstrip("/"):
            reload_later(f"load failed: {error.message}")
            return True  # Keep the black background instead of WebKit's error page.
        return False

    view.connect("load-failed", on_load_failed)

    # Fullscreen before mapping so the first frame is not a resize from a normal window.
    window.fullscreen()
    window.show_all()
    window.present()
    log.info("open %s", url)
    view.load_uri(url)
    view.grab_focus()
    Gtk.main()
    log.info("closed")
    # Only a key exit locks; a service stop or restart (SIGTERM) does not.
    if closed_by_key:
        session_lock.log.handlers = log.handlers
        session_lock.log.setLevel(logging.INFO)
        session_lock.lock_after_exit()


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8767/")
    except Exception:
        log.exception("webview crashed")
        raise
