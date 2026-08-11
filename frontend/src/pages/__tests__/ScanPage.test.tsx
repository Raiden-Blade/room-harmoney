import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock, route } from "../../test/mockFetch";
import { saveSession, getSession } from "../../state/session";
import { ProductPage } from "../ProductPage";
import { RoutePage } from "../RoutePage";
import { ScanPage } from "../ScanPage";

/**
 * S1 起動/スキャン画面: URL直リンク・フォールバック（4.1章 / HARNESS.md 既定のE2E経路）の
 * 単体テスト。カメラは使わず `/s/:qrId` 経路で `POST /api/session` が呼ばれ、
 * `qr_scan` イベントが送信され、商品QRなら S2（商品詳細）へ遷移することを確認する。
 */
function renderAt(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/s/:qrId" element={<ScanPage />} />
        <Route path="/scan" element={<ScanPage />} />
        <Route path="/products/:productId" element={<ProductPage />} />
        <Route path="/route" element={<RoutePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

/**
 * `<StrictMode>` 下（`frontend/src/main.tsx` の実運用構成）で `useEffect` が
 * 意図的に2回実行される状況を再現してレンダリングする。
 */
function renderStrictAt(initialPath: string) {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/s/:qrId" element={<ScanPage />} />
          <Route path="/scan" element={<ScanPage />} />
          <Route path="/products/:productId" element={<ProductPage />} />
        </Routes>
      </MemoryRouter>
    </StrictMode>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ScanPage (S1) - URL直リンク fallback", () => {
  it("qr_id直リンクから session 作成・qr_scan送信・S2遷移まで到達する", async () => {
    const { calls } = installFetchMock([
      route("GET", "/api/qr/QR-PRODUCT-P001", () => ({
        body: {
          type: "product",
          product_id: "P001",
          position: { floor: 1, x: 17, y: 18 },
          direct_url: "https://roomharmony.example.com/r/QR-PRODUCT-P001",
        },
      })),
      route("POST", "/api/session", () => ({
        body: {
          session_id: "sess-1",
          start: { floor: 1, x: 3, y: 50 },
          floor: 1,
          experiment_group: "A",
        },
      })),
      route("POST", "/api/events", () => ({ body: { ok: true } })),
      route("GET", "/api/products/P001", () => ({
        body: {
          product_id: "P001",
          name: "ナチュラル2人掛けソファ",
          cat_large: "リビング",
          cat_mid: "ソファ",
          cat_small: "2人掛けソファ",
          color: "ナチュラル",
          price: 39900,
          image_url: "https://dummyimage.com/300x300",
          floor: 1,
          zone: "A",
          x: 17,
          y: 18,
          sub_passage_flag: false,
        },
      })),
      route("GET", "/api/recommendations", () => ({ body: { related: [], coordinates: [] } })),
    ]);

    renderAt("/s/QR-PRODUCT-P001");

    // S2（商品詳細）へ遷移することを確認（= URL直リンクだけでハッピーパスに到達できる）。
    await screen.findByTestId("product-page", undefined, { timeout: 3000 });

    // POST /api/session が qr_id を伴って呼ばれた。
    const sessionCall = calls.find((c) => c.method === "POST" && c.url.includes("/api/session"));
    expect(sessionCall?.body).toEqual({ qr_id: "QR-PRODUCT-P001" });

    // qr_scan イベントが送信された。
    const eventCalls = calls.filter((c) => c.method === "POST" && c.url.includes("/api/events"));
    const qrScanCall = eventCalls.find(
      (c) => (c.body as { event_type?: string })?.event_type === "qr_scan",
    );
    expect(qrScanCall).toBeDefined();
    const qrScanBody = qrScanCall!.body as { session_id?: string };
    expect(qrScanBody.session_id).toBe("sess-1");

    // セッションが sessionStorage に保存され、来店ロックが解除される。
    await waitFor(() => {
      expect(getSession()?.sessionId).toBe("sess-1");
    });
  });

  it("入口QRの場合は店内トップ表示に留まる", async () => {
    installFetchMock([
      route("GET", "/api/qr/QR-ENTRANCE-001", () => ({
        body: {
          type: "entrance",
          product_id: null,
          position: { floor: 1, x: 3, y: 50 },
          direct_url: "https://roomharmony.example.com/r/QR-ENTRANCE-001",
        },
      })),
      route("POST", "/api/session", () => ({
        body: {
          session_id: "sess-2",
          start: { floor: 1, x: 3, y: 50 },
          floor: 1,
          experiment_group: "B",
        },
      })),
      route("POST", "/api/events", () => ({ body: { ok: true } })),
    ]);

    renderAt("/s/QR-ENTRANCE-001");

    await screen.findByTestId("scan-entrance");
  });

  it(
    "StrictModeでuseEffectが2回実行されても session 作成・qr_scan送信はそれぞれ1回に収束する" +
      "（QA G3 G-G3-7 回帰: 二重セッション/二重イベントの再発防止）",
    async () => {
      const { calls } = installFetchMock([
        route("GET", "/api/qr/QR-PRODUCT-P001", () => ({
          body: {
            type: "product",
            product_id: "P001",
            position: { floor: 1, x: 17, y: 18 },
            direct_url: "https://roomharmony.example.com/r/QR-PRODUCT-P001",
          },
        })),
        route("POST", "/api/session", () => ({
          body: {
            session_id: "sess-strict-1",
            start: { floor: 1, x: 3, y: 50 },
            floor: 1,
            experiment_group: "A",
          },
        })),
        route("POST", "/api/events", () => ({ body: { ok: true } })),
        route("GET", "/api/products/P001", () => ({
          body: {
            product_id: "P001",
            name: "ナチュラル2人掛けソファ",
            cat_large: "リビング",
            cat_mid: "ソファ",
            cat_small: "2人掛けソファ",
            color: "ナチュラル",
            price: 39900,
            image_url: "https://dummyimage.com/300x300",
            floor: 1,
            zone: "A",
            x: 17,
            y: 18,
            sub_passage_flag: false,
          },
        })),
        route("GET", "/api/recommendations", () => ({ body: { related: [], coordinates: [] } })),
      ]);

      renderStrictAt("/s/QR-PRODUCT-P001");

      await screen.findByTestId("product-page", undefined, { timeout: 3000 });

      // 修正前は StrictMode の二重 effect 実行により POST /api/session が2回呼ばれ、
      // 2つの異なる session_id・experiment_group が作られてしまっていた（QA証跡:
      // harness/evidence/G3/G-G3-7/events-db-dump.txt）。1回のQR到達につき
      // session 作成・qr_scan送信はそれぞれ1回だけであることを検証する。
      const sessionCalls = calls.filter(
        (c) => c.method === "POST" && c.url.includes("/api/session"),
      );
      expect(sessionCalls).toHaveLength(1);

      const qrScanCalls = calls.filter(
        (c) =>
          c.method === "POST" &&
          c.url.includes("/api/events") &&
          (c.body as { event_type?: string })?.event_type === "qr_scan",
      );
      expect(qrScanCalls).toHaveLength(1);

      await waitFor(() => {
        expect(getSession()?.sessionId).toBe("sess-strict-1");
      });
    },
  );

  it("存在しないqr_idの場合はエラー表示になる（QR読取失敗のエッジケース）", async () => {
    installFetchMock([
      route("GET", "/api/qr/QR-BOGUS", () => ({
        status: 404,
        body: { code: "QR_NOT_FOUND", message: "qr_id=QR-BOGUS は登録されていません。" },
      })),
      route("POST", "/api/session", () => ({
        status: 404,
        body: { code: "QR_NOT_FOUND", message: "qr_id=QR-BOGUS は登録されていません。" },
      })),
    ]);

    renderAt("/s/QR-BOGUS");

    await screen.findByTestId("scan-error");
  });
});

/**
 * S5 逆方向の受け口（チャットボットからのディープリンク・4.4章／フェーズ2-C）。
 * `product_id` / `coordinate_id` の既存挙動の回帰確認と、`to_product`（S4ルートへの受け口）の
 * 新規確認をまとめる。
 */
describe("ScanPage (S1) - チャットボットからのディープリンク受け口", () => {
  it("?product_id= が来たら商品詳細（S2）へ遷移する（回帰）", async () => {
    installFetchMock([
      route("GET", "/api/products/P001", () => ({
        body: {
          product_id: "P001",
          name: "ナチュラル2人掛けソファ",
          cat_large: "リビング",
          cat_mid: "ソファ",
          cat_small: "2人掛けソファ",
          color: "ナチュラル",
          price: 39900,
          image_url: "https://dummyimage.com/300x300",
          floor: 1,
          zone: "A",
          x: 17,
          y: 18,
          sub_passage_flag: false,
        },
      })),
      route("GET", "/api/recommendations", () => ({ body: { related: [], coordinates: [] } })),
    ]);

    renderAt("/scan?product_id=P001");

    await screen.findByTestId("product-page");
  });

  it("?coordinate_id= が来たらコーディネート詳細（S3）へ遷移する（回帰）", async () => {
    render(
      <MemoryRouter initialEntries={["/scan?coordinate_id=C001"]}>
        <Routes>
          <Route path="/scan" element={<ScanPage />} />
          <Route path="/coordinates/:coordinateId" element={<div data-testid="coordinate-stub" />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("coordinate-stub");
  });

  it("?to_product= が来たらS4ルート画面へ遷移し、来店セッションがあればルートAPIが呼ばれる（複数値対応）", async () => {
    saveSession({
      sessionId: "sess-deeplink",
      experimentGroup: "A",
      qrId: "QR-ENTRANCE-001",
      start: { floor: 1, x: 3, y: 50 },
    });

    const { calls } = installFetchMock([
      route("GET", "/api/route", () => ({
        body: {
          waypoints: [
            { floor: 1, x: 3, y: 50, type: "入口" },
            { floor: 1, x: 17, y: 18, type: "商品近傍" },
          ],
          sub_passages: [],
          visiting_order: ["P001", "P002"],
          unreachable: [],
          total_distance: 10,
        },
      })),
      route("GET", "/api/store-map/1", () => ({
        body: {
          floor: 1,
          floorplan: { type: "zones_rect", width: 100, height: 100, zones_rect: [] },
          zones: [],
          waypoints: [],
          edges: [],
          sub_passages: [],
        },
      })),
      route("GET", "/api/products/P001", () => ({
        body: {
          product_id: "P001",
          name: "ナチュラルソファ",
          cat_large: "リビング",
          cat_mid: "ソファ",
          cat_small: "2人掛けソファ",
          color: "ナチュラル",
          price: 39900,
          image_url: "https://dummyimage.com/300x300",
          floor: 1,
          zone: "A",
          x: 17,
          y: 18,
          sub_passage_flag: false,
        },
      })),
      route("GET", "/api/products/P002", () => ({
        body: {
          product_id: "P002",
          name: "ブラックソファ",
          cat_large: "リビング",
          cat_mid: "ソファ",
          cat_small: "2人掛けソファ",
          color: "ブラック",
          price: 44900,
          image_url: "https://dummyimage.com/300x300",
          floor: 1,
          zone: "A",
          x: 24,
          y: 23,
          sub_passage_flag: false,
        },
      })),
    ]);

    renderAt("/scan?to_product=P001,P002");

    await screen.findByTestId("route-page");

    const routeCall = calls.find((c) => c.method === "GET" && c.url.includes("/api/route"));
    expect(routeCall).toBeDefined();
    const routeUrl = new URL(routeCall!.url);
    expect(routeUrl.searchParams.getAll("to_product")).toEqual(["P001", "P002"]);
  });

  it("有効な来店セッションが無い状態で ?to_product= が来ても遷移はでき、遷移先（S4）が来店ロックを表示する", async () => {
    installFetchMock([]);

    renderAt("/scan?to_product=P001");

    await screen.findByTestId("visit-lock");
  });
});

/**
 * 新機能: 商品番号（数字列）による直接遷移。
 * QRを読み取れない来店客が商品番号を手入力すると、`GET /api/product-code/{code}` で
 * qr_id を解決し、以降は既存のQR解決フロー（session作成→qr_scan送信→S2遷移）に
 * 合流することを確認する。
 */
describe("ScanPage (S1) - 商品番号（手入力）による直接遷移", () => {
  it("商品番号を入力して送信すると、商品番号解決→session作成→qr_scan送信→S2遷移まで到達する", async () => {
    const { calls } = installFetchMock([
      route("GET", "/api/product-code/01-03-02-0001", () => ({
        body: {
          product_id: "P001",
          qr_id: "QR-PRODUCT-P001",
          position: { floor: 1, x: 17, y: 18 },
          product_code: "01-03-02-0001",
        },
      })),
      route("GET", "/api/qr/QR-PRODUCT-P001", () => ({
        body: {
          type: "product",
          product_id: "P001",
          position: { floor: 1, x: 17, y: 18 },
          direct_url: "https://roomharmony.example.com/r/QR-PRODUCT-P001",
        },
      })),
      route("POST", "/api/session", () => ({
        body: {
          session_id: "sess-code-1",
          start: { floor: 1, x: 17, y: 18 },
          floor: 1,
          experiment_group: "A",
        },
      })),
      route("POST", "/api/events", () => ({ body: { ok: true } })),
      route("GET", "/api/products/P001", () => ({
        body: {
          product_id: "P001",
          name: "ナチュラル2人掛けソファ",
          cat_large: "リビング",
          cat_mid: "ソファ",
          cat_small: "2人掛けソファ",
          color: "ナチュラル",
          price: 39900,
          image_url: "https://dummyimage.com/300x300",
          floor: 1,
          zone: "A",
          x: 17,
          y: 18,
          sub_passage_flag: false,
          product_code: "01-03-02-0001",
        },
      })),
      route("GET", "/api/recommendations", () => ({ body: { related: [], coordinates: [] } })),
    ]);

    const user = userEvent.setup();
    renderAt("/scan");

    await screen.findByTestId("scan-page");
    const input = screen.getByTestId("product-code-input");
    await user.type(input, "01-03-02-0001");
    await user.click(screen.getByTestId("product-code-submit"));

    await screen.findByTestId("product-page", undefined, { timeout: 3000 });

    // 商品番号解決API → qr_id を使ったセッション作成、の順で呼ばれている。
    const codeCall = calls.find(
      (c) => c.method === "GET" && c.url.includes("/api/product-code/01-03-02-0001"),
    );
    expect(codeCall).toBeDefined();

    const sessionCall = calls.find((c) => c.method === "POST" && c.url.includes("/api/session"));
    expect(sessionCall?.body).toEqual({ qr_id: "QR-PRODUCT-P001" });

    const qrScanCall = calls.find(
      (c) =>
        c.method === "POST" &&
        c.url.includes("/api/events") &&
        (c.body as { event_type?: string })?.event_type === "qr_scan",
    );
    expect(qrScanCall).toBeDefined();

    await waitFor(() => {
      expect(getSession()?.sessionId).toBe("sess-code-1");
    });
  });

  it("ハイフン無しの数字列を入力すると自動でハイフンが付与され、同じ商品に解決できる", async () => {
    installFetchMock([
      route("GET", "/api/product-code/01-03-02-0001", () => ({
        body: {
          product_id: "P001",
          qr_id: "QR-PRODUCT-P001",
          position: { floor: 1, x: 17, y: 18 },
          product_code: "01-03-02-0001",
        },
      })),
      route("GET", "/api/qr/QR-PRODUCT-P001", () => ({
        body: {
          type: "product",
          product_id: "P001",
          position: { floor: 1, x: 17, y: 18 },
          direct_url: "https://roomharmony.example.com/r/QR-PRODUCT-P001",
        },
      })),
      route("POST", "/api/session", () => ({
        body: {
          session_id: "sess-code-2",
          start: { floor: 1, x: 17, y: 18 },
          floor: 1,
          experiment_group: "B",
        },
      })),
      route("POST", "/api/events", () => ({ body: { ok: true } })),
      route("GET", "/api/products/P001", () => ({
        body: {
          product_id: "P001",
          name: "ナチュラル2人掛けソファ",
          cat_large: "リビング",
          cat_mid: "ソファ",
          cat_small: "2人掛けソファ",
          color: "ナチュラル",
          price: 39900,
          image_url: "https://dummyimage.com/300x300",
          floor: 1,
          zone: "A",
          x: 17,
          y: 18,
          sub_passage_flag: false,
          product_code: "01-03-02-0001",
        },
      })),
      route("GET", "/api/recommendations", () => ({ body: { related: [], coordinates: [] } })),
    ]);

    const user = userEvent.setup();
    renderAt("/scan");

    await screen.findByTestId("scan-page");
    const input = screen.getByTestId("product-code-input") as HTMLInputElement;
    await user.type(input, "0103020001");
    // 数字だけ入力しても 2-2-2-3 の位置でハイフンが自動挿入される。
    expect(input.value).toBe("01-03-02-0001");
    await user.click(screen.getByTestId("product-code-submit"));

    await screen.findByTestId("product-page", undefined, { timeout: 3000 });
  });

  it("無効な商品番号を入力するとエラーが表示され、遷移しない（該当商品なし）", async () => {
    installFetchMock([
      route("GET", "/api/product-code/99-99-99-9999", () => ({
        status: 404,
        body: {
          code: "PRODUCT_CODE_NOT_FOUND",
          message: "商品番号 99-99-99-9999 に該当する商品が見つかりません。番号をご確認ください。",
        },
      })),
    ]);

    const user = userEvent.setup();
    renderAt("/scan");

    await screen.findByTestId("scan-page");
    await user.type(screen.getByTestId("product-code-input"), "99-99-99-9999");
    await user.click(screen.getByTestId("product-code-submit"));

    const errorNotice = await screen.findByTestId("product-code-error");
    expect(errorNotice.textContent).toContain("見つかりません");
    expect(screen.queryByTestId("product-page")).toBeNull();
  });
});
