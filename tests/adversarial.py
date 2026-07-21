"""Adversarial / real-user scenario tests against the sorter core.

Each scenario mimics something warehouse staff plausibly do or receive.
We record PASS (handled sensibly) vs BUG (crash / silent wrong output).
"""
import io
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

from sorter.config import load_config
from sorter.shopee import sort_shopee
from sorter.tiktok import sort_tiktok

config = load_config()
results = []


def rec(name, status, detail):
    results.append((name, status, detail))
    print(f"[{status}] {name}\n      {detail}\n")


def make_pdf(order_sns, prefix="Shopee Order No. "):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for sn in order_sns:
        if sn is not None:
            c.drawString(100, 700, f"{prefix}{sn}")
        else:
            c.drawString(100, 700, "(scanned image - no text)")
        c.showPage()
    c.save()
    buf.seek(0)
    return buf


def make_xlsx(rows):
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name="orders", index=False)
    buf.seek(0)
    return buf


def pinfo(sku, qty=1, name="Product"):
    return f"[1] เลขอ้างอิง SKU ผู้ขาย:{sku}; ชื่อสินค้า:{name}; จำนวน: {qty}"


# ---------------------------------------------------------------
# S1: duplicate order_sn in the packing list (Shopee re-exported /
#     staff pasted two overlapping exports into one file)
# ---------------------------------------------------------------
try:
    rows = [
        {"order_sn": "DUP-1", "product_info": pinfo("FB1601N", 1)},
        {"order_sn": "DUP-1", "product_info": pinfo("FB1601N", 1)},  # duplicate!
        {"order_sn": "UNIQ-2", "product_info": pinfo("FB1801N", 1)},
    ]
    x = make_xlsx(rows)
    p = make_pdf(["DUP-1", "UNIQ-2"])
    r = sort_shopee([x], [p], config)
    if r.num_orders != 2:
        rec("S1 duplicate order_sn in xlsx", "BUG",
            f"2 PDF pages -> orders sheet has {r.num_orders} rows (row explosion from .loc on duplicated index)")
    else:
        rec("S1 duplicate order_sn in xlsx", "PASS", f"orders rows={r.num_orders}")
except Exception as e:
    rec("S1 duplicate order_sn in xlsx", "BUG", f"CRASH {type(e).__name__}: {e}")

# ---------------------------------------------------------------
# S2: click "Sort" twice (Streamlit reruns, same file objects reused)
# ---------------------------------------------------------------
try:
    x = make_xlsx([{"order_sn": "A1", "product_info": pinfo("FB1601N")}])
    p = make_pdf(["A1"])
    sort_shopee([x], [p], config)
    r2 = sort_shopee([x], [p], config)  # same objects, second click
    rec("S2 sort clicked twice (same file objects)", "PASS", f"second run ok, pages={r2.num_pages}")
except Exception as e:
    rec("S2 sort clicked twice (same file objects)", "BUG",
        f"CRASH on 2nd run {type(e).__name__}: {e} (file pointer at EOF - needs seek(0))")

# ---------------------------------------------------------------
# S3: scanned/image-only label PDF (no extractable text)
# ---------------------------------------------------------------
try:
    x = make_xlsx([{"order_sn": f"S{i}", "product_info": pinfo("FB1601N")} for i in range(30)])
    p = make_pdf([None] * 30)
    r = sort_shopee([x], [p], config)
    n_warn = len(r.warnings)
    if n_warn > 12:
        rec("S3 scanned PDF, no text (30 pages)", "BUG",
            f"{n_warn} separate warnings -> UI floods with {n_warn} yellow boxes; should aggregate")
    else:
        rec("S3 scanned PDF, no text (30 pages)", "PASS", f"{n_warn} warnings")
except Exception as e:
    rec("S3 scanned PDF, no text", "BUG", f"CRASH {type(e).__name__}: {e}")

