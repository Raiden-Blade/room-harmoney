import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * G4 E2E ハッピーパス（QA検証・独立実装、実装コードは変更しない）。
 *
 * カメラは使わず、要件4.1のURL直リンク・フォールバック（/s/:qrId）経由で
 * S1→S2に到達する（docs/HARNESS.md §2 G4 特記）。
 *
 * 前提: backend（port 8000, DATABASE_URL=検証用DB固定）と
 * frontend 本番ビルド配信（`vite preview`, port 4173）を事前に手動起動しておくこと。
 */

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const EVIDENCE_ROOT = path.resolve(__dirname, "..", "..", "harness", "evidence", "G4");

function evidencePath(ac: string, filename: string): string {
  const dir = path.join(EVIDENCE_ROOT, ac);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  return path.join(dir, filename);
}

test.describe.serial("G4 happy path (fresh session)", () => {
  test("AC-1/AC-2/AC-3/AC-4: QR起点 -> 商品詳細 -> 関連/コーデ -> ルート -> ログ記録", async ({
    page,
  }) => {
    // --- S1: URL直リンク・フォールバックで商品QRを解決 -> S2へ自動遷移 ---
    await page.goto("/s/QR-PRODUCT-P001");
    await expect(page.getByTestId("product-page")).toBeVisible();
    await expect(page.getByTestId("product-detail")).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/products\/P001$/);

    // 商品詳細本体
    await expect(page.getByRole("heading", { name: "ナチュラル2人掛けソファ" })).toBeVisible();
    await expect(page.getByTestId("product-price")).toContainText("39,900");

    // --- AC-1: 関連商品がリフト順（backendの /api/recommendations 応答順）で表示 ---
    const relatedList = page.getByTestId("related-list");
    await expect(relatedList).toBeVisible();
    const relatedItems = relatedList.locator("li");
    await expect(relatedItems).toHaveCount(2);
    // backend `GET /api/recommendations?product_id=P001` の実応答順は P036, P037（lift降順）。
    await expect(relatedItems.nth(0)).toHaveAttribute("data-testid", "related-item-P036");
    await expect(relatedItems.nth(1)).toHaveAttribute("data-testid", "related-item-P037");
    await expect(relatedItems.nth(0)).toContainText("ブラックデスクライト");
    await expect(relatedItems.nth(1)).toContainText("ホワイトデスクライト");
    // 「伸びしろ」バッジ（high_lift_low_corate）
    await expect(relatedItems.nth(0).getByTestId("high-lift-low-corate-badge")).toBeVisible();

    // この商品を使ったコーディネートが1件以上（AC-2前提）
    const coordinateList = page.getByTestId("coordinate-list");
    await expect(coordinateList).toBeVisible();
    await expect(page.getByTestId("coordinate-link-C001")).toBeVisible();

    await page.screenshot({
      path: evidencePath("AC-1", "01-s2-product-detail-related-lift-order.png"),
      fullPage: true,
    });

    // --- S2 -> S4: 関連商品の「場所を見る」でルート画面へ（複数フロア・階段経由） ---
    await page.getByTestId("related-tap-P036").click();
    await expect(page).toHaveURL(/\/route\?to_product=P036/);
    await expect(page.getByTestId("route-page")).toBeVisible();
    await expect(page.getByTestId("floor-map-svg")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("floor-switch")).toBeVisible();
    await expect(page.getByTestId("visiting-order-item-P036")).toBeVisible();
    // ルート線（起点->目的商品）がSVG上に描画される
    await expect(page.getByTestId("route-line")).toHaveCount(1);

    await page.screenshot({
      path: evidencePath("AC-3", "01-s4-route-from-related-item.png"),
      fullPage: true,
    });

    // --- S2に戻り、コーディネートリンクからS3へ ---
    await page.goto("/products/P001");
    await expect(page.getByTestId("product-detail")).toBeVisible();
    await page.getByTestId("coordinate-link-C001").click();
    await expect(page).toHaveURL(/\/coordinates\/C001$/);
    await expect(page.getByTestId("coordinate-page")).toBeVisible();

    // --- AC-2: 構成商品と合計金額目安 ---
    const coordProducts = page.getByTestId("coordinate-products").locator("li");
    await expect(coordProducts).toHaveCount(4);
    await expect(page.getByTestId("coordinate-product-P001")).toBeVisible();
    await expect(page.getByTestId("coordinate-product-P003")).toBeVisible();
    await expect(page.getByTestId("coordinate-product-P007")).toBeVisible();
    await expect(page.getByTestId("coordinate-product-P009")).toBeVisible();
    await expect(page.getByTestId("coordinate-total-price")).toContainText("70,690");

    await page.screenshot({
      path: evidencePath("AC-2", "01-s3-coordinate-detail.png"),
      fullPage: true,
    });

    // --- S3 -> S4: 「このコーデで揃える／場所を見る」で複数目的地ルートへ ---
    // 構成商品の1つ P009 は sub_passage_flag=true（SUBゾーン）のため、
    // このルートは経由サブ通路を含む（backend `/api/route` で確認済み: sub_passages 1件）。
    await page.getByTestId("coordinate-gather-button").click();
    await expect(page).toHaveURL(/\/route\?/);
    await expect(page.getByTestId("route-page")).toBeVisible();
    await expect(page.getByTestId("floor-map-svg")).toBeVisible({ timeout: 10_000 });

    // --- AC-3: 経路が地図上に線で描画され、経由サブ通路が示される ---
    await expect(page.getByTestId("route-line")).toHaveCount(1);
    await expect(page.getByTestId("route-subpassage")).toHaveCount(1);
    await expect(page.getByTestId("zone-rect-SUB")).toBeVisible();
    // 巡回順（visiting_order）が表示される
    await expect(page.getByTestId("visiting-order-item-P001")).toBeVisible();
    await expect(page.getByTestId("visiting-order-item-P003")).toBeVisible();
    await expect(page.getByTestId("visiting-order-item-P007")).toBeVisible();
    await expect(page.getByTestId("visiting-order-item-P009")).toBeVisible();

    await page.screenshot({
      path: evidencePath("AC-3", "02-s4-route-multi-destination-subpassage.png"),
      fullPage: true,
    });

    // --- AC-4: このセッションのイベントログをDBで直接検証するため、session_id を書き出す ---
    const sessionId = await page.evaluate(() => sessionStorage.getItem("rh_session_id"));
    const experimentGroup = await page.evaluate(() =>
      sessionStorage.getItem("rh_experiment_group"),
    );
    expect(sessionId).toBeTruthy();
    expect(experimentGroup).toBeTruthy();
    writeFileSync(
      evidencePath("AC-4", "session-id.json"),
      JSON.stringify({ sessionId, experimentGroup }, null, 2),
      "utf-8",
    );
  });
});

