/**
 * ドメインレスポンス型（手書き）。
 *
 * `docs/openapi.json` のレスポンススキーマはバックエンド実装意図（app/schemas.py 冒頭コメント）
 * により `additionalProperties: true` の汎用オブジェクトとして出力されている
 * （バックエンドはリポジトリ/ロジック層の辞書をそのまま返す設計のため）。
 * そのため `openapi-typescript` が生成する `schema.ts` だけではレスポンスの具体的な
 * フィールドが分からない。ここでは `backend/app/routers/*.py` と `backend/app/repositories.py`
 * （= 実装上の真実源）を読んで確認した実際のレスポンス形状を手書きで型定義する。
 * バックエンドが `response_model` を精緻化してOpenAPIに反映した際は、このファイルを
 * `schema.ts` 由来の型に置き換えられるようにレイヤーを分離している。
 */

export interface Product {
  product_id: string;
  name: string;
  cat_large: string;
  cat_mid: string;
  cat_small: string;
  color: string;
  price: number;
  image_url: string;
  floor: number;
  zone: string;
  x: number;
  y: number;
  sub_passage_flag: boolean;
}

export interface RelatedItem {
  product: Product;
  cat_mid: string;
  lift: number;
  high_lift_low_corate: boolean;
  score: number;
}

export interface CoordinateSummary {
  coordinate_id: string;
  name: string;
  theme: string;
  product_ids: string[];
  image_url: string;
  total_price_estimate: number;
}

export interface RecommendationsResponse {
  related: RelatedItem[];
  coordinates: CoordinateSummary[];
}

export interface CoordinateDetail extends CoordinateSummary {
  products: Product[];
}

export interface SessionStart {
  floor: number;
  x: number;
  y: number;
}

export interface SessionResponse {
  session_id: string;
  start: SessionStart;
  floor: number;
  experiment_group: string;
}

export interface QrResolution {
  type: "entrance" | "product";
  product_id: string | null;
  position: { floor: number; x: number; y: number };
  direct_url: string;
}

export interface RouteWaypoint {
  floor: number;
  x: number;
  y: number;
  type: string;
}

export interface RouteSubPassagePoint {
  floor: number;
  x: number;
  y: number;
}

export interface RouteResponse {
  waypoints: RouteWaypoint[];
  sub_passages: RouteSubPassagePoint[];
  visiting_order: string[];
  unreachable: string[];
  total_distance: number;
}

export interface ZoneRect {
  zone: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Zone {
  zone: string;
  floor: number;
  x: number;
  y: number;
}

export interface MapWaypoint {
  id: string;
  floor: number;
  x: number;
  y: number;
  type: string;
}

export interface MapEdge {
  from: string;
  to: string;
  distance: number;
}

export interface SubPassageInfo {
  waypoint_id: string;
  floor: number;
  note: string;
}

export interface StoreMapFloor {
  floor: number;
  floorplan: {
    type: string;
    width: number;
    height: number;
    zones_rect: ZoneRect[];
  };
  zones: Zone[];
  waypoints: MapWaypoint[];
  edges: MapEdge[];
  sub_passages: SubPassageInfo[];
}

/**
 * `GET /api/admin/kpi`（フェーズ2-B1/B2・10章 計測・ログ設計／12章 KPI）のレスポンス型。
 * ここでも `backend/app/analytics.py` の `compute_kpis` を実装上の真実源として手書きする
 * （OpenAPI上は `additionalProperties: true` の汎用オブジェクトのため）。
 */
export type ExperimentGroupKey = "treatment" | "control";

export interface KpiFunnel {
  scanned: number;
  related_viewed: number;
  related_tapped: number;
  route_viewed: number;
  coordinate_viewed: number;
  chatbot_opened: number;
}

export interface KpiRates {
  related_tap_rate: number;
  route_reach_rate: number;
  coordinate_view_rate: number;
  sub_passage_rate: number;
}

export interface KpiGroupResult {
  session_count: number;
  funnel: KpiFunnel;
  rates: KpiRates;
}

export type PosMetricKey = "co_purchase_rate" | "items_per_purchase" | "spend_per_customer";

export type PosMetricValues = Record<PosMetricKey, number | null>;

export interface PosMetricsBlock {
  groups: Record<ExperimentGroupKey, PosMetricValues>;
  diff: Record<PosMetricKey, number | null>;
}

export interface AdminKpiResponse {
  groups: Record<ExperimentGroupKey, KpiGroupResult>;
  diff: KpiRates;
  pos_metrics: PosMetricsBlock | null;
  note: string;
}
