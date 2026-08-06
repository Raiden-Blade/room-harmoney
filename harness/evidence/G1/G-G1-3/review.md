# G-G1-3 テストの実質性レビュー（QA独立レビュー）

対象: `backend/tests/unit/test_recommender.py`, `test_routing.py`, `test_sample_data_integrity.py`
方法: 各テストを読み、(a) 何を注入し (b) 何を厳密に assert しているかを確認。
「assert True 相当」「戻り値の型だけ確認」「固定値をそのまま突き合わせるだけ」等のハリボテが無いか検査した。

## 推薦（test_recommender.py）

| # | テスト | 検証内容 | 実質性 |
|---|---|---|---|
| 1 | test_related_sorted_by_lift_descending | lift=3.0/1.0/2.0 の3件を注入し、related の product_id 順序が ["PB","PD","PC"]（=lift 降順）、かつ lift 値列も一致することを assert | 実質的。順序だけでなく数値も突合しており、実装のソートキーが機能していないと失敗する |
| 2 | test_high_lift_low_corate_is_prioritized_over_equal_lift | lift 同値(2.0)でも high_lift_low_corate=true 側が先頭に来る順序、かつ `score` が厳密に大きい(`>`)ことを assert | 実質的。lift だけでは同点になるケースを用意し、ブースト項が実際にスコアへ寄与していることを検証 |
3 | test_hybrid_weight_changes_ranking_order | 同一データに対し、デフォルト重みでは coordinate 適合ありの PG が上位、weights={"coordinate_weight":0.0} を渡すと順序が反転して PH が上位になることを assert | 実質的。weights 引数が実際にスコア計算へ反映されることを、順序反転という形で検証（固定値の突合ではない） |
| 4 | test_unknown_product_id_returns_empty_result_safely | 存在しない product_id で product_found=False かつ related/coordinates が空であることを assert | 実質的。例外を握りつぶすだけの実装ではなく、フラグと空リストの両方を検証 |
| 5 | test_no_related_co_purchase_returns_empty_related_list | 起点と無関係な co_purchase のみ注入し、product_found=True だが related=[] になることを assert | 実質的。「該当なし」の分岐が独立して機能していることを確認 |
| 6 | test_no_matching_coordinates_returns_empty_coordinates_list | 起点を含まないコーデのみ注入し coordinates=[] を assert | 実質的 |
| 7 | test_coordinates_only_include_ones_containing_origin_product | 3件のコーデ（起点含む2件・含まない1件）を注入し、返る coordinate_id の集合が起点含有の2件と完全一致することを assert | 実質的。フィルタ条件（起点商品を含むか）が正しく効いているかを集合比較で厳密に検証 |

ハリボテ（assert True 相当・値の固定化のみ）は検出されなかった。全テストが「入力データを変えれば期待結果も変わる」形になっており、実装のロジック（ソートキー、ブースト計算、フィルタ条件）が壊れれば確実に失敗する構造。

## 経路（test_routing.py）

| # | テスト | 検証内容 | 実質性 |
|---|---|---|---|
| 1 | test_shortest_path_picks_the_actual_shortest_route | 直結100の「わざと長い」ダミーエッジを用意し、遠回り(10+10+5+10=35)の方が選ばれることを node_ids と total_distance の両方で assert | 実質的。ダイクストラが正しく最短距離を選ぶかを、誤答（100直結）を選んだら失敗する構造で検証 |
| 2 | test_same_start_and_end_returns_zero_distance_single_point | 起点=終点で距離0・単一ノードを assert | 実質的（エッジケース） |
| 3 | test_multi_destination_route_proposes_nearest_neighbor_order | 入力順をわざと逆（[prod_x, sub]）にし、実際に近い sub が先に来ることを assert（貪欲法の検証） | 実質的。入力順をそのまま返すような偽実装では失敗する |
| 4 | test_different_floor_is_solved_via_stairs_connection | 2フロアにまたがる経路で floors=[1,2]、階段ノードを経由、total_distance=37.0（内訳を手計算しコメントで明記）を assert | 実質的。フロア間接続エッジが実際に使われているかを距離の数値一致で検証 |
| 5 | test_no_route_raises_route_not_found_error | 孤立ノードへの到達不能を RouteNotFoundError で検証 | 実質的 |
| 6 | test_unknown_node_id_raises_route_not_found_error | 未知ノードIDで例外 | 実質的 |
| 7 | test_multi_destination_route_reports_unreachable_destinations | 到達可能1件＋到達不能1件を混在させ、order と unreachable が正しく分離されることを assert | 実質的 |
| 8 | test_route_can_include_sub_passage_waypoint | サブ通路ノードへの経路で sub_passage_waypoints に1件のみ・type一致を assert | 実質的 |
| 9 | test_nearest_node_resolves_qr_or_product_coordinate_to_waypoint | 座標(32,1)から最近傍が f1_prod_x（座標(30,0)）になることを assert（f1_isolated(99,99)等の他候補もあり、距離計算が機能しないと失敗） | 実質的 |
| 10 | test_nearest_node_raises_when_no_candidate_on_floor | 存在しないフロアで例外 | 実質的 |

## サンプルデータ整合性（test_sample_data_integrity.py）

- 参照整合性（coordinates.product_ids ⊂ products, co_purchase.cat_mid ⊂ products.cat_mid）を実データに対して forループで全件検証（サンプリングではなく網羅的）。
- `test_co_purchase_has_intentional_high_lift_low_corate_pairs` は「flagged 群の lift が non-flagged 群の最大値より大きい」「flagged 群の support が non-flagged 群の最小値より小さい」ことを実データに対して assert しており、意図（5.1章の「伸びしろ」ペア）が実データに反映されているかを検証する実質的なテスト。
- `test_store_map_all_waypoints_are_connected_across_four_floors` は networkx の `node_connected_component` を使い、全ノード数と一致するかで連結性を検証（4フロアが実際に繋がっていないと失敗する）。
- 2件のスモークテスト（経路・推薦）は実データで例外が出ないことに加え、フロア横断（floors[0]==1, floors[-1]==4）や型（list であること）も確認しており、単なる「呼べればOK」以上の検証を含む。

## 結論
検査した24件の単体テストにハリボテ（assert True 相当、固定値のみの突合、型だけの確認）は見つからなかった。
いずれも「実装のロジックが壊れれば必ず失敗する」形になっている独立検証可能なテストと判断する。
