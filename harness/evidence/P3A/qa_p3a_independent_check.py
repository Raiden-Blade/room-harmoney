"""QA独立検算スクリプト（G-P3A-4, G-P3A-5）。
実装のtestファイル（test_personalized.py / test_recommendations_personalized.py）は
一切import・再利用しない。実データ（data/products.json 等）を自前で読み、
HybridRecommender / PersonalizedRecommender を直接使って独立に検算する。
"""
import json
import sys
from pathlib import Path

REPO = Path(r"C:\Users\haseg\OneDrive\Documents\ニトリ制作物\room-harmony")
sys.path.insert(0, str(REPO / "backend"))

from recommender.hybrid import HybridRecommender
from recommender.personalized import PersonalizedRecommender

DATA_DIR = str(REPO / "data")

base = HybridRecommender.from_data_dir(data_dir=DATA_DIR)
personalized = PersonalizedRecommender.from_data_dir(data_dir=DATA_DIR)

products = json.loads((REPO / "data" / "products.json").read_text(encoding="utf-8"))
product_ids = [p["product_id"] for p in products]

print(f"=== G-P3A-4: 後方互換の独立検算（product数={len(product_ids)}） ===")
mismatches = []
for pid in product_ids:
    base_result = base.recommend(pid)
    base_order = [(it.product["product_id"], it.score) for it in base_result.related]

    for label, member_id in [
        ("member_idなし", None),
        ("未知member_id", "NO-SUCH-MEMBER-XYZ"),
        ("履歴空M003", "M003"),
    ]:
        if member_id is None:
            pr = personalized.recommend(pid)
        else:
            pr = personalized.recommend(pid, member_id=member_id)
        pr_order = [(it.product["product_id"], it.score) for it in pr.related]
        if (
            pr_order != base_order
            or pr.coordinates != base_result.coordinates
            or pr.product_found != base_result.product_found
        ):
            mismatches.append((pid, label, base_order, pr_order))

if mismatches:
    print(f"FAIL: {len(mismatches)} 件の不一致")
    for m in mismatches[:20]:
        print(m)
else:
    print(
        f"PASS: 全 {len(product_ids)} product_id x 3ケース"
        "(member_idなし/未知member_id/M003履歴空) で"
        " related順序・score・coordinates・product_found が base と完全一致"
    )

print()
print("=== G-P3A-5: アフィニティ効果の独立確認（M004、カーテン3回購入） ===")
member_history = json.loads((REPO / "data" / "member_history.json").read_text(encoding="utf-8"))
m004 = next(m for m in member_history["members"] if m["member_id"] == "M004")
print(f"M004 purchased (raw, 自前読み込み): {m004['purchased']}")

changed_products = []
for pid in product_ids:
    base_result = base.recommend(pid)
    if not base_result.related:
        continue
    base_order = [it.product["product_id"] for it in base_result.related]
    pr = personalized.recommend(pid, member_id="M004")
    pr_order = [it.product["product_id"] for it in pr.related]
    has_curtain = any(it.cat_mid == "カーテン" for it in base_result.related)
    if has_curtain and pr_order != base_order:
        for b_it, p_it in zip(
            sorted(base_result.related, key=lambda x: x.product["product_id"]),
            sorted(pr.related, key=lambda x: x.product["product_id"]),
        ):
            assert b_it.product["product_id"] == p_it.product["product_id"]
            if b_it.cat_mid == "カーテン":
                expected = b_it.score * (1 + 0.15 * 3)
                ok = abs(p_it.score - expected) < 1e-9
                changed_products.append(
                    (pid, b_it.product["product_id"], b_it.score, p_it.score, expected, ok)
                )

print(
    "カーテンを含むrelatedがあり、かつ並びが変化した product_id 数:",
    len(set(p[0] for p in changed_products)),
)
for row in changed_products:
    pid, curtain_pid, base_score, pers_score, expected, ok = row
    print(
        f"  product_id={pid} curtain_item={curtain_pid} base_score={base_score:.4f} "
        f"personalized_score={pers_score:.4f} expected(x1.45)={expected:.4f} match={ok}"
    )

if "P027" in product_ids:
    print()
    print("--- P027 詳細比較（結合テストで使われている例と同じ商品を自前で再現） ---")
    b = base.recommend("P027")
    p = personalized.recommend("P027", member_id="M004")
    print("base order :", [(it.product["product_id"], it.cat_mid, round(it.score, 4)) for it in b.related])
    print("pers order :", [(it.product["product_id"], it.cat_mid, round(it.score, 4)) for it in p.related])
    order_changed = [it.product["product_id"] for it in b.related] != [
        it.product["product_id"] for it in p.related
    ]
    print("順位変化:", order_changed)

all_ok = not mismatches and len(changed_products) > 0 and all(row[5] for row in changed_products)
print()
print("=== 総合 ===", "PASS" if all_ok else "FAIL")
sys.exit(0 if all_ok else 1)
