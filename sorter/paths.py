"""Path resolution for the desktop build.

Two distinct concerns, kept separate on purpose:

  resource_path()  -- READ-ONLY files bundled inside the frozen app (fonts,
                       the seed sku_map.json). Under PyInstaller, __file__
                       points into a temp extraction dir, not the source
                       tree, so these must be resolved via sys._MEIPASS.

  app_data_dir()   -- WRITABLE per-machine storage (settings.json, the local
                       fallback sku_map.json, batch history). Never inside
                       the bundle: onedir/onefile installs are reinstalled/
                       overwritten on every update, and are not guaranteed
                       writable (e.g. Program Files on Windows).

APP_NAME fixes the folder name used in both OS-standard locations below, so
it must stay in sync with anything referencing those paths directly (install
docs, support instructions).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "LabelSorter"


def resource_path(*parts: str) -> Path:
    """Resolve a bundled, read-only resource by relative path parts.

    Works identically when running from source (this file's location) and
    when frozen by PyInstaller (sys._MEIPASS, the onedir/onefile extraction
    root set at runtime).
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


def app_data_dir() -> Path:
    """Per-OS writable directory for this app's local state.

    macOS:   ~/Library/Application Support/LabelSorter
    Windows: %APPDATA%\\LabelSorter   (Roaming, per-user)
    Other:   ~/.local/share/LabelSorter (XDG-ish fallback; not a target
             platform, but avoids a hard crash if ever run there)
    """
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def batches_dir() -> Path:
    path = app_data_dir() / "batches"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_sku_map_path() -> Path:
    """Per-machine fallback copy, used only when no shared-folder path is
    configured yet (see sorter.config for the full resolution order).
    """
    return app_data_dir() / "sku_map.json"
