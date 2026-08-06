/**
 * S4 マップ・ルート画面（7章 / DESIGN.md S4）。
 *
 * `GET /api/route` は来店ロック対象（AC-5）で、`route_view` はバックエンドが
 * 呼び出し時に自動記録する（`backend/app/routers/route.py`）ため、フロントから
 * 二重送信はしない。起点はセッション開始QRの起点座標（9章: 精密な現在地測位はしない）。
 * `from_qr` はURLクエリで上書き可能だが、既定はセッションが記憶している起点QRを使う。
 * 複数目的地は `to_product` を複数指定し、`visiting_order`（B2 最近傍法の巡回順）に
 * 従ってピンに番号を振る。複数フロアにまたがる場合はフロア切替ボタンを表示する。
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError, getRoute, getStoreMap, getProduct } from "../api/client";
import type { Product, RouteResponse, StoreMapFloor } from "../api/types";
import { ChatbotLink } from "../components/ChatbotLink";
import { ErrorNotice } from "../components/ErrorNotice";
import { FloorMap, type RouteDestinationPin } from "../components/FloorMap";
import { VisitLockScreen } from "../components/VisitLockScreen";
import { computeFloorTransfers } from "../routeFloorTransfers";
import { clearSession, getSession } from "../state/session";

export function RoutePage() {
  const [searchParams] = useSearchParams();
  const session = getSession();

  const toProducts = useMemo(() => searchParams.getAll("to_product").filter(Boolean), [searchParams]);
  const fromQr = searchParams.get("from_qr") ?? session?.qrId ?? null;

  const [route, setRoute] = useState<RouteResponse | null>(null);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [products, setProducts] = useState<Record<string, Product>>({});
  const [currentFloor, setCurrentFloor] = useState<number | null>(null);
  const [floorData, setFloorData] = useState<StoreMapFloor | null>(null);

  useEffect(() => {
    if (!session) {
      setLocked(true);
      return;
    }
    if (!fromQr || toProducts.length === 0) return;

    let cancelled = false;
    getRoute(fromQr, toProducts, session.sessionId)
      .then(async (r) => {
        if (cancelled) return;
        setRoute(r);
        setCurrentFloor(r.waypoints[0]?.floor ?? session.start.floor);
        const entries = await Promise.all(
          r.visiting_order.map(async (id) => {
            try {
              return [id, await getProduct(id)] as const;
            } catch {
              return null;
            }
          }),
        );
        if (cancelled) return;
        const map: Record<string, Product> = {};
        for (const entry of entries) {
          if (entry) map[entry[0]] = entry[1];
        }
        setProducts(map);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 409) {
          clearSession();
          setLocked(true);
          return;
        }
        setError(err instanceof ApiError ? err.message : "ルートの取得に失敗しました。");
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromQr, toProducts.join(","), session?.sessionId]);

  useEffect(() => {
    if (currentFloor == null) return;
    let cancelled = false;
    getStoreMap(currentFloor)
      .then((f) => {
        if (!cancelled) setFloorData(f);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "フロアマップの取得に失敗しました。");
      });
    return () => {
      cancelled = true;
    };
  }, [currentFloor]);

  if (locked) {
    return <VisitLockScreen />;
  }

  if (!fromQr || toProducts.length === 0) {
    return (
      <main className="app-shell" data-testid="route-no-destination">
        <p>目的地が指定されていません。商品またはコーディネートの詳細画面から「場所を見る」をお試しください。</p>
        <Link to="/scan">QRを読み取る</Link>
      </main>
    );
  }

  if (error) {
    return <ErrorNotice message={error} />;
  }

  if (!route) {
    return (
      <main className="app-shell" data-testid="route-loading">
        <p>ルートを計算しています…</p>
      </main>
    );
  }

  const floorsInRoute = Array.from(new Set(route.waypoints.map((w) => w.floor))).sort((a, b) => a - b);
  // 跨フロア経路の乗換表示（4.3章・フェーズ2-C）: 「◯階→◯階（階段/EV）」。
  // 単一フロアの経路では常に空配列になる。
  const floorTransfers = computeFloorTransfers(route.waypoints);

  const routeWaypointsOnFloor = currentFloor == null ? [] : route.waypoints.filter((w) => w.floor === currentFloor);
  const subPassagesOnFloor =
    currentFloor == null ? [] : route.sub_passages.filter((p) => p.floor === currentFloor);

  const destinations: RouteDestinationPin[] = route.visiting_order
    .map((id, index) => {
      const p = products[id];
      if (!p || p.floor !== currentFloor) return null;
      return { productId: id, name: p.name, x: p.x, y: p.y, order: index + 1 } satisfies RouteDestinationPin;
    })
    .filter((v): v is RouteDestinationPin => v !== null);

  const startOnThisFloor = session && currentFloor === session.start.floor ? session.start : null;

  return (
    <main className="app-shell" data-testid="route-page">
      <h1>店内ルート</h1>

      {floorsInRoute.length > 1 && (
        <div className="floor-switch" data-testid="floor-switch">
          {floorsInRoute.map((f) => (
            <button
              key={f}
              type="button"
              className={f === currentFloor ? "btn-primary" : "btn-secondary"}
              data-testid={`floor-switch-${f}`}
              onClick={() => setCurrentFloor(f)}
            >
              {f}F
            </button>
          ))}
        </div>
      )}

      {floorTransfers.length > 0 && (
        <ul className="floor-transfers" data-testid="floor-transfers">
          {floorTransfers.map((t, index) => (
            <li key={`${t.fromFloor}-${t.toFloor}-${index}`} data-testid={`floor-transfer-${index}`}>
              {t.fromFloor}階→{t.toFloor}階（{t.viaType}）
            </li>
          ))}
        </ul>
      )}

      <ol className="visiting-order" data-testid="visiting-order">
        {route.visiting_order.map((id, index) => (
          <li key={id} data-testid={`visiting-order-item-${id}`}>
            {index + 1}. {products[id]?.name ?? id}
          </li>
        ))}
      </ol>

      {route.unreachable.length > 0 && (
        <p className="warning" data-testid="route-unreachable">
          到達できない目的地があります: {route.unreachable.join(", ")}
        </p>
      )}

      {floorData && (
        <FloorMap
          floorData={floorData}
          routeWaypoints={routeWaypointsOnFloor}
          subPassagePoints={subPassagesOnFloor}
          startPoint={startOnThisFloor}
          destinations={destinations}
        />
      )}

      <ChatbotLink toProducts={toProducts} screen="route" />
    </main>
  );
}
