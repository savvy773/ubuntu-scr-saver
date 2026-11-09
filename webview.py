#!/usr/bin/env python3
"""Fullscreen WebKitGTK window for the dashboard (lighter than a Chrome kiosk).

Exit code 3 means WebKitGTK is not installed, so the caller can fall back.
"""

import os
import sys
from pathlib import Path

# Native Wayland repaints cost ~10% CPU here; XWayland measured 0.7% (same as Chrome).
if os.environ.get("DISPLAY"):
    os.environ.setdefault("GDK_BACKEND", "x11")

try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gdk, Gtk, WebKit2
except (ImportError, ValueError) as error:
    print(f"[Webview] WebKitGTK unavailable: {error}", file=sys.stderr)
    sys.exit(3)

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "scr-saver/webkit"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "scr-saver/webkit"


def main(url):
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
    view.connect("close", lambda *_: window.destroy())
    # Disable the right-click menu (reload/inspect) like a kiosk.
    view.connect("context-menu", lambda *_: True)

    window.show_all()
    window.fullscreen()
    window.present()
    view.load_uri(url)
    view.grab_focus()
    Gtk.main()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8767/")
