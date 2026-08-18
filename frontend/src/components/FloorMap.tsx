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
import { getDestinationLabelLayout } from "./floorMapLayout";

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
const DESTINATION_LABEL_FONT_SIZE = 5;

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
      {/* ゾーン矩形（docs/DESIGN_SYSTEM.md §1: 通常ゾーン=--rh-surface-alt、サブ通路=--rh-badge-bg/text） */}
      {zonesRect.map((z) => (
        <g key={z.zone}>
          <rect
            x={z.x}
            y={z.y}
            width={z.w}
            height={z.h}
            className={`zone-rect zone-${z.zone}`}
            data-testid={`zone-rect-${z.zone}`}
            fill={z.zone === "SUB" ? "#fff1e8" : "#f5f5f5"}
            stroke={z.zone === "SUB" ? "#c05621" : "#e1e1e1"}
          />
          <text
            x={z.zone === "SUB" ? z.x + z.w / 2 : z.x + 3}
            y={z.y + 8}
            fontSize={z.zone === "SUB" ? "3.5" : "4"}
            fontWeight="600"
            textAnchor={z.zone === "SUB" ? "middle" : "start"}
            fill="#5f6368"
          >
            {z.zone === "SUB" ? "サブ" : `ゾーン${z.zone}`}
          </text>
        </g>
      ))}

      {/* ルート線（起点→目的商品、経由サブ通路含む）: --rh-brand・太め・実線 */}
      {routeWaypoints.length >= 2 && (
        <polyline
          points={routePoints}
          data-testid="route-line"
          fill="none"
          stroke="#009e96"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}

      {/* 階段/EVはルートより手前に描き、近接する2ラベルを左右へ分離する。 */}
      {stairEvWaypoints.map((wp) => {
        const placeOnLeft = wp.type === "階段";
        return (
          <g key={wp.id} data-testid={`waypoint-group-${wp.type}`}>
            <rect
              x={wp.x - 3}
              y={wp.y - 3}
              width={6}
              height={6}
              data-testid={`waypoint-${wp.type}`}
              fill="#6d6d6d"
              stroke="#ffffff"
              strokeWidth={1}
            />
            <text
              x={wp.x + (placeOnLeft ? -5 : 5)}
              y={wp.y - 5}
              fontSize="5"
              fontWeight="700"
              textAnchor={placeOnLeft ? "end" : "start"}
              fill="#4f4f4f"
              stroke="#ffffff"
              strokeWidth="2"
              strokeLinejoin="round"
              paintOrder="stroke"
            >
              {wp.type}
            </text>
          </g>
        );
      })}

      {/* 経由サブ通路ピン: 淡色＋破線（--rh-badge-bg/--rh-badge-text） */}
      {subPassagePoints.map((p, i) => (
        <circle
          key={`sub-${i}`}
          cx={p.x}
          cy={p.y}
          r={3}
          data-testid="route-subpassage"
          fill="#fff1e8"
          stroke="#c05621"
          strokeWidth={1}
          strokeDasharray="1.5 1"
        />
      ))}

      {/* 起点ピン（--rh-heading・濃紺） */}
      {startPoint && (
        <circle
          cx={startPoint.x}
          cy={startPoint.y}
          r={3.5}
          data-testid="route-start"
          fill="#14293a"
        />
      )}

      {/* 目的商品ピン（巡回順の番号付き）: --rh-price */}
      {destinations.map((d) => {
        const containingZone = zonesRect.find(
          (zone) => d.x >= zone.x && d.x <= zone.x + zone.w && d.y >= zone.y && d.y <= zone.y + zone.h,
        );
        const label = getDestinationLabelLayout(d, width, height, containingZone);
        return (
          <g key={d.productId} aria-label={`${d.order}. ${d.name}`}>
            <title>{`${d.order}. ${d.name}`}</title>
            <circle
              cx={d.x}
              cy={d.y}
              r={3.5}
              data-testid={`route-destination-${d.productId}`}
              fill="#e8352a"
              stroke="#ffffff"
              strokeWidth={1}
            />
            <text x={d.x} y={d.y + 1.5} fontSize="4.5" fill="#fff" textAnchor="middle">
              {d.order}
            </text>
            <text
              x={label.x}
              y={label.y}
              data-testid={`route-destination-label-${d.productId}`}
              fontSize={DESTINATION_LABEL_FONT_SIZE}
              fontWeight="700"
              fill="#c62820"
              stroke="#ffffff"
              strokeWidth="2"
              strokeLinejoin="round"
              paintOrder="stroke"
              textAnchor={label.textAnchor}
            >
              {label.text}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
