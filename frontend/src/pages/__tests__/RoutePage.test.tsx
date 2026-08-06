import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock, route } from "../../test/mockFetch";
import { saveSession } from "../../state/session";
import { RoutePage } from "../RoutePage";

const STORE_MAP_FLOOR_1 = {
  floor: 1,
  floorplan: {
    type: "zones_rect",
    width: 100,
    height: 100,
    zones_rect: [
      { zone: "A", x: 5, y: 5, w: 35, h: 35 },
      { zone: "SUB", x: 85, y: 70, w: 14, h: 28 },
    ],
  },
  zones: [{ zone: "A", floor: 1, x: 20, y: 20 }],
  waypoints: [
    { id: "f1_c1", floor: 1, x: 10, y: 50, type: "通路" },
    { id: "f1_entrance", floor: 1, x: 3, y: 50, type: "入口" },
  ],
  edges: [{ from: "f1_c1", to: "f1_entrance", distance: 7 }],
  sub_passages: [{ waypoint_id: "f1_subpassage", floor: 1, note: "関連商品集積" }],
};

function product(id: string, name: string, x: number, y: number) {
  return {
    product_id: id,
    name,
    cat_large: "リビング",
    cat_mid: "ソファ",
    cat_small: "2人掛けソファ",
    color: "ナチュラル",
    price: 39900,
    image_url: "https://dummyimage.com/300x300",
    floor: 1,
    zone: "A",
    x,
    y,
    sub_passage_flag: false,
  };
}

function renderRoutePage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/route" element={<RoutePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RoutePage (S4)", () => {
  it("route の waypoint からSVGにルート線・起点・目的地・サブ通路ピンが描画される（複数目的地の巡回順）", async () => {
    saveSession({
      sessionId: "sess-active",
      experimentGroup: "A",
      qrId: "QR-ENTRANCE-001",
      start: { floor: 1, x: 3, y: 50 },
    });

    installFetchMock([
      route("GET", "/api/route", () => ({
        body: {
          waypoints: [
            { floor: 1, x: 3, y: 50, type: "入口" },
            { floor: 1, x: 10, y: 50, type: "通路" },
            { floor: 1, x: 85, y: 84, type: "サブ通路" },
            { floor: 1, x: 17, y: 18, type: "商品近傍" },
            { floor: 1, x: 24, y: 23, type: "商品近傍" },
          ],
          sub_passages: [{ floor: 1, x: 85, y: 84 }],
          visiting_order: ["P001", "P002"],
          unreachable: [],
          total_distance: 123.4,
        },
      })),
      route("GET", "/api/store-map/1", () => ({ body: STORE_MAP_FLOOR_1 })),
      route("GET", "/api/products/P001", () => ({ body: product("P001", "ナチュラルソファ", 17, 18) })),
      route("GET", "/api/products/P002", () => ({ body: product("P002", "ブラックソファ", 24, 23) })),
    ]);

    renderRoutePage("/route?to_product=P001&to_product=P002");

    const svg = await screen.findByTestId("floor-map-svg");
    expect(svg).toBeInTheDocument();

    // ルート線（起点→目的商品）が描画される。
    expect(await screen.findByTestId("route-line")).toBeInTheDocument();
    // 起点ピン。
    expect(screen.getByTestId("route-start")).toBeInTheDocument();
    // 目的地ピン（2箇所）。
    expect(screen.getByTestId("route-destination-P001")).toBeInTheDocument();
    expect(screen.getByTestId("route-destination-P002")).toBeInTheDocument();
    // 経由サブ通路ピン。
    expect(screen.getAllByTestId("route-subpassage").length).toBeGreaterThanOrEqual(1);

    // 巡回順（visiting_order）通りに表示される。
    const visitingOrder = screen.getByTestId("visiting-order");
    const orderedItems = visitingOrder.querySelectorAll("li");
    expect(orderedItems[0]).toHaveTextContent("1. ナチュラルソファ");
    expect(orderedItems[1]).toHaveTextContent("2. ブラックソファ");
  });

  it("有効なセッションが無い場合は来店ロックUIになり、routeAPIは呼ばれない（AC-5）", async () => {
    const { fetchMock } = installFetchMock([]);

    renderRoutePage("/route?to_product=P001");

    expect(await screen.findByTestId("visit-lock")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
