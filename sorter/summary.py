"""จำนวนใบพัด (fan-blade / box quantity) summary — shared between the Shopee
and TikTok tabs. Transform logic (explode_y_to_lock, split, summarize) is
identical for both platforms; only the line-item loader differs.
"""
from __future__ import annotations

import re

import pandas as pd

from .config import Config


def explode_y_to_lock(items: pd.DataFrame) -> pd.DataFrame:
    """Rewrite FB...Y rows to FB...N and append a matching O01 lock row.

    Each Y variant (fan blade with cap) implies one extra ตัวล็อคใบพัดลม per
    qty, so the O01 row inherits the original qty and order_size.
    """
    out = items.copy()
    is_y = out["sku"].str.startswith("FB") & out["sku"].str.endswith("Y")

    lock_rows = out.loc[is_y].copy()
    lock_rows["sku"] = "O01"

    out.loc[is_y, "sku"] = out.loc[is_y, "sku"].str[:-1] + "N"
    return pd.concat([out, lock_rows], ignore_index=True)


def split_fanblade_vs_box(items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split into (needs-assembly, packable-as-box).

    A line needs assembly if its order had >=2 distinct items, or the qty is >=2.
    """
    needs_assembly = (items["order_size"] >= 2) | (items["qty"] >= 2)
    return items[needs_assembly].copy(), items[~needs_assembly].copy()


def summarize(items: pd.DataFrame, config: Config, warnings: list[str]) -> pd.DataFrame:
    """Map SKU -> readable label and sum qty per label.

    Appends a warning for any SKU that fails to map (so silent loss can't happen).
    """
    items = items.copy()
    items["label"] = items["sku"].str.strip().map(config.sku_map)

    unmapped = sorted(items.loc[items["label"].isna(), "sku"].unique().tolist())
    if unmapped:
        warnings.append(f"SKU ที่ไม่รู้จัก (ไม่รวมในสรุป) / Unmapped SKUs (excluded from summary): {unmapped}")

    return (
        items.dropna(subset=["label"])
        .groupby("label", as_index=False)["qty"]
        .sum()
        .sort_values("label")
        .reset_index(drop=True)
    )


def build_report(line_items: pd.DataFrame, config: Config, warnings: list[str]) -> pd.DataFrame:
    """Produce the side-by-side Total | กล่อง | ใบพัด summary from line items."""
    with_lock = explode_y_to_lock(line_items)
    fanblade_raw, box_raw = split_fanblade_vs_box(with_lock)

    total = summarize(with_lock, config, warnings)
    box = summarize(box_raw, config, warnings)
    fanblade = summarize(fanblade_raw, config, warnings)

    spacer = pd.DataFrame({"": [""] * max(len(total), len(box), len(fanblade), 1)})
    report = pd.concat(
        [total, spacer, box, spacer, fanblade],
        axis=1,
        keys=["Total", "_s1", "กล่อง", "_s2", "ใบพัด"],
    ).fillna("")
    report.columns = report.columns.droplevel(1)

    # Uneven group lengths force pandas to pad the shorter qty columns with
    # NaN before fillna(""), which upcasts those columns to float — turning
    # e.g. qty 1 into "1.0". Restore whole numbers to plain ints.
    report = report.map(lambda v: int(v) if isinstance(v, float) and v.is_integer() else v)
    return report


# ---------------------------------------------------------------------------
# Shopee line-item loader (parses product_info regex, mirrors sorter.shopee)
# ---------------------------------------------------------------------------
_PRODUCT_INFO_SPLIT_RE = re.compile(r"\[\d+\]\s*")
_SKU_RE = re.compile(r"เลขอ้างอิง SKU.*?:\s*([^;\s]+)")
_QTY_RE = re.compile(r"จำนวน:\s*(\d+)")
_NAME_RE = re.compile(r"ชื่อสินค้า:\s*([^;]+)")


def _parse_product_info(text, config: Config) -> list[tuple[str, int]]:
    if not isinstance(text, str):
        return []
    items = []
    for part in _PRODUCT_INFO_SPLIT_RE.split(text):
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


def load_line_items_shopee(df: pd.DataFrame, config: Config) -> pd.DataFrame:
    """order_sn/product_info dataframe -> one row per line item."""
    records = []
    for _, row in df.iterrows():
        order_sn = str(row.get("order_sn", "")).strip()
        items = _parse_product_info(row.get("product_info"), config)
        order_size = len(items)
        for sku, qty in items:
            records.append({
                "order_sn": order_sn,
                "sku": sku,
                "qty": qty,
                "order_size": order_size,
            })
    return pd.DataFrame(records, columns=["order_sn", "sku", "qty", "order_size"])


# ---------------------------------------------------------------------------
# TikTok line-item loader (Order ID / Seller SKU / Product Name / Quantity)
# ---------------------------------------------------------------------------
def _clean(v) -> str:
    return str(v or "").strip().strip("\t").strip()


def _infer_sku(seller_sku: str, product_name: str, config: Config) -> str:
    if seller_sku:
        return seller_sku
    for pattern, label in config.name_map:
        if pattern.search(product_name):
            return label
    return ""


def load_line_items_tiktok(df: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Order ID/Seller SKU/Product Name/Quantity dataframe -> one row per line item."""
    df = df.copy()
    df["order_id"] = df["Order ID"].map(_clean)
    order_size = df.groupby("order_id")["order_id"].transform("size")

    records = []
    for (_, row), osize in zip(df.iterrows(), order_size):
        order_id = row["order_id"]
        if not order_id:
            continue
        sku = _infer_sku(_clean(row.get("Seller SKU")), _clean(row.get("Product Name")), config)
        try:
            qty = int(float(_clean(row.get("Quantity")) or "1"))
        except ValueError:
            qty = 1
        records.append({
            "order_id": order_id,
            "sku": sku,
            "qty": qty,
            "order_size": int(osize),
        })
    return pd.DataFrame(records, columns=["order_id", "sku", "qty", "order_size"])
