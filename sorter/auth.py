"""Admin / history-tab passwords for the desktop build.

There is no central server to hold a secret, and asking the owner to
re-type the same password into every staff machine invites drift. Instead,
piggyback on the shared folder already used for the SKU map (see
sorter.config) and version.json (see sorter.version): an auth.json there
holds both passwords, so setting one on any connected machine applies to
all of them.

Mirrors sorter.config's shared/local fallback exactly, and for the same
reason: a machine with no shared folder configured yet (or not yet, or ever
— a lone user testing the app) must still be able to set a working password,
just one that stays local to that machine until a shared folder is connected.

Resolution order (first match wins):
  1. Environment variable (ADMIN_PASSWORD / HISTORY_PASSWORD) — power-user
     override, mainly useful for local development.
  2. auth.json in the shared folder, if one is connected.
  3. auth.json in this machine's local app-data dir.
  4. "" — the caller shows "not configured" / bootstrap-setup rather than
     defaulting to no password.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import get_settings
from .paths import app_data_dir


def _auth_file() -> Path:
    shared_sku_path = get_settings().get("shared_sku_map_path")
    if shared_sku_path:
        return Path(shared_sku_path).parent / "auth.json"
    return app_data_dir() / "auth.json"


def _read_auth() -> dict:
    path = _auth_file()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_auth(update: dict) -> None:
    path = _auth_file()
    data = _read_auth()
    data.update(update)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD") or _read_auth().get("admin_password", "")


def get_history_password() -> str:
    return (
        os.environ.get("HISTORY_PASSWORD")
        or _read_auth().get("history_password")
        or get_admin_password()
    )


def set_admin_password(password: str) -> None:
    _write_auth({"admin_password": password})


def set_history_password(password: str) -> None:
    _write_auth({"history_password": password})
