"""Lazada order list processor.

Unlike Shopee/TikTok, there is no shipping-label PDF to reorder — Lazada
orders are handled as a plain row-reversal of the order list, plus the same
กล่อง/ใบพัด (box vs needs-assembly) summary used elsewhere in the app.

SKU translation is algorithmic, not a lookup table: Lazada's `sellerSku`
already encodes the product label directly as "<label>-<N>" (e.g. "16HO-3",
"18PP+จุก-1"), where the trailing "-N" is a price-tier/variant code that
doesn't identify the product. Confirmed against ~33 real examples from the
business owner with zero exceptions, including entries with no suffix at all
(e.g. "16M", "ด้ามกระทะ") which pass through unchanged. See
sorter/config.py's load_lazada_group_config() for the (much smaller) piece
that *is* configurable: the display order of groups.

Multi-quantity orders: Lazada's export has no quantity column, so a repeat
purchase of the same product within one order is assumed to appear as
multiple rows sharing the same orderNumber (same convention as the existing
TikTok CSV handling) — qty is derived by counting those repeats.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

from .config import Config
from .core import today_stamp
from .summary import split_fanblade_vs_box

_SUFFIX_RE = re.compile(r"-\d+$")
LOCK_LABEL = "ตัวล็อคใบพัดลม"
JUK_SUFFIX = "+จุก"


@dataclass
class LazadaResult:
    orders_bytes: bytes
    orders_filename: str
    summary_df: pd.DataFrame
    summary_bytes: bytes
    picking_rows: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    num_orders: int = 0
    num_rows: int = 0


def translate_lazada_sku(seller_sku) -> str:
    """'16HO-3' -> '16HO'; '16M' -> '16M' (no suffix to strip); blank -> '[UNKNOWN]'."""
    if pd.isna(seller_sku):
        return "[UNKNOWN]"
    s = str(seller_sku).strip()
    if not s:
        return "[UNKNOWN]"
    label = _SUFFIX_RE.sub("", s)
    return label if label else f"[{s}]"


def _explode_juk_to_lock(items: pd.DataFrame) -> pd.DataFrame:
    """Mirrors sorter.summary.explode_y_to_lock, but keyed off the already-
    translated label's "+จุก" suffix instead of a raw SKU's "Y" suffix — a
    "+จุก" (with cap) purchase implies one extra ตัวล็อคใบพัดลม per qty,
    regardless of which platform the order came from.
    """
    out = items.copy()
    is_juk = out["label"].str.endswith(JUK_SUFFIX)

    lock_rows = out.loc[is_juk].copy()
    lock_rows["label"] = LOCK_LABEL

    out.loc[is_juk, "label"] = out.loc[is_juk, "label"].str.replace(JUK_SUFFIX, "", regex=False)
    return pd.concat([out, lock_rows], ignore_index=True)


def _summarize(items: pd.DataFrame) -> pd.DataFrame:
    """Sum qty per label. No SKU->label mapping step needed here (unlike
    sorter.summary.summarize) — translation already happened in
    load_line_items_lazada(), so there's no possibility of an "unmapped SKU"
    the way there is for Shopee/TikTok's dict-based lookup.
    """
    return (
        items.groupby("label", as_index=False)["qty"]
        .sum()
        .sort_values("label")
        .reset_index(drop=True)
    )


def load_line_items_lazada(df: pd.DataFrame) -> pd.DataFrame:
    """orderNumber/sellerSku dataframe -> one row per distinct (order, label),
    with qty = how many raw rows shared that pair and order_size = how many
    *distinct* labels appear in that order (mirrors sorter.tiktok's order_size,
    but counts distinct products, not raw line count, so two rows of the same
    product register as qty=2 of one item, not two items).
    """
    raw = pd.DataFrame({
        "order_sn": df["orderNumber"].astype(str).str.strip(),
        "label": df["sellerSku"].map(translate_lazada_sku),
    })
    raw["order_size"] = raw.groupby("order_sn")["label"].transform("nunique")
    items = (
        raw.groupby(["order_sn", "label", "order_size"], as_index=False)
        .size()
        .rename(columns={"size": "qty"})
    )
    return items


def build_report_lazada(items: pd.DataFrame) -> pd.DataFrame:
    """Same Total | กล่อง | ใบพัด layout as sorter.summary.build_report,
    positionally compatible with exec_summary._extract_group_tables().
    """
    with_lock = _explode_juk_to_lock(items)
    needs_assembly, box = split_fanblade_vs_box(with_lock)

    total = _summarize(with_lock)
    box_s = _summarize(box)
    fanblade_s = _summarize(needs_assembly)

    spacer = pd.DataFrame({"": [""] * max(len(total), len(box_s), len(fanblade_s), 1)})
    report = pd.concat(
        [total, spacer, box_s, spacer, fanblade_s],
        axis=1,
        keys=["Total", "_s1", "กล่อง", "_s2", "ใบพัด"],
    ).fillna("")
    report.columns = report.columns.droplevel(1)

    # Same float-upcast fix as sorter.summary.build_report (uneven group
    # lengths pad the shorter qty columns with NaN, forcing 1 -> 1.0).
    report = report.map(lambda v: int(v) if isinstance(v, float) and v.is_integer() else v)
    return report


def build_picking_rows_lazada(df_reversed: pd.DataFrame) -> list[dict]:
    """Order list for the สรุปรวม PDF: one output row per raw xlsx row, in the
    same (reversed) order, with sellerSku translated to a readable label.

    NO row alteration — the list mirrors the spreadsheet line-for-line:
      - no collapsing/summing (4 rows of "16HO+จุก" stay 4 rows of "16HO+จุก")
      - no +จุก -> ตัวล็อคใบพัดลม lock line (the raw "+จุก" label shows as-is)

    Highlighting IS kept, as a picking aid (it colours cells, it never adds,
    removes, or merges rows). Same rule as sorter.core.build_picking_rows:
      no highlight -> order has a single distinct product on a single row
      green        -> order has a single distinct product across >=2 rows
                      (every one of those rows is green)
      yellow       -> mixed order (>=2 distinct products): the order's first
                      row marks its "#" cell, every later row marks its "qty"
                      cell — a visual bracket grouping the order's lines

    The Total/กล่อง/ใบพัด summary tables below are the only place counting and
    +จุก lock accounting happen.
    """
    order_sn_col = df_reversed["orderNumber"].astype(str).str.strip()
    label_col = df_reversed["sellerSku"].map(translate_lazada_sku)

    tmp = pd.DataFrame({"order_sn": order_sn_col, "label": label_col})
    order_size_map = tmp.groupby("order_sn")["label"].nunique().to_dict()
    order_rowcount_map = tmp.groupby("order_sn").size().to_dict()

    rows: list[dict] = []
    emitted_per_order: dict[str, int] = {}

    for order_sn, label in zip(order_sn_col, label_col):
        is_mixed = order_size_map[order_sn] >= 2
        is_green = (not is_mixed) and order_rowcount_map[order_sn] >= 2

        if is_mixed:
            n = emitted_per_order.get(order_sn, 0)
            emitted_per_order[order_sn] = n + 1
            highlight, highlight_cell = "yellow", ("num" if n == 0 else "qty")
        elif is_green:
            highlight, highlight_cell = "green", None
        else:
            highlight, highlight_cell = None, None
        rows.append({"order_sn": order_sn, "label": label, "qty": 1, "highlight": highlight, "highlight_cell": highlight_cell})

    return rows


def sort_lazada(xlsx_files: list, _config: Config) -> LazadaResult:
    """xlsx_files: file-like objects (Streamlit UploadedFile or path).
    `_config` is accepted for call-site symmetry with sort_shopee/sort_tiktok
    but unused — Lazada's group ordering is loaded internally via
    config.load_lazada_group_config() at PDF-build time, not needed here.
    """
    warnings: list[str] = []

    frames = [pd.read_excel(f, sheet_name=0) for f in xlsx_files]
    df = pd.concat(frames, ignore_index=True)

    required = {"orderNumber", "sellerSku"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"ไฟล์ไม่มีคอลัมน์ที่จำเป็น: {', '.join(sorted(missing))} / "
            f"File is missing required column(s): {', '.join(sorted(missing))}"
        )

    blank_sku = df["sellerSku"].isna() | (df["sellerSku"].astype(str).str.strip() == "")
    if blank_sku.any():
        warnings.append(
            f"{int(blank_sku.sum())} แถวไม่มี sellerSku (นับเป็น [UNKNOWN]) / "
            f"{int(blank_sku.sum())} row(s) had no sellerSku (counted as [UNKNOWN])"
        )

    items = load_line_items_lazada(df)
    summary_df = build_report_lazada(items)
    summary_bytes = summary_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    # The actual request: reverse row order, top-to-bottom becomes
    # bottom-to-top. Order doesn't affect the summary above, so this can
    # happen independently, after the counts are already computed.
    df_reversed = df.iloc[::-1].reset_index(drop=True)
    orders_buf = io.BytesIO()
    df_reversed.to_excel(orders_buf, index=False)

    picking_rows = build_picking_rows_lazada(df_reversed)

    stamp = today_stamp()
    return LazadaResult(
        orders_bytes=orders_buf.getvalue(),
        orders_filename=f"Lazada_Orders_Reversed_{stamp}.xlsx",
        summary_df=summary_df,
        summary_bytes=summary_bytes,
        picking_rows=picking_rows,
        warnings=warnings,
        num_orders=int(df_reversed["orderNumber"].nunique()),
        num_rows=len(df_reversed),
    )
