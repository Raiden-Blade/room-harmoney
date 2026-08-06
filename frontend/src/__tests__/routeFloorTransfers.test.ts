import { describe, expect, it } from "vitest";

import { computeFloorTransfers } from "../routeFloorTransfers";

/**
 * 跨フロア経路の乗換情報算出（4.3章 複数フロア・フェーズ2-C）の単体テスト。
 */
describe("computeFloorTransfers", () => {
  it("単一フロアの経路では乗換なし（空配列）", () => {
    const transfers = computeFloorTransfers([
      { floor: 1, type: "入口" },
      { floor: 1, type: "通路" },
      { floor: 1, type: "商品近傍" },
    ]);
    expect(transfers).toEqual([]);
  });

  it("階段を経由してフロアが変わる箇所を乗換として検出する", () => {
    const transfers = computeFloorTransfers([
      { floor: 1, type: "入口" },
      { floor: 1, type: "階段" },
      { floor: 2, type: "階段" },
      { floor: 2, type: "商品近傍" },
    ]);
    expect(transfers).toEqual([{ fromFloor: 1, toFloor: 2, viaType: "階段" }]);
  });

  it("複数目的地で複数回フロアを跨ぐ場合はすべて検出する", () => {
    const transfers = computeFloorTransfers([
      { floor: 1, type: "入口" },
      { floor: 1, type: "EV" },
      { floor: 2, type: "EV" },
      { floor: 2, type: "商品近傍" },
      { floor: 2, type: "階段" },
      { floor: 3, type: "階段" },
      { floor: 3, type: "商品近傍" },
    ]);
    expect(transfers).toEqual([
      { fromFloor: 1, toFloor: 2, viaType: "EV" },
      { fromFloor: 2, toFloor: 3, viaType: "階段" },
    ]);
  });

  it("ウェイポイントが0件・1件でも例外を投げない", () => {
    expect(computeFloorTransfers([])).toEqual([]);
    expect(computeFloorTransfers([{ floor: 1, type: "入口" }])).toEqual([]);
  });
});
