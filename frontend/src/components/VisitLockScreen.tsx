/**
 * 来店ロックUI（9章 非機能要件 / AC-5）。
 *
 * 有効な店内QR起点セッションが無い状態で中核画面（S2 関連表示・S4 ルート）に来た場合、
 * またはAPIが 409 `VISIT_LOCK_REQUIRED` を返した場合に表示する共通コンポーネント。
 */
import { Link } from "react-router-dom";

export function VisitLockScreen({ message }: { message?: string }) {
  return (
    <div className="visit-lock" data-testid="visit-lock" role="alert">
      <h2>この機能はご利用いただけません</h2>
      <p>
        {message ??
          "店頭のQRコードを読み取ってください。有効な来店セッションが開始されると、関連商品や店内ルートをご案内できます。"}
      </p>
      <Link to="/scan" className="btn-primary" data-testid="visit-lock-scan-link">
        QRを読み取る
      </Link>
    </div>
  );
}
