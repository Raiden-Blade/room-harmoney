/**
 * S3 コーディネート詳細画面（7章 / DESIGN.md S3）。
 *
 * `GET /api/coordinates/{id}` はセッション任意（`backend/app/routers/coordinates.py`）。
 * セッションが有効なら `coordinate_view` はバックエンドが自動記録する（二重送信しない）。
 * 「このコーデで揃える／場所を見る」（`coordinate_tap`）はフロントの明示イベントとして送り、
 * 構成商品すべてを目的地にした複数目的地ルート（S4）へ遷移する。ルート表示自体は
 * 来店ロック対象のため、セッションが無い場合はこのボタンから直接ロック画面へ促す。
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, getCoordinate, postEvent } from "../api/client";
import type { CoordinateDetail } from "../api/types";
import { ChatbotLink } from "../components/ChatbotLink";
import { ErrorNotice } from "../components/ErrorNotice";
import { ImageWithFallback } from "../components/ImageWithFallback";
import { getSession } from "../state/session";

export function CoordinatePage() {
  const { coordinateId } = useParams<{ coordinateId: string }>();
  const navigate = useNavigate();

  const [coordinate, setCoordinate] = useState<CoordinateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!coordinateId) return;
    let cancelled = false;
    const session = getSession();

    getCoordinate(coordinateId, session?.sessionId ?? null)
      .then((c) => {
        if (!cancelled) setCoordinate(c);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "コーディネート情報の取得に失敗しました。");
      });

    return () => {
      cancelled = true;
    };
  }, [coordinateId]);

  if (!coordinateId) {
    return <ErrorNotice message="コーディネートIDが指定されていません。" />;
  }

  if (error) {
    return <ErrorNotice message={error} />;
  }

  if (!coordinate) {
    return (
      <main className="app-shell" data-testid="coordinate-loading">
        <p>読み込み中…</p>
      </main>
    );
  }

  async function handleGatherClick() {
    if (!coordinate) return;
    const session = getSession();
    const productIds = coordinate.products.map((p) => p.product_id);

    if (!session) {
      // 来店ロック（AC-5）: ルート表示（S4）は中核機能のためセッション必須。
      navigate("/scan");
      return;
    }

    // 10章 計測: coordinate_tap（「このコーデで揃える／場所を見る」タップ）
    await postEvent(session.sessionId, "coordinate_tap", {
      coordinate_id: coordinate.coordinate_id,
      product_ids: productIds,
    }).catch(() => undefined);

    const params = new URLSearchParams();
    for (const id of productIds) params.append("to_product", id);
    navigate(`/route?${params.toString()}`);
  }

  return (
    <main className="app-shell" data-testid="coordinate-page">
      <ImageWithFallback
        src={coordinate.image_url}
        alt={coordinate.name}
        data-testid="coordinate-image"
        width={600}
        height={400}
        className="coordinate-hero-image"
      />
      <h1>{coordinate.name}</h1>
      <p>テーマ: {coordinate.theme}</p>

      <ul className="coordinate-products" data-testid="coordinate-products">
        {coordinate.products.map((p) => (
          <li key={p.product_id} data-testid={`coordinate-product-${p.product_id}`}>
            <ImageWithFallback src={p.image_url} alt={p.name} width={72} height={72} />
            <span>{p.name}</span>
            <span>¥{p.price.toLocaleString("ja-JP")}</span>
          </li>
        ))}
      </ul>

      <p className="total-price" data-testid="coordinate-total-price">
        合計金額目安: ¥{coordinate.total_price_estimate.toLocaleString("ja-JP")}
      </p>

      <button
        type="button"
        className="btn-primary"
        data-testid="coordinate-gather-button"
        onClick={() => {
          void handleGatherClick();
        }}
      >
        このコーデで揃える／場所を見る
      </button>

      <ChatbotLink coordinateId={coordinateId} screen="coordinate_detail" />
    </main>
  );
}
