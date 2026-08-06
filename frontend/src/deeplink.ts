/**
 * チャットボット双方向ディープリンク仕様（4.4章 / 13章フェーズ2-C）。
 *
 * `docs/` は改変しない運用のため、URLスキームはここに一次情報として集約する。
 * 受け口（inbound: チャットボット→本アプリ）と送り出し（outbound: 本アプリ→チャットボット）の
 * 両方で同じパラメータ名を使うことで、チャットボット側が「開いた時のコンテキスト」を
 * そのまま「戻り先」として再利用できる（往復導線）。すべて純粋関数（DOM/フックに非依存）にして
 * 単体テストしやすくしている。
 *
 * ## パラメータ一覧
 * - `product_id`（単一）: 商品詳細（S2）へのディープリンク。inbound/outbound 双方で使用。
 * - `coordinate_id`（単一）: コーディネート詳細（S3）へのディープリンク。inbound/outbound 双方で使用。
 * - `to_product`（複数可）: ルート表示（S4）へのディープリンク。
 *   inbound では堅牢性のため2形式を両方受け付ける:
 *     1. カンマ区切り単一パラメータ: `?to_product=P001,P002`
 *     2. 同名パラメータの繰り返し: `?to_product=P001&to_product=P002`
 *   （2は `RoutePage` が `URLSearchParams#getAll` で読む既存形式と同じ。）
 *   outbound（チャットボットへ送る側）ではURLを簡潔にするため1のカンマ区切り形式で送る。
 * - `screen`（outboundのみ）: チャットボットを開いた時点の画面名（文脈のヒント）。
 *   inbound側では読まない（本アプリの遷移先は product_id/coordinate_id/to_product のみで決まる）。
 *
 * ## inbound 受け口
 * `ScanPage`（S1）が起動URLのクエリを解決する唯一の受け口。優先順位は
 * `product_id` → `coordinate_id` → `to_product` → （QR直リンク）の順（4.4章・既存挙動を維持）。
 * 来店セッションが無い場合でも遷移自体は行い、遷移先の画面が来店ロックUIを表示する
 * （14章 前提: 受け口の到達性を優先し、ロック判定は各画面の責務に委ねる）。
 */

/** チャットボットを開いた時点の画面名（`chatbot_open` payload の `screen` にも使う）。 */
export type DeepLinkScreen =
  | "scan_entrance"
  | "product_detail"
  | "coordinate_detail"
  | "route"
  | "error";

export interface InboundDeepLink {
  productId: string | null;
  coordinateId: string | null;
  /** 重複除去・順序維持済み。空配列は「指定なし」。 */
  toProducts: string[];
}

export interface OutboundDeepLinkContext {
  productId?: string | null;
  coordinateId?: string | null;
  toProducts?: string[];
  screen?: DeepLinkScreen;
}

/**
 * `to_product` を「カンマ区切り単一パラメータ」「同名パラメータの繰り返し」の両形式から読み取る。
 * 重複は除去し、出現順を維持する。
 */
export function parseToProducts(searchParams: URLSearchParams): string[] {
  const raw = searchParams.getAll("to_product");
  const flattened = raw.flatMap((value) => value.split(","));
  const trimmed = flattened.map((value) => value.trim()).filter((value) => value.length > 0);
  return Array.from(new Set(trimmed));
}

/** inbound ディープリンクのクエリパラメータを解析する（S1 ScanPage が使用）。 */
export function parseInboundDeepLink(searchParams: URLSearchParams): InboundDeepLink {
  return {
    productId: searchParams.get("product_id"),
    coordinateId: searchParams.get("coordinate_id"),
    toProducts: parseToProducts(searchParams),
  };
}

/**
 * `to_product` ディープリンクの遷移先パス（S4 ルート画面）を組み立てる。
 * `RoutePage` は `getAll("to_product")` で読むため、同名パラメータを繰り返す形式で出力する。
 */
export function buildRoutePath(toProducts: string[]): string {
  const params = new URLSearchParams();
  for (const id of toProducts) {
    if (id) params.append("to_product", id);
  }
  return `/route?${params.toString()}`;
}

/** outbound（チャットボットへ送る）ディープリンクのクエリパラメータを組み立てる。 */
export function buildChatbotDeepLinkParams(context: OutboundDeepLinkContext): URLSearchParams {
  const params = new URLSearchParams();
  if (context.productId) params.set("product_id", context.productId);
  if (context.coordinateId) params.set("coordinate_id", context.coordinateId);
  if (context.toProducts && context.toProducts.length > 0) {
    params.set("to_product", context.toProducts.join(","));
  }
  if (context.screen) params.set("screen", context.screen);
  return params;
}

/** チャットボットのベースURLに、現在の文脈をディープリンクとして付与したURLを組み立てる。 */
export function buildChatbotUrl(baseUrl: string, context: OutboundDeepLinkContext): string {
  const qs = buildChatbotDeepLinkParams(context).toString();
  return qs ? `${baseUrl}?${qs}` : baseUrl;
}

/**
 * `chatbot_open` イベントのpayloadを組み立てる（10章 計測）。
 * 個人情報・購入情報は含めない（9章プライバシー方針）。文脈（product_id/coordinate_id/
 * to_product/screen）のみを記録する。
 */
export function buildChatbotOpenPayload(context: OutboundDeepLinkContext): Record<string, unknown> {
  return {
    product_id: context.productId ?? null,
    coordinate_id: context.coordinateId ?? null,
    to_product: context.toProducts && context.toProducts.length > 0 ? context.toProducts : null,
    screen: context.screen ?? null,
  };
}