test.describe("G4 AC-5: visit lock without an active session", () => {
  // このdescribeブロックは既定の新規コンテキスト（sessionStorage空）で実行される。
  test("AC-5: 有効QRセッション無しで /route に直接遷移するとロックUIが表示される", async ({
    page,
  }) => {
    await page.goto("/route?to_product=P001");
    await expect(page.getByTestId("visit-lock")).toBeVisible();
    await expect(page.getByRole("alert")).toContainText("この機能はご利用いただけません");
    await expect(page.getByTestId("visit-lock-scan-link")).toBeVisible();

    await page.screenshot({
      path: evidencePath("AC-5", "01-route-locked-no-session.png"),
      fullPage: true,
    });
  });

  test("AC-5: 有効QRセッション無しで /products/:id に直接遷移すると関連/コーデがロックされる", async ({
    page,
  }) => {
    await page.goto("/products/P001");
    // 商品情報自体はロック対象外（設計コメント: products.py はセッション不要）
    await expect(page.getByTestId("product-detail")).toBeVisible();
    // 関連商品セクションはロック対象（AC-5）
    await expect(page.getByTestId("visit-lock")).toBeVisible();

    await page.screenshot({
      path: evidencePath("AC-5", "02-product-detail-related-locked-no-session.png"),
      fullPage: true,
    });
  });
});
