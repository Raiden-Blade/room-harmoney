import { defineConfig } from "@playwright/test";

/**
 * G4 E2E（実ブラウザ / Playwright）設定。
 *
 * QA検証専用。backend（port 8000, DATABASE_URL を検証用DBに固定）と
 * frontend 本番ビルド配信（`vite preview`, port 4173）はテスト実行前に
 * 手動で起動しておく前提（docs/HARNESS.md §2 G4 参照）。
 * webServer は使わず、既に起動済みのサーバーに対して実行する
 * （backend の DB 固定・AC-4 のログ検証に手動起動が必要なため）。
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*.e2e.ts/,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "../harness/evidence/G4/AC-6/playwright-report.json" }]],
  use: {
    baseURL: "http://localhost:4173",
    headless: true,
    channel: "chromium",
    viewport: { width: 1280, height: 900 },
    screenshot: "off",
    trace: "off",
  },
});
