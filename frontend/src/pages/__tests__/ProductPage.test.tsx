import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock, route } from "../../test/mockFetch";
import { saveSession } from "../../state/session";
import { ProductPage } from "../ProductPage";

const PRODUCT = {
  product_id: "P027",
  name: "食器セット",
  cat_large: "キッチン",
  cat_mid: "食器",
  cat_small: "食器セット",
  color: "ホワイト",
  price: 4900,
  image_url: "https://dummyimage.com/300x300&text=P027",
  floor: 2,
  zone: "C",
  x: 40,
  y: 20,
  sub_passage_flag: false,
};

function relatedProduct(id: string, name: string) {
  return {
    product_id: id,
    name,
    cat_large: "キッチン",
    cat_mid: "キッチン雑貨",
    cat_small: "小物",
    color: "ナチュラル",
    price: 1200,
    image_url: "https://dummyimage.com/80x80",
    floor: 2,
    zone: "C",
    x: 41,
    y: 21,
    sub_passage_flag: false,
  };
}

function renderProductPage(productId = "P027") {
  return render(
    <MemoryRouter initialEntries={[`/products/${productId}`]}>
      <Routes>
        <Route path="/products/:productId" element={<ProductPage />} />
        <Route path="/route" element={<div data-testid="mock-route-page">route page</div>} />
        <Route path="/coordinates/:coordinateId" element={<div data-testid="mock-coordinate-page">coordinate page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ProductPage (S2)", () => {
  it("有効なセッションがあれば関連商品がAPI順（リフト降順）のまま表示され、related_tapでルートへ遷移する", async () => {
    saveSession({
      sessionId: "sess-active",
      experimentGroup: "A",
      qrId: "QR-PRODUCT-P027",
      start: { floor: 1, x: 3, y: 50 },
    });

    const { calls } = installFetchMock([
      route("GET", "/api/products/P027", () => ({ body: PRODUCT })),
      route("GET", "/api/recommendations", () => ({
        body: {
          related: [
            {
              product: relatedProduct("P033", "キッチン雑貨セットA"),
              cat_mid: "キッチン雑貨",
              lift: 1.3,
              high_lift_low_corate: false,
              score: 1.3,
            },
            {
              product: relatedProduct("P034", "キッチン雑貨セットB"),
              cat_mid: "キッチン雑貨",
              lift: 1.1,
              high_lift_low_corate: false,
              score: 1.1,
            },
          ],
          coordinates: [
            {
              coordinate_id: "C009",
              name: "キッチン北欧コーデ",
              theme: "北欧",
              product_ids: ["P027", "P033"],
              image_url: "https://dummyimage.com/600x400",
              total_price_estimate: 12000,
            },
          ],
        },
      })),
      route("POST", "/api/events", () => ({ body: { ok: true } })),
    ]);

    renderProductPage();

    await screen.findByTestId("product-detail");
    expect(screen.getByText("食器セット")).toBeInTheDocument();

    const relatedList = await screen.findByTestId("related-list");
    const items = within(relatedList).getAllByRole("listitem");
    // バックエンドがリフト降順で返した順序をフロントがそのまま維持していること。
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("キッチン雑貨セットA")).toBeInTheDocument();
    expect(within(items[1]).getByText("キッチン雑貨セットB")).toBeInTheDocument();

    // コーディネートへのリンクが表示される。
    expect(screen.getByTestId("coordinate-link-C009")).toBeInTheDocument();

    // related_tap: 「場所を見る」タップでイベント送信＋S4遷移。
    fireEvent.click(screen.getByTestId("related-tap-P033"));

    await screen.findByTestId("mock-route-page");
    const eventCall = calls.find(
      (c) =>
        c.method === "POST" &&
        c.url.includes("/api/events") &&
        (c.body as { event_type?: string })?.event_type === "related_tap",
    );
    expect(eventCall).toBeDefined();
    const eventBody = eventCall!.body as { payload?: { to_product_id?: string } };
    expect(eventBody.payload?.to_product_id).toBe("P033");
  });

  it("有効なセッションが無い場合、関連商品セクションは来店ロックUIになる（AC-5）", async () => {
    installFetchMock([route("GET", "/api/products/P027", () => ({ body: PRODUCT }))]);

    renderProductPage();

    // 商品情報自体は表示される（中核機能ではないためロック対象外）。
    await screen.findByTestId("product-detail");
    // 関連商品は来店ロック。
    expect(await screen.findByTestId("visit-lock")).toBeInTheDocument();
  });

  it("APIが409（VISIT_LOCK_REQUIRED）を返した場合も同じ来店ロックUIにフォールバックする", async () => {
    saveSession({
      sessionId: "sess-stale",
      experimentGroup: "A",
      qrId: "QR-PRODUCT-P027",
      start: { floor: 1, x: 3, y: 50 },
    });

    installFetchMock([
      route("GET", "/api/products/P027", () => ({ body: PRODUCT })),
      route("GET", "/api/recommendations", () => ({
        status: 409,
        body: { code: "VISIT_LOCK_REQUIRED", message: "店頭のQRコードを読み取ってください。" },
      })),
    ]);

    renderProductPage();

    expect(await screen.findByTestId("visit-lock")).toBeInTheDocument();
  });
});
