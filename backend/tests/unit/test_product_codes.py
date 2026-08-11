"""商品番号採番バッチ（`backend/batch/product_codes.py`）の単体テスト。G1ゲート。

重点観点（新機能「商品番号による直接遷移」実装指示より）:
  (1) コード形式（"LL-MM-SS-NNNN"、合計10桁のハイフン区切り。段階B1で個別番号を
      3桁→4桁へ拡張。実データで中分類あたり1,000件超のカテゴリに対応するため）
  (2) 階層採番（大分類/中分類/小分類ごとに名称ソートで安定採番されること）
  (3) 全商品ユニーク
  (4) 決定的/再現性（同一入力→同一出力。商品の並び順を変えても採番結果は不変）
  (5) ハイフン正規化（`repositories.normalize_product_code`）
  (6) QRマスタ（商品QR）への product_code 併記
  (7) 参照整合: 実データ（data/products.json）で run() が矛盾なく動作する
"""
from __future__ import annotations

import json
import re

import pytest

from app.repositories import normalize_product_code
from batch.product_codes import assign_codes, attach_codes_to_qr_codes, run

from tests.fixtures import DATA_DIR as FIXTURES_DATA_DIR

CODE_RE = re.compile(r"^\d{2}-\d{2}-\d{2}-\d{4}$")


def _product(
    product_id: str,
    cat_large: str,
    cat_mid: str,
    cat_small: str,
    **extra,
) -> dict:
    base = {
        "product_id": product_id,
        "name": f"商品{product_id}",
        "cat_large": cat_large,
        "cat_mid": cat_mid,
        "cat_small": cat_small,
        "color": "ホワイト",
        "price": 1000,
        "image_url": "https://example.com/x.png",
        "floor": 1,
        "zone": "A",
        "x": 1,
        "y": 1,
        "sub_passage_flag": False,
    }
    base.update(extra)
    return base


def test_code_format_is_ll_mm_ss_nnnn_10_digits():
    """(1) 生成される product_code は "LL-MM-SS-NNNN"（合計10桁）形式であること。"""
    products = [
        _product("P001", "リビング", "ソファ", "2人掛け"),
        _product("P002", "リビング", "ソファ", "3人掛け"),
        _product("P003", "寝室", "ベッド", "シングル"),
    ]

    result = assign_codes(products)

    for p in result:
        assert CODE_RE.match(p["product_code"]), p["product_code"]
        digits = p["product_code"].replace("-", "")
        assert len(digits) == 10


def test_hierarchical_numbering_is_stable_name_sorted():
    """(2) 大分類/中分類/小分類は名称ソートで 01 から安定採番される。

    大分類「あ分類」「か分類」は名称順で "あ" < "か" のため あ分類=01, か分類=02。
    中分類・小分類も同様にその親の中で名称ソート順に 01 から振られる。
    """
    products = [
        _product("P010", "か分類", "中2", "小1"),
        _product("P011", "あ分類", "中1", "小1"),
        _product("P012", "あ分類", "中1", "小2"),
    ]

    result = assign_codes(products)
    by_id = {p["product_id"]: p for p in result}

    # "あ分類" が名称順で先 -> LL=01。"か分類" -> LL=02。
    assert by_id["P011"]["product_code"].startswith("01-")
    assert by_id["P012"]["product_code"].startswith("01-")
    assert by_id["P010"]["product_code"].startswith("02-")

    # "あ分類" 配下は中分類が「中1」のみ -> MM=01。
    assert by_id["P011"]["product_code"].split("-")[1] == "01"
    # 「中1」配下は小分類が 小1, 小2 の2つ -> 名称順で 小1=01, 小2=02。
    assert by_id["P011"]["product_code"].split("-")[2] == "01"
    assert by_id["P012"]["product_code"].split("-")[2] == "02"


