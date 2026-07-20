"""TikTok label sorter — groups shipping labels by product for efficient
picking. Ported from tiktok_label_sorter.py into a pure function operating on
in-memory uploaded files instead of hardcoded paths.

Reads a TikTok Shop "To Ship" order CSV and the matching shipping-label PDF,
then reorders the PDF pages so same-product orders are contiguous.

Matching key: each PDF label page carries "Order ID: <id>", which matches the
CSV "Order ID" column.

Notes on TikTok labels:
  - One PDF page per line-item. A multi-item (MIXED) order therefore prints
    2+ pages that share the same Order ID. All pages of one order are kept
    contiguous (anchored to the order's first page index).

Output flow (mirrors sorter.shopee):
  Phase A: single-product, qty = 1, grouped by product (size-then-type)
  Phase B: single-product, qty >= 2, same group ordering
  Phase C: MIXED (orders with 2+ distinct products) — all pages kept together
  Phase D: UNKNOWN (page has no matching CSV row / unmapped product)
"""
from __future__ import annotations

import io
import re

import pandas as pd
from pypdf import PdfReader

from . import summary as summary_mod
from .config import Config
from .core import (
    SortResult,
    build_picking_rows,
    build_sorted_pdf_bytes,
    group_sort_key,
    phase_summary_lines,
    today_stamp,
)

_ORDER_RE = re.compile(r"Order ID:\s*(\d+)")


def _clean(v) -> str:
    return (v or "").strip().strip("\t").strip()


def _translate_row(seller_sku: str, product_name: str, config: Config) -> str:
    """Return the picking group label for one CSV line-item."""
    seller_sku = (seller_sku or "").strip()
    if seller_sku:
        return config.sku_map.get(seller_sku, f"[{seller_sku}]")
    name = product_name or ""
    for pattern, label in config.name_map:
        if pattern.search(name):
            return label
    return "[UNKNOWN]"


def _read_csvs(csv_files: list) -> pd.DataFrame:
    frames = []
    for f in csv_files:
        if hasattr(f, "seek"):
            f.seek(0)
        frames.append(pd.read_csv(f, dtype=str, keep_default_na=False, encoding="utf-8-sig"))
    return pd.concat(frames, ignore_index=True)


def sort_tiktok(csv_files: list, pdf_files: list, config: Config) -> SortResult:
    """csv_files/pdf_files: file-like objects (Streamlit UploadedFile or path)."""
    warnings: list[str] = []

    df = _read_csvs(csv_files)
    df["_oid"] = df["Order ID"].map(_clean)

    order_items: dict[str, list[tuple[str, int, str]]] = {}
    for _, row in df.iterrows():
        oid = row["_oid"]
        if not oid:
            continue
        try:
            qty = int(float(_clean(row.get("Quantity")) or "1"))
        except ValueError:
            qty = 1
        label = _translate_row(row.get("Seller SKU"), row.get("Product Name"), config)
        order_items.setdefault(oid, []).append((_clean(row.get("Seller SKU")), qty, label))

    readers = [PdfReader(f) for f in pdf_files]
    all_pages = [page for r in readers for page in r.pages]
    num_pages = len(all_pages)

    page_info = []  # {idx, order_id, phase, group}
    pages_without_id = []  # aggregated below — a scanned PDF would otherwise
                           # emit one warning per page and flood the UI
    for i, page in enumerate(all_pages):
        text = page.extract_text() or ""
        matches = _ORDER_RE.findall(text)
        if not matches:
            pages_without_id.append(i + 1)
            oid = None
        else:
            oid = matches[0]
            if len(set(matches)) > 1:
                warnings.append(
                    f"หน้า {i + 1}: พบหลาย Order ID {set(matches)} — ใช้ {oid} / "
                    f"page {i + 1}: multiple Order IDs found — using {oid}"
                )

        items = order_items.get(oid, [])
        if not items:
            phase, group = "D", "[UNKNOWN]"
        elif len(items) >= 2:
            phase, group = "C", "MIXED"
        else:
            _, qty, label = items[0]
            group = label
            # qty<=1 packs as a single unit; only qty>=2 needs the Phase B
            # multi-pick treatment (a 0/blank qty must not land in Phase B).
            phase = "A" if qty <= 1 else "B"

        page_info.append({"idx": i, "order_id": oid, "phase": phase, "group": group})

    if pages_without_id:
        shown = ", ".join(str(n) for n in pages_without_id[:20])
        more = f" ... (+{len(pages_without_id) - 20})" if len(pages_without_id) > 20 else ""
        warnings.append(
            f"{len(pages_without_id)} หน้าไม่พบ Order ID (อาจเป็นไฟล์สแกน) / "
            f"{len(pages_without_id)} page(s) had no readable Order ID "
            f"(a scanned/image PDF?): หน้า {shown}{more}"
        )

    # First-page index per order, so all pages of one order stay contiguous
    first_idx: dict[str, int] = {}
    for p in page_info:
        if p["order_id"] is not None:
            first_idx.setdefault(p["order_id"], p["idx"])

    def sort_key(p):
        from .core import PHASE_RANK
        grank, gkey = group_sort_key(p["group"], config)
        order_anchor = first_idx.get(p["order_id"], p["idx"])
        return (PHASE_RANK[p["phase"]], grank, gkey, order_anchor, p["idx"])

    sorted_pages = sorted(page_info, key=sort_key)

    phase_summary = phase_summary_lines(sorted_pages, config)
    picking_rows = build_picking_rows(sorted_pages, order_items, "order_id")
    pdf_bytes = build_sorted_pdf_bytes(all_pages, sorted_pages)

    # Reordered CSV (rows reordered to match label order, unique order sequence)
    ordered_oids = []
    seen = set()
    for p in sorted_pages:
        oid = p["order_id"]
        if oid and oid not in seen:
            seen.add(oid)
            ordered_oids.append(oid)

    rank = {oid: i for i, oid in enumerate(ordered_oids)}
    df["_rank"] = df["_oid"].map(lambda o: rank.get(o, len(rank)))
    df_sorted = (
        df.sort_values(["_rank"], kind="stable")
        .drop(columns=["_oid", "_rank"])
        .reset_index(drop=True)
    )

    unmatched = [p for p in sorted_pages if p["order_id"] not in order_items]
    if unmatched:
        warnings.append(
            f"{len(unmatched)} หน้า PDF ไม่พบออเดอร์ใน CSV ที่ตรงกัน (เก็บไว้ใน PDF) / "
            f"{len(unmatched)} PDF page(s) have no matching CSV order (kept in PDF): "
            + ", ".join(f"page {p['idx'] + 1} ({p['order_id']!r})" for p in unmatched)
        )

    orders_bytes = df_sorted.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    # จำนวนใบพัด summary
    df_for_summary = df.drop(columns=["_rank"], errors="ignore")
    line_items = summary_mod.load_line_items_tiktok(df_for_summary, config)
    summary_df = summary_mod.build_report(line_items, config, warnings)
    summary_bytes = summary_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    stamp = today_stamp()
    return SortResult(
        pdf_bytes=pdf_bytes,
        orders_bytes=orders_bytes,
        orders_filename=f"Tiktok_Orders_Sorted_{stamp}.csv",
        summary_df=summary_df,
        summary_bytes=summary_bytes,
        phase_summary=phase_summary,
        picking_rows=picking_rows,
        warnings=warnings,
        num_pages=num_pages,
        num_orders=len(df_sorted),
    )
