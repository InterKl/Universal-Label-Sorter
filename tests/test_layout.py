import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pypdf

from sorter.summary import build_report
from sorter.config import load_config
from sorter.exec_summary import build_exec_summary_pdf, build_title

FIX = Path(__file__).resolve().parent / "_output"
FIX.mkdir(exist_ok=True)
FIX = str(FIX)
config = load_config()

# small dummy summary_df, reused across all scenarios
line_items = pd.DataFrame([
    {"sku": "FB1601N", "qty": 1, "order_size": 1},
    {"sku": "FB1801N", "qty": 3, "order_size": 1},
    {"sku": "FB1601N", "qty": 1, "order_size": 2},
    {"sku": "FB1801N", "qty": 1, "order_size": 2},
])
warnings = []
summary_df = build_report(line_items, config, warnings)

LABELS = ["12H", "14H", "16H", "16HO", "16PP", "18H", "18PP", "18SH", "16M", "ตัวล็อคใบพัดลม", "ด้ามกระทะ"]

def make_rows(n, highlight_every=7):
    rows = []
    for i in range(n):
        h = None
        if highlight_every and (i + 1) % highlight_every == 0:
            h = "green" if (i // highlight_every) % 2 == 0 else "yellow"
        rows.append({"label": LABELS[i % len(LABELS)], "qty": 1 if h != "green" else 3, "highlight": h})
    return rows

scenarios = {
    "small_6": make_rows(6, highlight_every=3),
    "mid_130": make_rows(130),
    "large_170": make_rows(170),
}

for name, rows in scenarios.items():
    title = build_title("Shopee", "TEST", 1)
    pdf_bytes = build_exec_summary_pdf(rows, summary_df, title)
    out = f"{FIX}/layout_{name}.pdf"
    with open(out, "wb") as f:
        f.write(pdf_bytes)
    n_pages = len(pypdf.PdfReader(out).pages)
    print(f"{name}: {len(rows)} rows -> {n_pages} page(s), {len(pdf_bytes)} bytes -> {out}")
