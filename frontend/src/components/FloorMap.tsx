/**
 * SVGフロアマップ（7.4章 / S4）。
 *
 * フロアプラン（ゾーンの矩形）の上に、起点・目的商品・経由サブ通路をピン表示し、
 * 起点→目的商品のルート線を描画する。複数フロアの場合はフロア単位でこのコンポーネントを
 * 切り替えて使う（階段/EVは type="階段"/"EV" のウェイポイントとして描画する）。
 *
 * 屋内測位は行わない（QR起点方式・9章）ため、座標はすべて `store_map.json` /
 * `products.json` の売場座標（0-100想定のフロア内相対座標）をそのままSVG座標として使う。
 */
import type { MapWaypoint, RouteSubPassagePoint, RouteWaypoint, StoreMapFloor } from "../api/types";

export interface RouteDestinationPin {
  productId: string;
  name: string;
  x: number;
  y: number;
  order: number;
}

export interface FloorMapProps {
  floorData: StoreMapFloor;
  routeWaypoints?: RouteWaypoint[];
  subPassagePoints?: RouteSubPassagePoint[];
  startPoint?: { x: number; y: number } | null;
  destinations?: RouteDestinationPin[];
}

const STAIR_EV_TYPES = new Set(["階段", "EV"]);

function isStairOrEv(wp: MapWaypoint): boolean {
  return STAIR_EV_TYPES.has(wp.type);
}

export function FloorMap({
  floorData,
  routeWaypoints = [],
  subPassagePoints = [],
  startPoint = null,
  destinations = [],
}: FloorMapProps) {
  const { width, height, zones_rect: zonesRect } = floorData.floorplan;
  const stairEvWaypoints = floorData.waypoints.filter(isStairOrEv);

  const routePoints = routeWaypoints.map((w) => `${w.x},${w.y}`).join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      role="img"
      aria-label={`フロア${floorData.floor}のマップ`}
      data-testid="floor-map-svg"
      data-floor={floorData.floor}
    >
      {/* ゾーン矩形 */}
      {zonesRect.map((z) => (
        <g key={z.zone}>
          <rect
            x={z.x}
            y={z.y}
            width={z.w}
            height={z.h}
            className={`zone-rect zone-${z.zone}`}
            data-testid={`zone-rect-${z.zone}`}
            fill={z.zone === "SUB" ? "#ffe0b2" : "#e0e0e0"}
            stroke="#999"
          />
          <text x={z.x + 4} y={z.y + 14} fontSize="6" fill="#333">
            {z.zone === "SUB" ? "サブ通路" : `ゾーン${z.zone}`}
          </text>
        </g>
      ))}

      {/* 階段/EV（複数フロア接続点） */}
      {stairEvWaypoints.map((wp) => (
        <g key={wp.id}>
          <rect
            x={wp.x - 3}
            y={wp.y - 3}
            width={6}
            height={6}
            data-testid={`waypoint-${wp.type}`}
            fill="#616161"
          />
          <text x={wp.x + 4} y={wp.y + 3} fontSize="5" fill="#616161">
            {wp.type}
          </text>
        </g>
      ))}

      {/* ルート線（起点→目的商品、経由サブ通路含む） */}
      {routeWaypoints.length >= 2 && (
        <polyline
          points={routePoints}
          data-testid="route-line"
          fill="none"
          stroke="#aa3bff"
          strokeWidth={1.5}
          strokeDasharray="4 2"
        />
      )}

      {/* 経由サブ通路ピン */}
      {subPassagePoints.map((p, i) => (
        <circle
          key={`sub-${i}`}
          cx={p.x}
          cy={p.y}
          r={3}
          data-testid="route-subpassage"
          fill="#fb8c00"
        />
      ))}

      {/* 起点ピン */}
      {startPoint && (
        <circle
          cx={startPoint.x}
          cy={startPoint.y}
          r={3.5}
          data-testid="route-start"
          fill="#1976d2"
        />
      )}

      {/* 目的商品ピン（巡回順の番号付き） */}
      {destinations.map((d) => (
        <g key={d.productId}>
          <circle
            cx={d.x}
            cy={d.y}
            r={3.5}
            data-testid={`route-destination-${d.productId}`}
            fill="#d32f2f"
          />
          <text x={d.x} y={d.y + 1.5} fontSize="4.5" fill="#fff" textAnchor="middle">
            {d.order}
          </text>
          <text x={d.x + 5} y={d.y - 3} fontSize="5" fill="#d32f2f">
            {d.name}
          </text>
        </g>
      ))}
    </svg>
  );
}
