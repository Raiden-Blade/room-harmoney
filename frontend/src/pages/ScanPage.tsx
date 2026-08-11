/**
 * S1 起動/スキャン画面（7章 / DESIGN.md S1）。
 *
 * 到達経路は3つ:
 * 1. カメラでQRを読み取る（`html5-qrcode`）。
 * 2. URL直リンク・フォールバック: `/s/:qrId` または `/scan?qr_id=...`（4.1章 / HARNESS.md）。
 *    カメラ非対応端末・E2Eの既定経路はこちら。
 * 3. 既存チャットボットからのディープリンク受け口: `?product_id=` / `?coordinate_id=` /
 *    `?to_product=`（4.4章・フェーズ2-C）。詳細な仕様は `../deeplink.ts` を参照。
 *    これは来店セッションの有無に関わらず該当画面へ遷移する
 *    （セッションが無ければ遷移先の画面が来店ロックを表示する）。
 *
 * QR解決フロー: `GET /api/qr/{qr_id}` で種別判定 → `POST /api/session` でセッション開始
 * （読取地点を起点として記録）→ `qr_scan` イベント送信 → 商品QRなら S2、入口QRなら
 * 店内トップ（本画面内に留まりチャットボット導線等を表示）。
 *
 * 4つ目の到達経路（新機能）: **商品番号による直接遷移**。QRの下に併記された商品番号
 * （`LL-MM-SS-NNN`。ハイフン有無どちらでも入力可）を手入力すると、
 * `GET /api/product-code/{code}` でその商品の `qr_id` を解決し、以降は
 * 上記と全く同じ `resolveAndEnter`（session作成→qr_scanイベント送信→S2遷移）に
 * 合流する。つまり「その商品のQRをスキャンしたのと等価」になる。
 */
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  ApiError,
  createSession,
  postEvent,
  resolveProductCode,
  resolveQr,
} from "../api/client";
import { ChatbotLink } from "../components/ChatbotLink";
import { QrCameraScanner } from "../components/QrCameraScanner";
import { buildRoutePath, parseInboundDeepLink } from "../deeplink";
import { PRODUCT_CODE_MAX_LENGTH, formatProductCodeInput } from "../productCode";
import { saveSession } from "../state/session";

type Status = "idle" | "resolving" | "entrance" | "error";

/** カメラで読み取ったテキストが `direct_url`（URL形式）の場合は末尾セグメントを qr_id とみなす。 */
function extractQrId(text: string): string {
  try {
    const url = new URL(text);
    const segments = url.pathname.split("/").filter(Boolean);
    return segments.length > 0 ? segments[segments.length - 1] : text;
  } catch {
    return text;
  }
}