# ---------------------------------------------------------------
# S4: totally empty packing list (staff exported before orders synced)
# ---------------------------------------------------------------
try:
    x = make_xlsx([{"order_sn": "X", "product_info": "X"}])
    df = pd.read_excel(x, sheet_name="orders").iloc[0:0]
    buf = io.BytesIO(); df.to_excel(buf, sheet_name="orders", index=False); buf.seek(0)
    p = make_pdf(["GHOST-1"])
    r = sort_shopee([buf], [p], config)
    rec("S4 empty packing list", "PASS", f"handled; pages={r.num_pages}, warnings={len(r.warnings)}")
except Exception as e:
    rec("S4 empty packing list", "BUG", f"CRASH {type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")

# ---------------------------------------------------------------
# S5: xlsx missing the 'orders' sheet (staff saved a filtered copy)
# ---------------------------------------------------------------
try:
    buf = io.BytesIO()
    pd.DataFrame([{"order_sn": "A", "product_info": pinfo("FB1601N")}]).to_excel(
        buf, sheet_name="Sheet1", index=False)
    buf.seek(0)
    p = make_pdf(["A"])
    sort_shopee([buf], [p], config)
    rec("S5 xlsx without 'orders' sheet", "PASS", "unexpectedly succeeded")
except Exception as e:
    rec("S5 xlsx without 'orders' sheet", "PASS-ish",
        f"raises {type(e).__name__} -> app shows generic Thai error. Message not specific about sheet name.")

# ---------------------------------------------------------------
# S6: qty = 0  (cancelled line) and negative qty
# ---------------------------------------------------------------
try:
    rows = [
        {"order_sn": "Z0", "product_info": pinfo("FB1601N", 0)},
        {"order_sn": "ZN", "product_info": pinfo("FB1801N", 1)},
    ]
    x = make_xlsx(rows)
    p = make_pdf(["Z0", "ZN"])
    r = sort_shopee([x], [p], config)
    qtys = [pr["qty"] for pr in r.picking_rows]
    phases = [ln[:8] for ln in r.phase_summary]
    rec("S6 qty=0 line item", "INFO",
        f"qty=0 -> picking qtys {qtys}; phases {phases} (qty 0 falls to Phase B 'qty>=2' branch? check)")
except Exception as e:
    rec("S6 qty=0 line item", "BUG", f"CRASH {type(e).__name__}: {e}")

# ---------------------------------------------------------------
# S7: order_sn with stray whitespace / case difference between
#     PDF text and xlsx cell
# ---------------------------------------------------------------
try:
    x = make_xlsx([{"order_sn": "  WS-1  ", "product_info": pinfo("FB1601N")}])
    p = make_pdf(["WS-1"])
    r = sort_shopee([x], [p], config)
    ph = r.phase_summary[0] if r.phase_summary else ""
    if "UNKNOWN" in ph:
        rec("S7 whitespace in xlsx order_sn", "BUG", "whitespace prevents match -> Phase D")
    else:
        rec("S7 whitespace in xlsx order_sn", "PASS", f"matched: {ph}")
except Exception as e:
    rec("S7 whitespace in xlsx order_sn", "BUG", f"CRASH {type(e).__name__}: {e}")

# ---------------------------------------------------------------
# S8: TikTok CSV missing the 'Order ID' column (wrong export type)
# ---------------------------------------------------------------
try:
    df = pd.DataFrame([{"Order No": "1", "Seller SKU": "FB1601N", "Quantity": "1"}])
    cbuf = io.BytesIO(df.to_csv(index=False).encode("utf-8-sig"))
    p = make_pdf(["1"], prefix="Order ID: ")
    sort_tiktok([cbuf], [p], config)
    rec("S8 TikTok CSV missing 'Order ID'", "PASS", "unexpectedly succeeded")
except Exception as e:
    rec("S8 TikTok CSV missing 'Order ID'", "PASS-ish",
        f"raises {type(e).__name__}: {str(e)[:80]} -> generic Thai error shown")

