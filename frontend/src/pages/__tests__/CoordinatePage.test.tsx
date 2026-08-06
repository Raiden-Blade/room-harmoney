import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock, route } from "../../test/mockFetch";
import { saveSession } from "../../state/session";
import { CoordinatePage } from "../CoordinatePage";

const COORDINATE = {
  coordinate_id: "C001",
  name: "ナチュラルリビング",
  theme: "ナチュラル",
  product_ids: ["P001", "P003"],
  image_url: "https://dummyimage.com/600x400&text=C001",
  total_price_estimate: 70690,
  products: [
    {
      product_id: "P001",
      name: "ナチュラル2人掛けソファ",
      cat_large: "リビング",
      cat_mid: "ソファ",
      cat_small: "2人掛けソファ",
      color: "ナチュラル",
      price: 39900,
      image_url: "https://dummyimage.com/72x72",
      floor: 1,
      zone: "A",
      x: 17,
      y: 18,
      sub_passage_flag: false,
    },
    {
      product_id: "P003",
      name: "ホワイトリビングテーブル",
      cat_large: "リビング",
      cat_mid: "リビングテーブル",
      cat_small: "センターテーブル",
      color: "ホワイト",
      price: 12900,
      image_url: "https://dummyimage.com/72x72",
      floor: 1,
      zone: "A",
      x: 18,
      y: 24,
      sub_passage_flag: false,
    },
  ],
};

function renderCoordinatePage() {
  return render(
    <MemoryRouter initialEntries={["/coordinates/C001"]}>
      <Routes>
        <Route path="/coordinates/:coordinateId" element={<CoordinatePage />} />
        <Route path="/route" element={<div data-testid="mock-route-page">route page</div>} />
        <Route path="/scan" element={<div data-testid="mock-scan-page">scan page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CoordinatePage (S3)", () => {
  it("完成イメージ・構成商品・合計金額目安を表示し、揃えるタップでcoordinate_tap送信とS4遷移が行われる", async () => {
    saveSession({
      sessionId: "sess-active",
      experimentGroup: "A",
      qrId: "QR-PRODUCT-P001",
      start: { floor: 1, x: 3, y: 50 },
    });

    const { calls } = installFetchMock([
      route("GET", "/api/coordinates/C001", () => ({ body: COORDINATE })),
      route("POST", "/api/events", () => ({ body: { ok: true } })),
    ]);

    renderCoordinatePage();

    await screen.findByTestId("coordinate-page");
    expect(screen.getByTestId("coordinate-image")).toBeInTheDocument();
    expect(screen.getByText("ナチュラルリビング")).toBeInTheDocument();

    const productsList = screen.getByTestId("coordinate-products");
    expect(within(productsList).getAllByRole("listitem")).toHaveLength(2);

    expect(screen.getByTestId("coordinate-total-price")).toHaveTextContent("70,690");

    fireEvent.click(screen.getByTestId("coordinate-gather-button"));

    await screen.findByTestId("mock-route-page");

    const eventCall = calls.find(
      (c) =>
        c.method === "POST" &&
        c.url.includes("/api/events") &&
        (c.body as { event_type?: string })?.event_type === "coordinate_tap",
    );
    expect(eventCall).toBeDefined();
    const eventBody = eventCall!.body as { payload?: { product_ids?: string[] } };
    expect(eventBody.payload?.product_ids).toEqual(["P001", "P003"]);
  });

  it("セッションが無い場合、揃えるタップはS1（QR読取）へ促す", async () => {
    installFetchMock([route("GET", "/api/coordinates/C001", () => ({ body: COORDINATE }))]);

    renderCoordinatePage();

    await screen.findByTestId("coordinate-page");
    fireEvent.click(screen.getByTestId("coordinate-gather-button"));

    await screen.findByTestId("mock-scan-page");
  });
});
