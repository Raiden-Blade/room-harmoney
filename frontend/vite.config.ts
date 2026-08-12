import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";

// https://vite.dev/config/
// `vitest/config` の defineConfig を使うことで vite の設定と `test`（Vitest）設定を
// 同一ファイルで型安全に扱う（G3: ビルド成功＋コンポーネント/結合スモークが緑）。
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // 9章 PWA: manifest 有効＋サービスワーカー。manifest.webmanifest は
      // public/ に既存の静的ファイルがあるためプラグインでの再生成はせず既存ファイルを使う。
      registerType: "autoUpdate",
      manifest: false,
      injectRegister: "auto",
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico,webmanifest}"],
      },
      devOptions: {
        // 開発中のdev起動（G3 DoD）を素直にするため、devサーバではSWを無効にする。
        enabled: false,
      },
    }),
  ],
  server: {
    port: 5173,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    // Codex/手動セットアップ中に残る `node_modules.partial` をテスト探索対象にすると、
    // Windows上で全量 `vitest run` が長時間停止する。製品コードではない一時依存、
    // ビルド成果物、Playwright専用E2Eを明示的に除外し、標準 `npm test` を決定的にする。
    exclude: [
      ...configDefaults.exclude,
      "node_modules.partial/**",
      "dist/**",
      "e2e/**",
      "test-results/**",
    ],
  },
});
