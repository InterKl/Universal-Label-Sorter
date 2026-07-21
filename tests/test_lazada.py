"""Lazada tests: SKU-strip translation (validated separately against the
real 32-entry mapping the business owner provided), row reversal, and the
กล่อง/ใบพัด split under conditions the one real sample file didn't cover
(multi-qty repeats, mixed orders, +จุก -> lock explosion).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io
import pandas as pd

from sorter.lazada import sort_lazada, translate_lazada_sku

FIX = Path(__file__).resolve().parent / "_output"
FIX.mkdir(exist_ok=True)

# ORDER-A  single item, qty=1                 -> total=1, กล่อง=1, ใบพัด=0
# ORDER-B  same item x3 (repeat rows)          -> qty=3   -> needs assembly
# ORDER-C  two distinct items (mixed order)    -> order_size=2 -> needs assembly (both)
# ORDER-D  a +จุก item, qty=1, single item     -> base label + a lock row, BOTH order_size=1/qty=1
rows = [
    {"orderNumber": "ORDER-A", "sellerSku": "16H-7"},
    {"orderNumber": "ORDER-B", "sellerSku": "16HO-3"},
    {"orderNumber": "ORDER-B", "sellerSku": "16HO-3"},
    {"orderNumber": "ORDER-B", "sellerSku": "16HO-3"},
    {"orderNumber": "ORDER-C", "sellerSku": "16M-5"},
    {"orderNumber": "ORDER-C", "sellerSku": "18M-3"},
    {"orderNumber": "ORDER-D", "sellerSku": "18PP+จุก-1"},
]
df = pd.DataFrame(rows)
buf = io.BytesIO()
df.to_excel(buf, index=False)
buf.seek(0)

result = sort_lazada([buf], None)

print(f"num_rows={result.num_rows} num_orders={result.num_orders}")
print(result.summary_df.to_string())
print()

# --- checks ---
def group_val(df, group_name, label):
    """Read one cell out of the Total|กล่อง|ใบพัด side-by-side layout."""
    idx = {"Total": 0, "กล่อง": 3, "ใบพัด": 6}[group_name]
    labels = df.iloc[:, idx].astype(str)
    qtys = df.iloc[:, idx + 1]
    match = labels == label
    if not match.any():
        return 0
    v = qtys[match].iloc[0]
    return int(v) if v != "" else 0

s = result.summary_df

assert group_val(s, "กล่อง", "16H") == 1, "ORDER-A (qty=1) should be in กล่อง"
assert group_val(s, "ใบพัด", "16H") == 0, "ORDER-A should NOT be in ใบพัด"
print("PASS: single item qty=1 -> กล่อง only")

assert group_val(s, "ใบพัด", "16HO") == 3, "ORDER-B (qty=3, repeat rows) should be in ใบพัด with qty=3"
assert group_val(s, "กล่อง", "16HO") == 0, "ORDER-B should NOT also be in กล่อง"
print("PASS: repeated rows (same order+label) -> qty=3, needs assembly")

assert group_val(s, "ใบพัด", "16M") == 1, "ORDER-C item 1 (mixed order) should be in ใบพัด"
assert group_val(s, "ใบพัด", "18M") == 1, "ORDER-C item 2 (mixed order) should be in ใบพัด"
print("PASS: mixed order (2 distinct items, same orderNumber) -> both need assembly")

assert group_val(s, "กล่อง", "18PP") == 1, "ORDER-D base label (18PP) should be in กล่อง (qty=1, order_size=1)"
assert group_val(s, "กล่อง", "ตัวล็อคใบพัดลม") == 1, "ORDER-D's +จุก should generate 1 lock, also in กล่อง"
print("PASS: +จุก item explodes into base label + ตัวล็อคใบพัดลม lock, both inherit order_size/qty")

assert translate_lazada_sku(None) == "[UNKNOWN]"
assert translate_lazada_sku("") == "[UNKNOWN]"
assert translate_lazada_sku(float("nan")) == "[UNKNOWN]"
print("PASS: blank/NaN sellerSku -> [UNKNOWN], never crashes")

# --- row reversal still correct with multiple distinct orders ---
reversed_df = pd.read_excel(io.BytesIO(result.orders_bytes))
assert reversed_df["orderNumber"].tolist() == df["orderNumber"].tolist()[::-1]
assert list(reversed_df.columns) == list(df.columns)
print("PASS: row reversal exact, columns preserved")

print("\nALL LAZADA TESTS PASS")