def test_individual_number_increments_within_smallest_bucket():
    """(2) 個別番号(NNNN)は同一小分類内で product_id 昇順に 0001, 0002, ... と振られる。"""
    products = [
        _product("P003", "リビング", "ソファ", "2人掛け"),
        _product("P001", "リビング", "ソファ", "2人掛け"),
        _product("P002", "リビング", "ソファ", "2人掛け"),
    ]

    result = assign_codes(products)
    by_id = {p["product_id"]: p for p in result}

    assert by_id["P001"]["product_code"].split("-")[3] == "0001"
    assert by_id["P002"]["product_code"].split("-")[3] == "0002"
    assert by_id["P003"]["product_code"].split("-")[3] == "0003"


def test_all_codes_are_unique_across_products():
    """(3) 全商品でproduct_codeがユニークであること（同名の小分類が複数の大分類に
    存在する意地悪ケースでも、上位階層の桁が異なるため衝突しないこと）。"""
    products = [
        _product("P001", "リビング", "収納", "ボックス"),
        _product("P002", "寝室", "収納", "ボックス"),  # 同名の中分類・小分類だが大分類が異なる
        _product("P003", "リビング", "ソファ", "2人掛け"),
        _product("P004", "寝室", "ベッド", "シングル"),
        _product("P005", "寝室", "ベッド", "シングル"),
    ]

    result = assign_codes(products)
    codes = [p["product_code"] for p in result]

    assert len(codes) == len(set(codes))


def test_deterministic_regardless_of_input_order():
    """(4) 商品の並び順を変えても、各 product_id に対する採番結果は変わらない（決定的）。"""
    products = [
        _product("P001", "リビング", "ソファ", "2人掛け"),
        _product("P002", "リビング", "ソファ", "3人掛け"),
        _product("P003", "寝室", "ベッド", "シングル"),
    ]
    shuffled = [products[2], products[0], products[1]]

    result_a = {p["product_id"]: p["product_code"] for p in assign_codes(products)}
    result_b = {p["product_id"]: p["product_code"] for p in assign_codes(shuffled)}

    assert result_a == result_b


def test_reproducible_same_input_yields_byte_identical_output():
    """(4) 同一入力を2回採番しても、バイト単位で同一の出力になること（再現性）。"""
    products = [
        _product("P001", "リビング", "ソファ", "2人掛け"),
        _product("P002", "寝室", "ベッド", "シングル"),
    ]

    result_1 = assign_codes(products)
    result_2 = assign_codes(products)

    assert result_1 == result_2
    assert json.dumps(result_1, ensure_ascii=False) == json.dumps(result_2, ensure_ascii=False)


def test_assign_codes_preserves_input_order_and_existing_fields():
    """付与後も入力の並び順・既存フィールドは変更されないこと。"""
    products = [
        _product("P002", "リビング", "ソファ", "3人掛け", price=59900),
        _product("P001", "リビング", "ソファ", "2人掛け", price=39900),
    ]

    result = assign_codes(products)

    assert [p["product_id"] for p in result] == ["P002", "P001"]
    assert result[0]["price"] == 59900
    assert result[1]["price"] == 39900
    assert "product_code" in result[0] and "product_code" in result[1]


def test_normalize_product_code_treats_hyphenated_and_plain_as_equal():
    """(5) ハイフン有無どちらの入力表現も同一の正規化結果になること（4桁個別番号）。"""
    assert normalize_product_code("01-03-02-0001") == normalize_product_code("0103020001")
    assert normalize_product_code("01-03-02-0001") == "0103020001"
    # 前後の空白等が混じっても数字以外は除去される。
    assert normalize_product_code(" 01-03-02-0001 ") == "0103020001"


def test_attach_codes_to_qr_codes_only_updates_product_type_entries():
    """(6) QRマスタの商品QR（type=="product"）にのみ product_code を併記し、
    入口QR等はそのままにすること。"""
    products_with_codes = assign_codes(
        [_product("P001", "リビング", "ソファ", "2人掛け")]
    )
    qr_codes = [
        {
            "qr_id": "QR-ENTRANCE-001",
            "type": "entrance",
            "product_id": None,
            "floor": 1,
            "x": 3,
            "y": 50,
            "direct_url": "https://example.com/r/QR-ENTRANCE-001",
        },
        {
            "qr_id": "QR-PRODUCT-P001",
            "type": "product",
            "product_id": "P001",
            "floor": 1,
            "x": 1,
            "y": 1,
            "direct_url": "https://example.com/r/QR-PRODUCT-P001",
        },
    ]

    result = attach_codes_to_qr_codes(qr_codes, products_with_codes)
    by_id = {q["qr_id"]: q for q in result}

    assert "product_code" not in by_id["QR-ENTRANCE-001"]
    assert by_id["QR-PRODUCT-P001"]["product_code"] == products_with_codes[0]["product_code"]


