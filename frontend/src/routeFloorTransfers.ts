/**
 * 跨フロア経路の乗換情報の算出（4.3章 複数フロア・フェーズ2-C）。
 *
 * `GET /api/route` の `waypoints` は全フロアを連結した1本の列で返る（各要素は `floor` を持つ）。
 * 連続する2要素の `floor` が異なる箇所＝フロア間接続（階段/EV）を通過した箇所であり、
 * その直前のウェイポイントの `type`（"階段" or "EV"）が乗換手段を表す
 * （`backend/routing/graph.py` の `inter_floor_edges` は階段/EVノード同士を直結するため、
 * フロアが変わる境界のウェイポイントは常に階段/EVノードになる）。
 *
 * UIから独立した純粋関数にして単体テストしやすくしている（`RoutePage`/`FloorMap` から利用）。
 */

export interface FloorTransferSource {
  floor: number;
  type: string;
}

export interface FloorTransfer {
  fromFloor: number;
  toFloor: number;
  /** 乗換手段（"階段" | "EV"）。データ上想定外の型が来た場合もそのまま表示用に返す。 */
  viaType: string;
}

export function computeFloorTransfers(waypoints: FloorTransferSource[]): FloorTransfer[] {
  const transfers: FloorTransfer[] = [];
  for (let i = 0; i < waypoints.length - 1; i += 1) {
    const current = waypoints[i];
    const next = waypoints[i + 1];
    if (current.floor !== next.floor) {
      transfers.push({ fromFloor: current.floor, toFloor: next.floor, viaType: current.type });
    }
  }
  return transfers;
}
