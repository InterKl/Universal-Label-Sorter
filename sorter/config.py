"""Loads sku_map.json — the single source of truth for SKU translation and
group ordering, shared by the Shopee and TikTok sorters and the จำนวนใบพัด
summary. Editable from the app's admin tab.

Desktop build: each staff member runs their own copy of the app, so the SKU
map cannot live inside the (read-only, per-machine) bundle. Resolution order:

  1. Shared path      -- a folder (Drive/Dropbox) recorded in settings.json,
                          the same folder on every staff machine. This is the
                          live, writable copy everyone should end up using.
  2. Local fallback    -- app_data_dir()/sku_map.json, used until step 1 is
                          configured, or if the shared path is unreachable
                          (folder not synced yet, drive unmounted, etc).
  3. Bundled seed      -- resource_path("sku_map.json"), the file shipped
                          inside the app. Only used to *initialize* step 2 on
                          first run; never read after that.

Whichever file is currently active, get_sku_map_status() reports which tier
it came from, so the admin tab can show staff when a machine has silently
fallen back to its local copy instead of the shared one.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import NamedTuple

from .paths import local_sku_map_path, resource_path, settings_path

BUNDLED_SEED_PATH = resource_path("sku_map.json")


class Config(NamedTuple):
    sku_map: dict[str, str]
    name_map: list[tuple[re.Pattern, str]]
    group_order: list[str]
    group_rank: dict[str, int]


# ---------------------------------------------------------------------------
# settings.json — per-machine pointer to the shared SKU-map folder
# ---------------------------------------------------------------------------
def get_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict) -> None:
    with open(settings_path(), "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
        f.write("\n")


def set_shared_sku_map_path(folder: str) -> None:
    """Point this machine at a shared folder's sku_map.json. If that file
    doesn't exist yet, seed it from whatever is currently active, so pointing
    a second machine at an empty shared folder doesn't discard existing data.
    """
    shared_file = Path(folder).expanduser() / "sku_map.json"
    if not shared_file.exists():
        shared_file.parent.mkdir(parents=True, exist_ok=True)
        # _resolve_active_path() (not get_sku_map_status()) because a fresh
        # machine's status is "seeded" — a path that doesn't exist on disk
        # yet, only where a seed *would* go. Use the resolver that actually
        # performs that seeding, so there's a real file to copy from.
        current_path = _resolve_active_path()
        shutil.copy(current_path, shared_file)

    settings = get_settings()
    settings["shared_sku_map_path"] = str(shared_file)
    save_settings(settings)


def clear_shared_sku_map_path() -> None:
    settings = get_settings()
    settings.pop("shared_sku_map_path", None)
    save_settings(settings)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def get_sku_map_status() -> tuple[Path, str]:
    """Return (active_path, source) without mutating anything.
    source is one of "shared", "local", "seeded" (about to be created).
    """
    shared = get_settings().get("shared_sku_map_path")
    if shared and Path(shared).exists():
        return Path(shared), "shared"
    if local_sku_map_path().exists():
        return local_sku_map_path(), "local"
    return local_sku_map_path(), "seeded"


def _resolve_active_path() -> Path:
    path, source = get_sku_map_status()
    if source == "seeded":
        shutil.copy(BUNDLED_SEED_PATH, path)
    return path


def load_config(path: Path | None = None) -> Config:
    active_path = path or _resolve_active_path()
    with open(active_path, encoding="utf-8") as f:
        raw = json.load(f)

    sku_map = raw["sku_map"]
    name_map = [(re.compile(pattern, re.IGNORECASE), label) for pattern, label in raw["name_map"]]
    group_order = raw["numbered_bases"] + raw["juk_variants"] + raw["others"]
    group_rank = {g: i for i, g in enumerate(group_order)}

    return Config(sku_map=sku_map, name_map=name_map, group_order=group_order, group_rank=group_rank)


def save_sku_map(new_sku_map: dict[str, str], path: Path | None = None) -> None:
    """Overwrite just the sku_map section, preserving name_map/group ordering."""
    active_path = path or _resolve_active_path()
    with open(active_path, encoding="utf-8") as f:
        raw = json.load(f)
    raw["sku_map"] = new_sku_map
    with open(active_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Lazada group ordering
# ---------------------------------------------------------------------------
# Lazada's sellerSku already encodes the product label directly (e.g.
# "16HO-3" -> "16HO"; see sorter.lazada.translate_lazada_sku) -- there is no
# dict-based translation to maintain, only the *display order* of groups.
# That rarely changes, so unlike sku_map.json this is read straight from the
# bundled resource -- no shared-folder sync needed for this one.
def load_lazada_group_config() -> Config:
    path = resource_path("lazada_config.json")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    group_order = raw["numbered_bases"] + raw["juk_variants"] + raw["others"]
    group_rank = {g: i for i, g in enumerate(group_order)}
    return Config(sku_map={}, name_map=[], group_order=group_order, group_rank=group_rank)