def test_run_on_real_sample_data_produces_unique_codes_and_matches_qr_master(tmp_path):
    """(7) サンプルデータ（段階A: 固定フィクスチャ）で run() を隔離ディレクトリに対して
    実行し、件数・ユニーク性・QRマスタとの整合を確認する（本番 data/ は書き換えない。
    フィクスチャを使うことで data/ の実データ差し替えでこのテストが壊れないようにする）。"""
    for filename in ("products.json", "qr_codes.json"):
        (tmp_path / filename).write_text(
            (FIXTURES_DATA_DIR / filename).read_text(encoding="utf-8"), encoding="utf-8"
        )

    summary = run(data_dir=tmp_path)

    products = json.loads((tmp_path / "products.json").read_text(encoding="utf-8"))
    qr_codes = json.loads((tmp_path / "qr_codes.json").read_text(encoding="utf-8"))

    assert summary["products"] == len(products)
    codes = [p["product_code"] for p in products]
    assert len(codes) == len(set(codes))
    for code in codes:
        assert CODE_RE.match(code)

    product_qrs = [q for q in qr_codes if q.get("type") == "product"]
    assert summary["product_qr_codes"] == len(product_qrs)
    code_by_product_id = {p["product_id"]: p["product_code"] for p in products}
    for qr in product_qrs:
        assert qr["product_code"] == code_by_product_id[qr["product_id"]]


def test_run_is_reproducible_on_real_sample_data(tmp_path):
    """(4)(7) サンプルデータ（段階A: 固定フィクスチャ）に対しても、run() を2回実行すれば
    バイト単位で同一出力になること。"""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    for target in (dir_a, dir_b):
        for filename in ("products.json", "qr_codes.json"):
            (target / filename).write_text(
                (FIXTURES_DATA_DIR / filename).read_text(encoding="utf-8"), encoding="utf-8"
            )

    run(data_dir=dir_a)
    run(data_dir=dir_b)

    assert (dir_a / "products.json").read_text(encoding="utf-8") == (
        dir_b / "products.json"
    ).read_text(encoding="utf-8")
    assert (dir_a / "qr_codes.json").read_text(encoding="utf-8") == (
        dir_b / "qr_codes.json"
    ).read_text(encoding="utf-8")


def test_missing_category_field_raises_clear_error():
    """商品が cat_large 等を欠く場合はサイレントに無視せず例外を送出すること。"""
    products = [{"product_id": "P001"}]

    with pytest.raises(KeyError):
        assign_codes(products)


def test_seq_digits_supports_over_1000_products_in_single_bucket():
    """段階B1: 個別番号(NNNN)が4桁化され、同一小分類に1,000件を超える商品があっても
    (実データのカーテン等、約2,600件を想定) 4桁ゼロ詰めでユニークに採番できること。"""
    products = [
        _product(f"P{i:05d}", "ファブリック", "カーテン", "カーテン")
        for i in range(1200)
    ]

    result = assign_codes(products)

    codes = [p["product_code"] for p in result]
    assert len(codes) == len(set(codes))
    seqs = sorted(int(code.split("-")[3]) for code in codes)
    assert seqs == list(range(1, 1201))
    # 1000件目以降も4桁のままゼロ埋めなし（桁あふれしていない）ことを確認。
    assert any(code.endswith("-1200") for code in codes)


def test_seq_digits_overflow_raises_clear_error():
    """個別番号の上限（9999）を超える場合はサイレントに無視せず例外を送出すること。"""
    products = [
        _product(f"P{i:05d}", "ファブリック", "カーテン", "カーテン")
        for i in range(10000)
    ]

    with pytest.raises(ValueError):
        assign_codes(products)
