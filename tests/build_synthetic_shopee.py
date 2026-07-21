import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

from sorter.config import load_config
from sorter.shopee import sort_shopee
from sorter.exec_summary import build_exec_summary_pdf, build_title

FIX = Path(__file__).resolve().parent / "_output"
FIX.mkdir(exist_ok=True)
FIX = str(FIX)

# 5 orders:
#  ORDER-A  single item qty=1              -> Phase A, no highlight
#  ORDER-B  single item qty=3               -> Phase B, green
#  ORDER-C  two distinct items (mixed)       -> Phase C, yellow x2 rows
#  ORDER-E  single item, unmapped SKU        -> Phase A, "[XYZ999]" bracket label
#  ORDER-D  page present, no matching xlsx row (order_sn only in PDF) -> Phase D

rows = [
    {
        "order_sn": "ORDER-A",
        "product_info": "[1] เลขอ้างอิง SKU ผู้ขาย:FB1601N; ชื่อสินค้า:Fan Blade 16H; จำนวน: 1",
    },
    {
        "order_sn": "ORDER-B",
        "product_info": "[1] เลขอ้างอิง SKU ผู้ขาย:FB1601N; ชื่อสินค้า:Fan Blade 16H; จำนวน: 3",
    },
    {
        "order_sn": "ORDER-C",
        "product_info": (
            "[1] เลขอ้างอิง SKU ผู้ขาย:FB1601N; ชื่อสินค้า:Fan Blade 16H; จำนวน: 1"
            "[2] เลขอ้างอิง SKU ผู้ขาย:FB1801N; ชื่อสินค้า:Fan Blade 18H; จำนวน: 2"
        ),
    },
    {
        "order_sn": "ORDER-E",
        "product_info": "[1] เลขอ้างอิง SKU ผู้ขาย:XYZ999; ชื่อสินค้า:Unknown Widget; จำนวน: 1",
    },
]
df = pd.DataFrame(rows)
xlsx_buf = io.BytesIO()
df.to_excel(xlsx_buf, sheet_name="orders", index=False)
with open(f"{FIX}/synth_shopee_orders.xlsx", "wb") as f:
    f.write(xlsx_buf.getvalue())

# PDF: 5 pages, one per order above PLUS an extra "ORDER-D" page with no matching xlsx row.
page_order_sns = ["ORDER-A", "ORDER-B", "ORDER-C", "ORDER-E", "ORDER-D"]
pdf_buf = io.BytesIO()
c = canvas.Canvas(pdf_buf, pagesize=A4)
for sn in page_order_sns:
    c.drawString(100, 700, f"Shopee Order No. {sn}")
    c.showPage()
c.save()
with open(f"{FIX}/synth_shopee_labels.pdf", "wb") as f:
    f.write(pdf_buf.getvalue())

print("Synthetic fixture written.")

# --- run through sort_shopee + exec summary ---
config = load_config()
with open(f"{FIX}/synth_shopee_orders.xlsx", "rb") as xf, open(f"{FIX}/synth_shopee_labels.pdf", "rb") as pf:
    result = sort_shopee([xf], [pf], config)

print(f"\nnum_pages={result.num_pages} num_orders={result.num_orders}")
for line in result.phase_summary:
    print(" ", line)
print("warnings:")
for w in result.warnings:
    print("  WARN:", w)

print("\npicking_rows:")
for i, r in enumerate(result.picking_rows, 1):
    print(f"  {i}: {r}")

from collections import Counter
actual_counts = Counter(r["highlight"] for r in result.picking_rows)
print("\nhighlight counts:", dict(actual_counts))
# 6 rows total: ORDER-A(none) + ORDER-E(none) + ORDER-B(green) + ORDER-C x2(yellow) + ORDER-D(none)
assert len(result.picking_rows) == 6, f"expected 6 rows (Phase C explodes to 2), got {len(result.picking_rows)}"
assert actual_counts[None] == 3, f"expected 3 no-highlight rows (2x Phase A + 1x Phase D), got {actual_counts[None]}"
assert actual_counts["green"] == 1, f"expected 1 green row (Phase B), got {actual_counts['green']}"
assert actual_counts["yellow"] == 2, f"expected 2 yellow rows (Phase C exploded), got {actual_counts['yellow']}"
print("PASS: highlight assignment matches expected business rule")

title = build_title("Shopee", "TEST", 1)
pdf_bytes = build_exec_summary_pdf(result.picking_rows, result.summary_df, title)
with open(f"{FIX}/exec_summary_synthetic.pdf", "wb") as f:
    f.write(pdf_bytes)
print(f"\nWrote {FIX}/exec_summary_synthetic.pdf ({len(pdf_bytes)} bytes)")
