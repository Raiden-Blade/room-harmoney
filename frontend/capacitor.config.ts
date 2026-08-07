import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Capacitor 設定（フェーズ3-C: ネイティブアプリ化 移行readiness）。
 *
 * このファイルは既存の PWA（Vite ビルド）をそのままネイティブシェルで包むための設定であり、
 * Web 側の実装（recommender/routing のロジック層・API クライアント・UI）には一切手を入れない
 * （9章 拡張性「将来のネイティブアプリ化を見据えロジック/データをUIから分離」を踏襲）。
 *
 * 本環境には Xcode / Android Studio・実機/エミュレータが無いため、`npx cap add android|ios`
 * によるネイティブプロジェクト生成・実機ビルド・実機E2Eは実行していない（環境制約）。
 * 詳細な移行手順・制約は `docs/NATIVE_READINESS.md` を参照。
 *
 * 注意: このファイルは `tsconfig.app.json`（include: ["src"]）にも `tsconfig.node.json`
 * （include: ["vite.config.ts"]）にも含まれないため `npm run build`（tsc -b && vite build）の
 * 型チェック/バンドル対象外（＝Web本体のビルドに影響を与えない）。Capacitor CLI（`npx cap`）が
 * 単体で読み込む設定ファイルであり、`playwright.config.ts` と同様の「ツール専用configはアプリの
 * tsconfig参照から外す」という既存の設計方針を踏襲している。
 */
const config: CapacitorConfig = {
  // ダミーの逆ドメイン形式appId。実運用時はニトリ側で正式なアプリIDに差し替える。
  appId: "jp.co.nitori.roomharmony",
  appName: "Room Harmony",
  // `npm run build` の出力先（vite.config.ts の既定値）をそのままネイティブシェルにコピーする。
  webDir: "dist",
  // server: {
  //   // 開発中にネイティブシェルからホストPC上のViteサーバへ直接接続したい場合は
  //   // `url` にLAN上のdevサーバURL（例: "http://192.168.x.x:5173"）を設定し、
  //   // `cleartext: true` を付与する（本番ビルドでは使わない。デバッグ専用）。
  //   url: "http://192.168.x.x:5173",
  //   cleartext: true,
  // },
};

export default config;
