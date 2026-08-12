/**
 * 既存チャットボットへの導線（4.4章 / S5）。
 *
 * `VITE_CHATBOT_BASE_URL` に実在するHTTP(S)接続先が設定された場合だけ、
 * `../deeplink.ts` のURLスキームに従って `product_id` / `coordinate_id` / `to_product` /
 * `screen` のディープリンクで遷移する。個人情報・購入情報はURLに含めない（9章プライバシー方針）。
 * 未設定または `example.invalid` のダミー値では、誤って接続済みに見せないよう非リンク表示にする。
 * クリック時に `chatbot_open` を、同じ文脈（product_id/coordinate_id/to_product/screen）を
 * payloadに含めて記録する（フェーズ2-C: 往復導線のため、outboundリンクとイベントで
 * 同一の文脈情報を使う）。
 */
import { buildChatbotOpenPayload, buildChatbotUrl, type DeepLinkScreen } from "../deeplink";
import { useEventLog } from "../hooks/useEventLog";

function configuredChatbotBaseUrl(): string | null {
  const raw = (import.meta.env.VITE_CHATBOT_BASE_URL as string | undefined)?.trim();
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    if (!new Set(["http:", "https:"]).has(parsed.protocol) || parsed.hostname === "example.invalid") {
      return null;
    }
    return raw;
  } catch {
    return null;
  }
}

export function ChatbotLink({
  productId,
  coordinateId,
  toProducts,
  screen,
  label = "チャットボットに相談する",
}: {
  productId?: string;
  coordinateId?: string;
  toProducts?: string[];
  screen?: DeepLinkScreen;
  label?: string;
}) {
  const logEvent = useEventLog();
  const context = { productId, coordinateId, toProducts, screen };
  const baseUrl = configuredChatbotBaseUrl();

  if (!baseUrl) {
    return (
      <span className="chatbot-link-unavailable" data-testid="chatbot-link-unavailable" role="status">
        既存チャットボットは接続準備中です
      </span>
    );
  }

  const href = buildChatbotUrl(baseUrl, context);

  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="chatbot-link"
      data-testid="chatbot-link"
      onClick={() => {
        void logEvent("chatbot_open", buildChatbotOpenPayload(context));
      }}
    >
      {label}
    </a>
  );
}
