"""
Independent re-implementation of lift computation, entirely separate from
backend/batch/lift_batch.py, used only to cross-check data/co_purchase.json.
Does NOT import batch.lift_batch or any implementation code.
"""
import json
from pathlib import Path

DATA_DIR = Path(r"C:\Users\haseg\OneDrive\Documents\ニトリ制作物\room-harmony\data")

LIFT_THRESHOLD = 2.0
CORATE_THRESHOLD = 0.045

source = json.loads((DATA_DIR / "co_purchase_source.json").read_text(encoding="utf-8"))
output = json.loads((DATA_DIR / "co_purchase.json").read_text(encoding="utf-8"))

support = {e["cat_mid"]: e["support"] for e in source["category_support"]}

print("=== G-P2A-3: independent recompute of ALL pairs (support/confidence/lift) ===")
mismatches = []
for pair, out_row in zip(source["co_purchases"], output):
    a, b = pair["cat_mid_a"], pair["cat_mid_b"]
    co = pair["co_support"]
    sa, sb = support[a], support[b]
    my_support = round(co, 4)
    my_confidence = round(co / sa, 3)
    my_lift = round(co / (sa * sb), 2)
    my_corate = round(co, 4)
    my_flag = (my_lift >= LIFT_THRESHOLD) and (my_corate <= CORATE_THRESHOLD)

    ok = (
        out_row["cat_mid_a"] == a and out_row["cat_mid_b"] == b
        and out_row["support"] == my_support
        and out_row["confidence"] == my_confidence
        and out_row["lift"] == my_lift
        and out_row["co_purchase_rate"] == my_corate
        and out_row["high_lift_low_corate"] == my_flag
    )
    status = "OK" if ok else "MISMATCH"
    if not ok:
        mismatches.append((a, b, out_row, {
            "support": my_support, "confidence": my_confidence, "lift": my_lift,
            "co_purchase_rate": my_corate, "high_lift_low_corate": my_flag,
        }))
    print(f"{status}  {a} -> {b}: support={my_support} confidence={my_confidence} "
          f"lift={my_lift} corate={my_corate} flag={my_flag}  (file: support={out_row['support']} "
          f"confidence={out_row['confidence']} lift={out_row['lift']} corate={out_row['co_purchase_rate']} "
          f"flag={out_row['high_lift_low_corate']})")

print()
print(f"Total pairs checked: {len(output)}")
print(f"Mismatches: {len(mismatches)}")
if mismatches:
    print("MISMATCH DETAILS:")
    for m in mismatches:
        print(m)

print()
print("=== G-P2A-7: cat_mid reference integrity against products.json ===")
products = json.loads((DATA_DIR / "products.json").read_text(encoding="utf-8"))
cat_mids = {p["cat_mid"] for p in products}
missing = []
for row in output:
    if row["cat_mid_a"] not in cat_mids:
        missing.append(row["cat_mid_a"])
    if row["cat_mid_b"] not in cat_mids:
        missing.append(row["cat_mid_b"])
print(f"distinct cat_mid in products.json: {len(cat_mids)}")
print(f"missing cat_mid refs: {missing if missing else 'NONE'}")

print()
print("=== Manual hand-calc spot check (3 pairs, independently by hand) ===")
# Pair 1: リビングテーブル -> 照明
a, b = "リビングテーブル", "照明"
sa, sb = support[a], support[b]
co = [p["co_support"] for p in source["co_purchases"] if p["cat_mid_a"] == a and p["cat_mid_b"] == b][0]
print(f"{a}->{b}: support_A={sa}, support_B={sb}, co_support={co}")
print(f"  support = {co} = {round(co,4)}")
print(f"  confidence = {co}/{sa} = {co/sa} = {round(co/sa,3)}")
print(f"  lift = {co}/({sa}*{sb}) = {co/(sa*sb)} = {round(co/(sa*sb),2)}")

# Pair 2: デスク -> ラグ・カーペット (a high-lift-low-corate candidate)
a, b = "デスク", "ラグ・カーペット"
sa, sb = support[a], support[b]
co = [p["co_support"] for p in source["co_purchases"] if p["cat_mid_a"] == a and p["cat_mid_b"] == b][0]
print(f"{a}->{b}: support_A={sa}, support_B={sb}, co_support={co}")
print(f"  support = {round(co,4)}")
print(f"  confidence = {co}/{sa} = {round(co/sa,3)}")
print(f"  lift = {co}/({sa}*{sb}) = {round(co/(sa*sb),2)}")
print(f"  co_purchase_rate={round(co,4)} <= {CORATE_THRESHOLD}? {round(co,4) <= CORATE_THRESHOLD}; lift>= {LIFT_THRESHOLD}? {round(co/(sa*sb),2) >= LIFT_THRESHOLD}")

# Pair 3: 食器 -> カーテン (lift near boundary ~1.0, should be False)
a, b = "食器", "カーテン"
sa, sb = support[a], support[b]
co = [p["co_support"] for p in source["co_purchases"] if p["cat_mid_a"] == a and p["cat_mid_b"] == b][0]
print(f"{a}->{b}: support_A={sa}, support_B={sb}, co_support={co}")
print(f"  support = {round(co,4)}")
print(f"  confidence = {co}/{sa} = {round(co/sa,3)}")
print(f"  lift = {co}/({sa}*{sb}) = {co/(sa*sb)} = {round(co/(sa*sb),2)}")
