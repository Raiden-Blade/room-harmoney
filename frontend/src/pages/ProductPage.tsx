/**
 * S2 商品詳細画面（7章 / DESIGN.md S2）。
 *
 * 商品情報自体は来店ロック対象外（`GET /api/products/{id}` はセッション不要、
 * `backend/app/routers/products.py` 参照）。一方、関連商品＋コーディネート
 * （`GET /api/recommendations`）は中核機能のため来店ロック対象（AC-5）。
 * `related_view` はバックエンドが `GET /api/recommendations` 呼び出し時に自動記録する
 * （`backend/app/routers/recommendations.py`）ため、フロントから二重送信はしない。
 * `related_tap`（関連商品の「場所を見る」タップ）はフロントの明示イベントとして送る。
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, getProduct, getRecommendations } from "../api/client";
import type { Product, RecommendationsResponse } from "../api/types";
import { ChatbotLink } from "../components/ChatbotLink";
import { ErrorNotice } from "../components/ErrorNotice";
import { ImageWithFallback } from "../components/ImageWithFallback";
import { VisitLockScreen } from "../components/VisitLockScreen";
import { useEventLog } from "../hooks/useEventLog";
import { clearSession, getSession } from "../state/session";

export function ProductPage() {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();
  const logEvent = useEventLog();

  const [product, setProduct] = useState<Product | null>(null);
  const [productError, setProductError] = useState<string | null>(null);

  const [recommendations, setRecommendations] = useState<RecommendationsResponse | null>(null);
  const [locked, setLocked] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);

  useEffect(() => {
    if (!productId) return;
    let cancelled = false;

    getProduct(productId)
      .then((p) => {
        if (!cancelled) setProduct(p);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setProductError(
          err instanceof ApiError ? err.message : "商品情報の取得に失敗しました。",
        );
      });

    const activeSession = getSession();
    if (!activeSession) {
      setLocked(true);
      return () => {
        cancelled = true;
      };
    }

    getRecommendations(productId, activeSession.sessionId)
      .then((r) => {
        if (!cancelled) setRecommendations(r);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 409) {
          // セッション失効（AC-5）。APIの409を同じロックUIにフォールバックする。
          clearSession();
          setLocked(true);
          return;
        }
        setRecError(
          err instanceof ApiError ? err.message : "関連商品の取得に失敗しました。",
        );
      });

    return () => {
      cancelled = true;
    };
  }, [productId]);

  if (!productId) {
    return <ErrorNotice message="商品IDが指定されていません。" />;
  }

  return (
    <main className="app-shell" data-testid="product-page">
      {productError && <ErrorNotice message={productError} />}

      {product && (
        <section className="product-detail" data-testid="product-detail">
          <ImageWithFallback src={product.image_url} alt={product.name} width={240} height={240} />
          <h1>{product.name}</h1>
          <p>
            {product.cat_large} / {product.cat_mid} / {product.cat_small}・{product.color}
          </p>
          <p className="price" data-testid="product-price">
            ¥{product.price.toLocaleString("ja-JP")}
          </p>
          <p>
            売場: {product.floor}F ゾーン{product.zone}
          </p>
          {product.product_code && (
            <p className="product-code" data-testid="product-code">
              商品番号: {product.product_code}（QR下部に記載）
            </p>
          )}
          <Link
            to={`/route?to_product=${encodeURIComponent(product.product_id)}`}
            className="btn-primary"
            data-testid="product-view-location"
            onClick={() => {
              void logEvent("related_tap", {
                from_product_id: null,
                to_product_id: product.product_id,
                source: "product_self",
              });
            }}
          >
            この商品の場所を見る
          </Link>
        </section>
      )}

      <section aria-labelledby="related-heading">
        <h2 id="related-heading">関連商品</h2>
        {locked && <VisitLockScreen />}
        {recError && <ErrorNotice message={recError} />}
        {!locked && recommendations && (
          <ul className="related-list" data-testid="related-list">
            {recommendations.related.length === 0 && <li>関連商品は見つかりませんでした。</li>}
            {recommendations.related.map((item) => (
              <li key={item.product.product_id} data-testid={`related-item-${item.product.product_id}`}>
                <ImageWithFallback
                  src={item.product.image_url}
                  alt={item.product.name}
                  width={80}
                  height={80}
                />
                <div>
                  <p>{item.product.name}</p>
                  <p>
                    ¥{item.product.price.toLocaleString("ja-JP")}
                    {item.high_lift_low_corate && (
                      <span className="badge" data-testid="high-lift-low-corate-badge">
                        伸びしろ
                      </span>
                    )}
                  </p>
                  <button
                    type="button"
                    className="btn-secondary"
                    data-testid={`related-tap-${item.product.product_id}`}
                    onClick={() => {
                      void logEvent("related_tap", {
                        from_product_id: productId,
                        to_product_id: item.product.product_id,
                        lift: item.lift,
                        score: item.score,
                      });
                      navigate(`/route?to_product=${encodeURIComponent(item.product.product_id)}`);
                    }}
                  >
                    場所を見る
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="coordinates-heading">
        <h2 id="coordinates-heading">この商品を使ったコーディネート</h2>
        {locked && <p>コーディネート提案を見るには来店セッションが必要です。</p>}
        {!locked && recommendations && (
          <ul className="coordinate-list" data-testid="coordinate-list">
            {recommendations.coordinates.length === 0 && <li>この商品を使ったコーディネートはまだありません。</li>}
            {recommendations.coordinates.map((c) => (
              <li key={c.coordinate_id}>
                <Link to={`/coordinates/${c.coordinate_id}`} data-testid={`coordinate-link-${c.coordinate_id}`}>
                  <ImageWithFallback src={c.image_url} alt={c.name} width={160} height={110} />
                  <p>
                    {c.name}（{c.theme}）
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ChatbotLink productId={productId} screen="product_detail" />
    </main>
  );
}
