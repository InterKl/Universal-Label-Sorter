"""Shared helpers used by both the Shopee and TikTok sorters:
group ordering, phase ranking, PDF page reordering with safety checks, and
the Bangkok-local date stamp used in download filenames.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from pypdf import PdfWriter

from .config import Config


@dataclass
class SortResult:
    pdf_bytes: bytes
    orders_bytes: bytes
    orders_filename: str
    summary_df: pd.DataFrame
    summary_bytes: bytes
    phase_summary: list[str]
    picking_rows: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    num_pages: int = 0
    num_orders: int = 0

PHASE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
PHASE_LABELS = {
    "A": "Phase A (qty=1) ",
    "B": "Phase B (qty>=2)",
    "C": "Phase C (MIXED) ",
    "D": "Phase D (UNKNOWN)",
}

BANGKOK = ZoneInfo("Asia/Bangkok")


def today_stamp() -> str:
    """Date stamp for filenames, e.g. '18Jul', computed in Bangkok local time.

    Deliberately avoids the %-d strftime directive: it is POSIX-only (glibc
    extension) and raises ValueError on Windows, so every sort would crash.
    """
    now = datetime.now(BANGKOK)
    return f"{now.day}{now.strftime('%b')}"


def group_sort_key(label: str, config: Config) -> tuple[int, str]:
    """Known groups sort by their fixed rank; unknown groups sort last, alphabetically."""
    unmapped_rank = len(config.group_order)
    return (config.group_rank.get(label, unmapped_rank), label)


def phase_summary_lines(sorted_pages: list[dict], config: Config) -> list[str]:
    """Build the human-readable 'Phase A [42]: 12H×5, ...' lines."""
    from collections import Counter, defaultdict

    phase_groups: dict[str, Counter] = defaultdict(Counter)
    for p in sorted_pages:
        phase_groups[p["phase"]][p["group"]] += 1

    lines = []
    for ph in ("A", "B", "C", "D"):
        if ph not in phase_groups:
            continue
        counts = phase_groups[ph]
        ordered = sorted(counts.items(), key=lambda kv: group_sort_key(kv[0], config))
        parts = [f"{g}×{n}" for g, n in ordered]
        total = sum(counts.values())
        lines.append(f"{PHASE_LABELS[ph]} [{total}]: " + ", ".join(parts))
    return lines


def build_picking_rows(sorted_pages: list[dict], order_items: dict, id_field: str) -> list[dict]:
    """Build the executive-summary numbered picking list.

    One row per order, except Phase C (MIXED) orders which explode into one
    row per line item (each order's product_info entry), since a single
    mixed-order page/label covers several distinct products.

    TikTok prints one physical PDF page per line item, so a MIXED order's
    pages all carry the same order id — `seen_mixed` guards against
    re-emitting that order's items once per page (Shopee prints one page
    per order, so this guard is a no-op there).

    Highlight rule (per business definition):
      Phase A (qty=1):   no highlight
      Phase B (qty>=2):  green on the whole row — the single SKU's quantity is >=2
      Phase C (MIXED):   yellow, but only one cell per row, marking the group:
                          the first line item's "#" cell, every other line
                          item's "qty" cell (`highlight_cell` says which)
      Phase D (UNKNOWN): no highlight
    """
    rows = []
    seen_mixed = set()
    for p in sorted_pages:
        oid = p[id_field]
        phase = p["phase"]
        items = order_items.get(oid, [])
        if phase == "B":
            qty = items[0][1] if items else 1
            rows.append({"label": p["group"], "qty": qty, "highlight": "green", "highlight_cell": None})
        elif phase == "C":
            if oid in seen_mixed:
                continue
            seen_mixed.add(oid)
            for i, (_, qty, label) in enumerate(items):
                cell = "num" if i == 0 else "qty"
                rows.append({"label": label, "qty": qty, "highlight": "yellow", "highlight_cell": cell})
        else:  # A or D
            rows.append({"label": p["group"], "qty": 1, "highlight": None, "highlight_cell": None})
    return rows


class SortIntegrityError(Exception):
    """Raised when the reordered page set doesn't exactly match the input pages."""


def build_sorted_pdf_bytes(all_pages: list, sorted_pages: list[dict]) -> bytes:
    """Write `all_pages` in the order given by `sorted_pages` (each dict has 'idx'),
    after verifying no page was dropped, duplicated, or invented.
    """
    num_pages = len(all_pages)
    sorted_idx = [p["idx"] for p in sorted_pages]

    if len(sorted_idx) != num_pages:
        raise SortIntegrityError(
            f"หน้าหายไปหลังจากจัดเรียง (page count mismatch: {len(sorted_idx)} != {num_pages})"
        )
    if len(set(sorted_idx)) != num_pages:
        raise SortIntegrityError("พบหน้าซ้ำหลังจากจัดเรียง (duplicate pages after sort)")
    if set(sorted_idx) != set(range(num_pages)):
        raise SortIntegrityError("พบหน้าที่ขาดหายไปหลังจากจัดเรียง (missing pages after sort)")

    writer = PdfWriter()
    for p in sorted_pages:
        writer.add_page(all_pages[p["idx"]])

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