export function ScanPage() {
  const params = useParams<{ qrId?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  // 商品番号による直接遷移（新機能）: 手入力フォームの状態。
  const [productCodeInput, setProductCodeInput] = useState("");
  const [productCodeError, setProductCodeError] = useState<string | null>(null);
  const [productCodeSubmitting, setProductCodeSubmitting] = useState(false);

  const inboundDeepLink = parseInboundDeepLink(searchParams);
  const deepProductId = inboundDeepLink.productId;
  const deepCoordinateId = inboundDeepLink.coordinateId;
  const deepToProducts = inboundDeepLink.toProducts;
  const deepToProductsKey = deepToProducts.join(",");
  const qrId = params.qrId ?? searchParams.get("qr_id");

  // URL直リンク（/s/:qrId 等）経由で解決済みの qrId を記録するガード。
  // React 18/19 <StrictMode> の開発ビルドでは useEffect が意図的に
  // 「setup → cleanup → setup」の順で2回実行されるため、ガードが無いと
  // resolveAndEnter（session作成 + qr_scan送信）が2回走り、1回のQR到達に対して
  // session が2つ・qr_scan イベントが2件作られてしまう（QA G3 G-G3-7 観察事項）。
  // 同一 qrId に対しては1回のみ resolveAndEnter を実行することで、
  // 「1スキャン = session 1・qr_scan 1」を保証する。
  // なお、これはURL直リンク解決フロー専用のガードであり、カメラ読取
  // （onDecoded 経由の resolveAndEnter 呼び出し）には影響しない。
  const resolvedQrIdRef = useRef<string | null>(null);

  // resolveAndEnter の非同期処理を、実際にコンポーネントが最終的に
  // アンマウントされた場合にのみ中断させるためのフラグ。
  // 単純な `let cancelled = false` をuseEffect内に閉じ込める実装だと、
  // StrictModeの「setup→cleanup→setup」の最初のsetupで開始した非同期処理が
  // 直後のcleanupで（実際には破棄されない疑似アンマウントにもかかわらず）
  // 中断されてしまう。ref はコンポーネントインスタンス間で共有され、
  // 2回目のsetupで false に戻せるため、疑似アンマウントでは中断されず、
  // 本当の最終アンマウント後のみ true のまま残る。
  const cancelledRef = useRef(false);

  async function resolveAndEnter(id: string, isCancelled: () => boolean = () => false) {
    setStatus("resolving");
    setError(null);
    try {
      const [qr, session] = await Promise.all([resolveQr(id), createSession(id)]);
      if (isCancelled()) return;
      saveSession({
        sessionId: session.session_id,
        experimentGroup: session.experiment_group,
        qrId: id,
        start: session.start,
      });
      // 10章 計測: qr_scan（商品QR/入口QRの種別を問わず記録）
      await postEvent(session.session_id, "qr_scan", {
        qr_id: id,
        qr_type: qr.type,
        product_id: qr.product_id,
      });
      if (isCancelled()) return;

      if (qr.type === "product" && qr.product_id) {
        navigate(`/products/${qr.product_id}`, { replace: true });
        return;
      }
      setStatus("entrance");
    } catch (err) {
      if (isCancelled()) return;
      setStatus("error");
      setError(
        err instanceof ApiError
          ? err.message
          : "QRの読み取りに失敗しました。時間をおいて再度お試しください。",
      );
    }
  }

  /**
   * 商品番号（新機能）の手入力フォーム送信ハンドラ。
   * `GET /api/product-code/{code}` で qr_id を解決し、以降は
   * `resolveAndEnter`（＝カメラ/URL直リンクと同一のQR解決フロー）に合流する。
   * ここでの失敗（無効な商品番号）は、QR自体の解決失敗とは別の `productCodeError` として
   * 表示する（9章アクセシビリティ: 何が失敗したか分かりやすい案内）。
   */
  async function handleProductCodeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = productCodeInput.trim();
    if (!trimmed) return;

    setProductCodeError(null);
    setProductCodeSubmitting(true);
    try {
      const resolution = await resolveProductCode(trimmed);
      await resolveAndEnter(resolution.qr_id);
    } catch (err) {
      setProductCodeError(
        err instanceof ApiError
          ? err.message
          : "商品番号の確認に失敗しました。時間をおいて再度お試しください。",
      );
    } finally {
      setProductCodeSubmitting(false);
    }
  }

  useEffect(() => {
    // このeffectが（疑似的にでも）setupされた = まだ有効、とみなす。
    cancelledRef.current = false;

    // S5 逆方向の受け口: チャットボットからのディープリンクを優先的に処理する。
    if (deepProductId) {
      navigate(`/products/${deepProductId}`, { replace: true });
      return;
    }
    if (deepCoordinateId) {
      navigate(`/coordinates/${deepCoordinateId}`, { replace: true });
      return;
    }
    // S4 ルート表示への受け口（フェーズ2-C・4.4章）: `?to_product=` （複数可）。
    // URLスキームの詳細は `../deeplink.ts` を参照。
    if (deepToProducts.length > 0) {
      navigate(buildRoutePath(deepToProducts), { replace: true });
      return;
    }
    if (qrId) {
      if (resolvedQrIdRef.current !== qrId) {
        resolvedQrIdRef.current = qrId;
        void resolveAndEnter(qrId, () => cancelledRef.current);
      }
    }

    return () => {
      cancelledRef.current = true;
    };
    // qrId/deepProductId/deepCoordinateId/deepToProductsKey が変化した時だけ再実行する。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qrId, deepProductId, deepCoordinateId, deepToProductsKey]);

  if (status === "resolving") {
    return (
      <main className="app-shell" data-testid="scan-resolving">
        <p>QRを確認しています…</p>
      </main>
    );
  }

  if (status === "entrance") {
    return (
      <main className="app-shell" data-testid="scan-entrance">
        <h1>Room Harmony</h1>
        <p>ご来店ありがとうございます。売場の商品QRを読み取ると、関連商品やコーディネートをご案内します。</p>
        <ChatbotLink label="チャットボットで商品を探す" screen="scan_entrance" />
      </main>
    );
  }

  return (
    <main className="app-shell" data-testid="scan-page">
      <h1>Room Harmony</h1>
      <p>店頭のQRコードを読み取ってください。</p>

      {status === "error" && error && (
        <p className="error-notice" role="alert" data-testid="scan-error">
          {error}
        </p>
      )}

      {!cameraActive && (
        <button
          type="button"
          className="btn-primary"
          data-testid="start-camera-button"
          onClick={() => {
            setCameraError(null);
            setCameraActive(true);
          }}
        >
          カメラでQRを読み取る
        </button>
      )}

      {cameraActive && (
        <QrCameraScanner
          onDecoded={(text) => {
            setCameraActive(false);
            void resolveAndEnter(extractQrId(text));
          }}
          onError={(message) => {
            setCameraActive(false);
            setCameraError(message);
          }}
        />
      )}

      {cameraError && (
        <p className="error-notice" role="alert" data-testid="camera-error">
          {cameraError}
        </p>
      )}

      <p className="hint">
        カメラが使えない場合は、QRに記載のURL（例: <code>/s/QR-PRODUCT-P001</code>）から直接お進みいただけます。
      </p>

      <section className="product-code-entry" aria-labelledby="product-code-heading">
        <h2 id="product-code-heading">QRを読み取れない場合</h2>
        <p>QRの下に表示された商品番号を入力してください。</p>
        <form onSubmit={(e) => void handleProductCodeSubmit(e)}>
          <label htmlFor="product-code-input">商品番号</label>
          <input
            id="product-code-input"
            data-testid="product-code-input"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            placeholder="例: 01-03-02-0001"
            maxLength={PRODUCT_CODE_MAX_LENGTH}
            value={productCodeInput}
            onChange={(e) => setProductCodeInput(formatProductCodeInput(e.target.value))}
          />
          <button
            type="submit"
            className="btn-secondary"
            data-testid="product-code-submit"
            disabled={productCodeSubmitting || productCodeInput.trim().length === 0}
          >
            商品へ進む
          </button>
        </form>
        {productCodeError && (
          <p className="error-notice" role="alert" data-testid="product-code-error">
            {productCodeError}
          </p>
        )}
      </section>
    </main>
  );
}
