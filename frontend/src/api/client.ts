/**
 * バックエンドAPI（17章）向けの薄いfetchラッパ。
 *
 * - ベースURLは `VITE_API_BASE_URL`（既定 http://localhost:8000）。
 * - エラー時はバックエンド共通フォーマット（`backend/app/errors.py`）の
 *   `{ code, message }` を持つ `ApiError` を投げる。フロントは `code` で機械的に分岐できる
 *   （例: `VISIT_LOCK_REQUIRED` → 来店ロックUI）。
 */
import type { components } from "./schema";
import type {
  AdminKpiResponse,
  CoordinateDetail,
  Product,
  QrResolution,
  RecommendationsResponse,
  RouteResponse,
  SessionResponse,
  StoreMapFloor,
} from "./types";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // 19章 エッジケース: 通信オフライン
    throw new ApiError(0, "NETWORK_ERROR", "通信エラーが発生しました。電波状況をご確認ください。");
  }

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }

  if (!res.ok) {
    const b = (body ?? {}) as { code?: string; message?: string };
    throw new ApiError(
      res.status,
      b.code ?? "UNKNOWN_ERROR",
      b.message ?? `APIエラー（${res.status}）が発生しました。`,
    );
  }
  return body as T;
}

export function createSession(qrId: string): Promise<SessionResponse> {
  const payload: components["schemas"]["CreateSessionRequest"] = { qr_id: qrId };
  return request<SessionResponse>("/api/session", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resolveQr(qrId: string): Promise<QrResolution> {
  return request<QrResolution>(`/api/qr/${encodeURIComponent(qrId)}`);
}

export function getProduct(productId: string): Promise<Product> {
  return request<Product>(`/api/products/${encodeURIComponent(productId)}`);
}

export function getRecommendations(
  productId: string,
  sessionId?: string | null,
): Promise<RecommendationsResponse> {
  const params = new URLSearchParams({ product_id: productId });
  if (sessionId) params.set("session_id", sessionId);
  return request<RecommendationsResponse>(`/api/recommendations?${params.toString()}`);
}

export function getCoordinate(
  coordinateId: string,
  sessionId?: string | null,
): Promise<CoordinateDetail> {
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  const qs = params.toString();
  return request<CoordinateDetail>(
    `/api/coordinates/${encodeURIComponent(coordinateId)}${qs ? `?${qs}` : ""}`,
  );
}

export function getRoute(
  fromQr: string,
  toProducts: string[],
  sessionId?: string | null,
): Promise<RouteResponse> {
  const params = new URLSearchParams();
  params.set("from_qr", fromQr);
  for (const p of toProducts) params.append("to_product", p);
  if (sessionId) params.set("session_id", sessionId);
  return request<RouteResponse>(`/api/route?${params.toString()}`);
}

export function getStoreMap(floor: number): Promise<StoreMapFloor> {
  return request<StoreMapFloor>(`/api/store-map/${floor}`);
}

/**
 * `GET /api/admin/kpi`（フェーズ2-B2 A/B×KPI管理ダッシュボード・17章「管理系は認証必須」）。
 * `X-Admin-Token` ヘッダーで管理トークンを渡す。トークン不一致/未指定時はバックエンドが
 * 401 `ADMIN_UNAUTHORIZED` を返し、`request()` が `ApiError` として投げる
 * （呼び出し元は `err.status === 401` で来店客向けとは別の再入力UIに分岐する）。
 */
export function getAdminKpi(adminToken: string): Promise<AdminKpiResponse> {
  return request<AdminKpiResponse>("/api/admin/kpi", {
    headers: { "X-Admin-Token": adminToken },
  });
}

export function postEvent(
  sessionId: string,
  eventType: string,
  payload: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
  const body: components["schemas"]["EventRequest"] = {
    session_id: sessionId,
    event_type: eventType,
    payload,
  };
  return request<Record<string, unknown>>("/api/events", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
