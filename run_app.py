"""Desktop launcher — the actual entry point PyInstaller freezes.

Starts Streamlit's server in-process via streamlit.web.bootstrap (the
supported way to embed Streamlit, rather than shelling out to the `streamlit`
CLI, which would require bundling a second Python interpreter invocation)
and opens the default browser once the server is likely up.

Run directly for local development too: `python run_app.py` behaves the same
as the frozen app, so the launcher itself is exercised before every build.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser

import streamlit.web.bootstrap as bootstrap

from sorter.paths import resource_path

DEFAULT_PORT = 8765


def _find_free_port(start: int, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    # Every candidate was in use — let the OS pick one rather than fail outright.
    return 0


def _open_browser_when_ready(url: str) -> None:
    # bootstrap.run() blocks the main thread once the server starts, so the
    # browser is opened from a short-lived background thread instead of a
    # server-start callback (bootstrap exposes no public hook for one).
    time.sleep(1.5)
    webbrowser.open(url)


def main() -> None:
    port = _find_free_port(DEFAULT_PORT)
    url = f"http://localhost:{port}"

    threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()

    flag_options = {
        "server_port": port,
        "server_address": "localhost",
        "server_headless": True,
        # No source files change once frozen; polling for them wastes CPU
        # and, more importantly, PyInstaller's temp extraction dir isn't a
        # real project directory for the watcher to make sense of.
        "server_fileWatcherType": "none",
        "browser_gatherUsageStats": False,
        "global_developmentMode": False,
    }

    main_script = str(resource_path("app.py"))

    # bootstrap.run() alone does NOT apply flag_options on startup — it only
    # registers a watcher for *future* config-file changes. The `streamlit
    # run` CLI applies the initial config via this call before invoking
    # bootstrap.run(); skipping it silently falls back to every default
    # (port 8501 instead of our chosen port, etc), found by testing the
    # launcher against the real Streamlit source rather than assuming the
    # CLI and the programmatic API behave identically.
    bootstrap.load_config_options(flag_options=flag_options)

    bootstrap.run(main_script, False, [], flag_options)


if __name__ == "__main__":
    # PyInstaller's onedir build sets sys.frozen; multiprocessing-style
    # re-execution guards aren't needed here since Streamlit's server runs
    # in-process, but keep the standard idiom for clarity if that ever changes.
    if getattr(sys, "frozen", False):
        pass
    main()