# ---------------------------------------------------------------
# S9: Shopee packing list uploaded into the TikTok tab
#     (staff picks the wrong tab - very plausible)
# ---------------------------------------------------------------
try:
    x = make_xlsx([{"order_sn": "A", "product_info": pinfo("FB1601N")}])
    p = make_pdf(["A"], prefix="Order ID: ")
    sort_tiktok([x], [p], config)
    rec("S9 xlsx uploaded to TikTok tab", "BUG", "silently accepted an xlsx as CSV")
except Exception as e:
    rec("S9 xlsx uploaded to TikTok tab", "PASS",
        f"rejected with {type(e).__name__} -> generic error (note: file_uploader type= already blocks this in UI)")

# ---------------------------------------------------------------
# S10: same PDF uploaded twice into the 2-file slot (double print)
# ---------------------------------------------------------------
try:
    x = make_xlsx([{"order_sn": "D1", "product_info": pinfo("FB1601N")}])
    p1 = make_pdf(["D1"]); p2 = make_pdf(["D1"])
    r = sort_shopee([x], [p1, p2], config)
    rec("S10 same PDF twice (2 slots)", "INFO",
        f"pages={r.num_pages} picking_rows={len(r.picking_rows)} warnings={len(r.warnings)} "
        f"-> duplicates silently accepted; is that desired?")
except Exception as e:
    rec("S10 same PDF twice", "BUG", f"CRASH {type(e).__name__}: {e}")

# ---------------------------------------------------------------
# S11: huge qty (typo: 1000 instead of 10)
# ---------------------------------------------------------------
try:
    x = make_xlsx([{"order_sn": "H1", "product_info": pinfo("FB1601N", 1000)}])
    p = make_pdf(["H1"])
    r = sort_shopee([x], [p], config)
    rec("S11 qty=1000 typo", "PASS", f"picking qty={r.picking_rows[0]['qty']}, no crash")
except Exception as e:
    rec("S11 qty=1000 typo", "BUG", f"CRASH {type(e).__name__}: {e}")

# ---------------------------------------------------------------
# S12: mixed order with 5 distinct SKUs (highlight_cell pattern)
# ---------------------------------------------------------------
try:
    pi = "".join(
        f"[{i+1}] เลขอ้างอิง SKU ผู้ขาย:{sku}; ชื่อสินค้า:P; จำนวน: 1"
        for i, sku in enumerate(["FB1601N", "FB1801N", "FB1602N", "FB1401N", "FB1201N"])
    )
    x = make_xlsx([{"order_sn": "M5", "product_info": pi}])
    p = make_pdf(["M5"])
    r = sort_shopee([x], [p], config)
    cells = [pr.get("highlight_cell") for pr in r.picking_rows]
    expected = ["num", "qty", "qty", "qty", "qty"]
    if cells == expected:
        rec("S12 mixed order, 5 SKUs", "PASS", f"highlight_cell pattern {cells}")
    else:
        rec("S12 mixed order, 5 SKUs", "BUG", f"expected {expected}, got {cells}")
except Exception as e:
    rec("S12 mixed order, 5 SKUs", "BUG", f"CRASH {type(e).__name__}: {e}")

# ---------------------------------------------------------------
# S13: PDF has FEWER pages than xlsx has orders (partial print)
# ---------------------------------------------------------------
try:
    rows = [{"order_sn": f"P{i}", "product_info": pinfo("FB1601N")} for i in range(5)]
    x = make_xlsx(rows)
    p = make_pdf(["P0", "P1"])  # only 2 of 5 printed
    r = sort_shopee([x], [p], config)
    rec("S13 PDF fewer pages than orders", "PASS",
        f"pages={r.num_pages} orders_out={r.num_orders} warnings={len(r.warnings)} (count-mismatch warned)")
except Exception as e:
    rec("S13 PDF fewer pages than orders", "BUG", f"CRASH {type(e).__name__}: {e}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
for name, status, _ in results:
    print(f"  [{status:8}] {name}")
bugs = [r for r in results if r[1] == "BUG"]
print(f"\n{len(bugs)} BUG(s) found out of {len(results)} scenarios")
