"""Shopee label sorter — groups shipping labels by product for efficient
picking. Ported from shopee_label_sorter.py into a pure function operating on
in-memory uploaded files instead of hardcoded paths.

Reads a Shopee packing-list xlsx and the matching shipping-label PDF, then
reorders the PDF pages so same-product orders are contiguous.

Output flow:
  Phase A: single-product, qty = 1, grouped by product (size-then-type)
  Phase B: single-product, qty >= 2, same group ordering
  Phase C: MIXED (orders with 2+ distinct products)
  Phase D: UNKNOWN (page has no matching xlsx row / unmapped product)
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

_PRODUCT_INFO_SPLIT_RE = re.compile(r"\[\d+\]\s*")
_SKU_RE = re.compile(r"เลขอ้างอิง SKU.*?:\s*([^;\s]+)")
_QTY_RE = re.compile(r"จำนวน:\s*(\d+)")
_NAME_RE = re.compile(r"ชื่อสินค้า:\s*([^;]+)")
_ORDER_RE = re.compile(r"Shopee Order No\.\s+(\S+)")


def _parse_product_info(text, config: Config) -> list[tuple[str, int]]:
    if not isinstance(text, str):
        return []
    parts = _PRODUCT_INFO_SPLIT_RE.split(text)
    items = []
    for part in parts:
        if not part.strip():
            continue
        sku_m = _SKU_RE.search(part)
        qty_m = _QTY_RE.search(part)
        name_m = _NAME_RE.search(part)
        sku = sku_m.group(1).strip() if sku_m else ""
        qty = int(qty_m.group(1)) if qty_m else 1
        if not sku and name_m:
            name = name_m.group(1).strip()
            for pattern, label in config.name_map:
                if pattern.search(name):
                    sku = label
                    break
        if sku:
            items.append((sku, qty))
    return items


def sort_shopee(xlsx_files: list, pdf_files: list, config: Config) -> SortResult:
    """xlsx_files/pdf_files: file-like objects (Streamlit UploadedFile or path)."""
    warnings: list[str] = []

    df = pd.concat(
        [pd.read_excel(f, sheet_name="orders") for f in xlsx_files],
        ignore_index=True,
    )

    order_items = {}  # order_sn -> list of (sku_raw, qty, translated_label)
    for _, row in df.iterrows():
        osn = str(row["order_sn"]).strip()
        parsed = _parse_product_info(row["product_info"], config)
        order_items[osn] = [
            (sku_raw, qty, config.sku_map.get(sku_raw, f"[{sku_raw}]"))
            for sku_raw, qty in parsed
        ]

    readers = [PdfReader(f) for f in pdf_files]
    all_pages = [page for r in readers for page in r.pages]
    num_pages = len(all_pages)
    if num_pages != len(df):
        warnings.append(
            f"จำนวนหน้า PDF ({num_pages}) ไม่ตรงกับจำนวนออเดอร์ ({len(df)}) / "
            f"page count ({num_pages}) != order count ({len(df)})"
        )

    page_info = []  # {idx, order_sn, phase, group}
    pages_without_id = []  # aggregated below — a scanned PDF would otherwise
                           # emit one warning per page and flood the UI
    for i, page in enumerate(all_pages):
        text = page.extract_text() or ""
        matches = _ORDER_RE.findall(text)
        if not matches:
            pages_without_id.append(i + 1)
            osn = None
        else:
            osn = matches[0]
            if len(matches) > 1 and len(set(matches)) > 1:
                warnings.append(
                    f"หน้า {i + 1}: พบหลายเลขออเดอร์ {matches} — ใช้ {osn} / "
                    f"page {i + 1}: multiple order_sn found — using {osn}"
                )

        items = order_items.get(osn, [])
        if not items:
            phase, group = "D", "[UNKNOWN]"
        elif len(items) >= 2:
            phase, group = "C", "MIXED"
        else:
            _, qty, translated = items[0]
            group = translated
            # qty<=1 packs as a single unit; only qty>=2 needs the Phase B
            # multi-pick treatment (a 0/blank qty must not land in Phase B).
            phase = "A" if qty <= 1 else "B"

        page_info.append({"idx": i, "order_sn": osn, "phase": phase, "group": group})

    if pages_without_id:
        shown = ", ".join(str(n) for n in pages_without_id[:20])
        more = f" ... (+{len(pages_without_id) - 20})" if len(pages_without_id) > 20 else ""
        warnings.append(
            f"{len(pages_without_id)} หน้าไม่พบเลขออเดอร์ (อาจเป็นไฟล์สแกน) / "
            f"{len(pages_without_id)} page(s) had no readable order number "
            f"(a scanned/image PDF?): หน้า {shown}{more}"
        )

    def sort_key(p):
        from .core import PHASE_RANK
        grank, gkey = group_sort_key(p["group"], config)
        return (PHASE_RANK[p["phase"]], grank, gkey, p["idx"])

    sorted_pages = sorted(page_info, key=sort_key)

    phase_summary = phase_summary_lines(sorted_pages, config)
    picking_rows = build_picking_rows(sorted_pages, order_items, "order_sn")
    pdf_bytes = build_sorted_pdf_bytes(all_pages, sorted_pages)

    # Reordered xlsx (same columns + sheet name, just reordered rows).
    # Duplicate order_sn rows (overlapping exports pasted together) would make
    # the .loc[] lookup below return every copy for each matching page, so the
    # sheet silently gains rows. Keep the first occurrence of each order.
    osn_key = df["order_sn"].astype(str).str.strip()
    n_dupes = int(osn_key.duplicated().sum())
    if n_dupes:
        dupe_names = sorted(osn_key[osn_key.duplicated()].unique().tolist())
        warnings.append(
            f"พบออเดอร์ซ้ำ {n_dupes} แถวในไฟล์ Packing List (ใช้แถวแรก) / "
            f"{n_dupes} duplicate order row(s) in the packing list (kept the first of each): "
            + ", ".join(dupe_names[:10])
            + (" ..." if len(dupe_names) > 10 else "")
        )
        keep = ~osn_key.duplicated()
        df = df[keep].reset_index(drop=True)
        osn_key = osn_key[keep].reset_index(drop=True)

    df_by_osn = df.set_index(osn_key, drop=False)
    ordered_osns = [p["order_sn"] for p in sorted_pages if p["order_sn"] in df_by_osn.index]
    df_sorted = df_by_osn.loc[ordered_osns].reset_index(drop=True)

    unmatched = [p for p in sorted_pages if p["order_sn"] not in df_by_osn.index]
    if unmatched:
        warnings.append(
            f"{len(unmatched)} หน้า PDF ไม่พบแถวออเดอร์ที่ตรงกัน (เก็บไว้ใน PDF, ไม่รวมใน Excel) / "
            f"{len(unmatched)} PDF page(s) have no matching xlsx row (kept in PDF, dropped from xlsx): "
            + ", ".join(f"page {p['idx'] + 1} ({p['order_sn']!r})" for p in unmatched)
        )

    orders_buf = io.BytesIO()
    df_sorted.to_excel(orders_buf, sheet_name="orders", index=False)

    # จำนวนใบพัด summary
    line_items = summary_mod.load_line_items_shopee(df, config)
    summary_df = summary_mod.build_report(line_items, config, warnings)
    summary_bytes = summary_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    stamp = today_stamp()
    return SortResult(
        pdf_bytes=pdf_bytes,
        orders_bytes=orders_buf.getvalue(),
        orders_filename=f"Shopee_Orders_Sorted_{stamp}.xlsx",
        summary_df=summary_df,
        summary_bytes=summary_bytes,
        phase_summary=phase_summary,
        picking_rows=picking_rows,
        warnings=warnings,
        num_pages=num_pages,
        num_orders=len(df_sorted),
    )
