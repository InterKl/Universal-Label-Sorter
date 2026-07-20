"""App version + update check against the shared distribution folder.

Staff already have the shared Drive/Dropbox folder configured for the SKU
map (see sorter.config) — that same folder doubles as the update channel, so
there is no separate server to run. version.json there looks like:

    {"latest": "1.2.0", "notes": "แก้บั๊กการจัดเรียงออเดอร์ผสม"}

This is advisory only: a staff machine with no shared folder configured yet,
or a version.json that's missing/unreadable, must never block or crash the
app — it just skips showing the banner.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import get_settings

APP_VERSION = "1.0.0"


def _parse(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in v.strip().split("."))
    except ValueError:
        return (0,)


def check_for_update() -> dict | None:
    """Returns {"latest": str, "notes": str} if a newer version is published
    in the shared folder, else None (up to date, or nothing to check).
    """
    shared_sku_path = get_settings().get("shared_sku_map_path")
    if not shared_sku_path:
        return None

    version_file = Path(shared_sku_path).parent / "version.json"
    if not version_file.exists():
        return None

    try:
        with open(version_file, encoding="utf-8") as f:
            data = json.load(f)
        latest = str(data.get("latest", ""))
    except (json.JSONDecodeError, OSError):
        return None

    if not latest or _parse(latest) <= _parse(APP_VERSION):
        return None

    return {"latest": latest, "notes": str(data.get("notes", ""))}
