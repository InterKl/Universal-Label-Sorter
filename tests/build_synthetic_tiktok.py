import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

from sorter.config import load_config
from sorter.tiktok import sort_tiktok
from sorter.exec_summary import build_exec_summary_pdf, build_title

FIX = Path(__file__).resolve().parent / "_output"
FIX.mkdir(exist_ok=True)
FIX = str(FIX)

# CSV: 4 orders.
#   1001  single line, qty=1          -> Phase A
#   1002  single line, qty=4          -> Phase B (green)
#   1003  TWO lines (mixed)            -> Phase C (yellow x2), and TikTok prints
#         2 PHYSICAL PAGES for this one order (one per line item) - this is
#         the case the seen_mixed dedup guard exists for.
#   (order 1004 in the PDF only, no CSV row -> Phase D)

csv_rows = [
    {"Order ID": "1001", "Seller SKU": "FB1601N", "Product Name": "Fan Blade 16H", "Quantity": "1"},
    {"Order ID": "1002", "Seller SKU": "FB1601N", "Product Name": "Fan Blade 16H", "Quantity": "4"},
    {"Order ID": "1003", "Seller SKU": "FB1601N", "Product Name": "Fan Blade 16H", "Quantity": "1"},
    {"Order ID": "1003", "Seller SKU": "FB1801N", "Product Name": "Fan Blade 18H", "Quantity": "2"},
]
df = pd.DataFrame(csv_rows)
csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
with open(f"{FIX}/synth_tiktok_orders.csv", "wb") as f:
    f.write(csv_bytes)

# PDF: 5 pages -> order 1001 (1pg), 1002 (1pg), 1003 (2pg, one per line item), 1004 (1pg, unmatched)
page_order_ids = ["1001", "1002", "1003", "1003", "1004"]
pdf_buf = io.BytesIO()
c = canvas.Canvas(pdf_buf, pagesize=A4)
for oid in page_order_ids:
    c.drawString(100, 700, f"Order ID: {oid}")
    c.showPage()
c.save()
with open(f"{FIX}/synth_tiktok_labels.pdf", "wb") as f:
    f.write(pdf_buf.getvalue())

print("Synthetic TikTok fixture written.")

config = load_config()
with open(f"{FIX}/synth_tiktok_orders.csv", "rb") as cf, open(f"{FIX}/synth_tiktok_labels.pdf", "rb") as pf:
    result = sort_tiktok([cf], [pf], config)

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
counts = Counter(r["highlight"] for r in result.picking_rows)
print("\nhighlight counts:", dict(counts))

# 5 physical pages total: 1001(1) + 1002(1) + 1003(2 pages -> deduped to
# exactly 2 rows, not 4) + 1004(1) = 5 picking rows.
assert len(result.picking_rows) == 5, (
    f"expected 5 picking rows (1001 + 1002 + 1003x2-deduped + 1004), got {len(result.picking_rows)}"
)
assert counts[None] == 2, f"expected 2 no-highlight rows (1001 Phase A + 1004 Phase D), got {counts[None]}"
assert counts["green"] == 1, f"expected 1 green row (1002 Phase B), got {counts['green']}"
assert counts["yellow"] == 2, f"expected 2 yellow rows (1003 Phase C, deduped not doubled), got {counts['yellow']}"
print("\nPASS: TikTok multi-page mixed-order dedup works correctly")

title = build_title("TikTok", "TEST", 1)
pdf_bytes = build_exec_summary_pdf(result.picking_rows, result.summary_df, title)
with open(f"{FIX}/exec_summary_tiktok_synthetic.pdf", "wb") as f:
    f.write(pdf_bytes)
print(f"Wrote exec_summary_tiktok_synthetic.pdf ({len(pdf_bytes)} bytes)")
