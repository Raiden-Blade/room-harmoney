import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import "./App.css";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { CoordinatePage } from "./pages/CoordinatePage";
import { ProductPage } from "./pages/ProductPage";
import { RoutePage } from "./pages/RoutePage";
import { ScanPage } from "./pages/ScanPage";

/**
 * Room Harmony フロントエンド ルーティング（7章 画面一覧 S1〜S4。S5はページ内導線）。
 *
 * - `/`, `/scan`: S1 起動/スキャン（カメラ or `?qr_id=` フォールバック、
 *   `?product_id=`/`?coordinate_id=` チャットボット受け口）
 * - `/s/:qrId`: S1 のURL直リンク・フォールバック（4.1章・カメラ不可時/E2E既定経路）
 * - `/products/:productId`: S2 商品詳細
 * - `/coordinates/:coordinateId`: S3 コーディネート詳細
 * - `/route`: S4 マップ・ルート
 * - `/admin`: 内部向け A/B×KPI管理ダッシュボード（フェーズ2-B2・20章 PM兼効果検証）。
 *   来店客のS1〜S5フローとは分離した導線で、顧客向け画面からはリンクしない（直リンク前提）。
 */
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ScanPage />} />
        <Route path="/scan" element={<ScanPage />} />
        <Route path="/s/:qrId" element={<ScanPage />} />
        <Route path="/products/:productId" element={<ProductPage />} />
        <Route path="/coordinates/:coordinateId" element={<CoordinatePage />} />
        <Route path="/route" element={<RoutePage />} />
        <Route path="/admin" element={<AdminDashboardPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
