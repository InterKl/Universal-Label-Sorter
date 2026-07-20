"""Local batch history — desktop build.

Each staff machine keeps its own history (there is no shared server), stored
under app_data_dir()/batches/<batch_id>/. Every file already exists as bytes
on the SortResult / exec-summary output — this module only persists them,
never recomputes.

Retention: since there is no cloud lifecycle rule to delete old batches for
us, purge_expired() must be called explicitly (app startup, after each sort).
30 days matches the retention decided for the hosted design; customer names/
addresses/phones are on this disk for that long, so the History tab stays
password-gated.
"""
from __future__ import annotations

import json
import random
import shutil
import string
from dataclasses import dataclass
from datetime import datetime, timedelta

from .core import BANGKOK
from .paths import batches_dir

# Filenames inside each batch's own directory. Kept fixed regardless of the
# original upload names, so load_batch_file() doesn't need to search.
FILES = {
    "labels": "labels_sorted.pdf",
    "orders": "orders_sorted",  # extension appended from meta["orders_ext"]
    "summary": "summary.csv",
    "exec_summary": "exec_summary.pdf",
}


@dataclass
class BatchMeta:
    batch_id: str
    platform: str
    created_at: str  # ISO 8601, Asia/Bangkok
    num_pages: int
    num_orders: int
    batch_no: int
    orders_ext: str
    order_filenames: list[str]
    pdf_filenames: list[str]
    warnings: list[str]


def _new_batch_id(platform: str) -> str:
    now = datetime.now(BANGKOK)
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{now:%Y%m%d-%H%M}-{platform}-{suffix}"


def save_batch(
    platform: str,
    result,
    exec_pdf_bytes: bytes,
    batch_no: int,
    order_filenames: list[str],
    pdf_filenames: list[str],
) -> str:
    """Persist one completed sort. Returns the new batch_id."""
    batch_id = _new_batch_id(platform)
    out_dir = batches_dir() / batch_id
    out_dir.mkdir(parents=True, exist_ok=False)

    orders_ext = result.orders_filename.rsplit(".", 1)[-1]

    (out_dir / FILES["labels"]).write_bytes(result.pdf_bytes)
    (out_dir / f"{FILES['orders']}.{orders_ext}").write_bytes(result.orders_bytes)
    (out_dir / FILES["summary"]).write_bytes(result.summary_bytes)
    (out_dir / FILES["exec_summary"]).write_bytes(exec_pdf_bytes)

    meta = BatchMeta(
        batch_id=batch_id,
        platform=platform,
        created_at=datetime.now(BANGKOK).isoformat(),
        num_pages=result.num_pages,
        num_orders=result.num_orders,
        batch_no=batch_no,
        orders_ext=orders_ext,
        order_filenames=order_filenames,
        pdf_filenames=pdf_filenames,
        warnings=result.warnings,
    )
    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta.__dict__, f, ensure_ascii=False, indent=2)

    return batch_id


def list_batches(days: int = 30) -> list[dict]:
    """Newest-first list of batch metadata (dicts, includes batch_id).
    Batches older than `days` are excluded even if not yet purged from disk.
    """
    cutoff = datetime.now(BANGKOK) - timedelta(days=days)
    out = []
    for d in batches_dir().iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            created = datetime.fromisoformat(meta["created_at"])
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            continue
        if created >= cutoff:
            out.append(meta)
    out.sort(key=lambda m: m["created_at"], reverse=True)
    return out


def load_batch_file(batch_id: str, kind: str) -> bytes:
    """kind is one of 'labels', 'orders', 'summary', 'exec_summary'."""
    out_dir = batches_dir() / batch_id
    if kind == "orders":
        with open(out_dir / "meta.json", encoding="utf-8") as f:
            ext = json.load(f)["orders_ext"]
        path = out_dir / f"{FILES['orders']}.{ext}"
    else:
        path = out_dir / FILES[kind]
    return path.read_bytes()


def purge_expired(days: int = 30) -> int:
    """Delete batch directories older than `days`. Returns count removed."""
    cutoff = datetime.now(BANGKOK) - timedelta(days=days)
    removed = 0
    for d in batches_dir().iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        try:
            with open(meta_path, encoding="utf-8") as f:
                created = datetime.fromisoformat(json.load(f)["created_at"])
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            # Unreadable/corrupt entry — remove it too rather than let it
            # accumulate forever with no way to age out.
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
            continue
        if created < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed
