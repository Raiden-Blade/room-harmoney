import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock, route } from "../../test/mockFetch";
import { getSession } from "../../state/session";
import { ProductPage } from "../ProductPage";
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
