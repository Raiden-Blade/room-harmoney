import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import "./App.css";
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
