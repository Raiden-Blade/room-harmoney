/**
 * 既存チャットボットへの導線（4.4章 / S5）。
 *
 * `VITE_CHATBOT_BASE_URL`（既定は `.env.example` の `CHATBOT_BASE_URL` 相当のダミー値）へ、
 * `../deeplink.ts` のURLスキームに従って `product_id` / `coordinate_id` / `to_product` /
 * `screen` のディープリンクで遷移する。個人情報・購入情報はURLに含めない（9章プライバシー方針）。
 * クリック時に `chatbot_open` を、同じ文脈（product_id/coordinate_id/to_product/screen）を
 * payloadに含めて記録する（フェーズ2-C: 往復導線のため、outboundリンクとイベントで
 * 同一の文脈情報を使う）。
 */
import { buildChatbotOpenPayload, buildChatbotUrl, type DeepLinkScreen } from "../deeplink";
import { useEventLog } from "../hooks/useEventLog";

const CHATBOT_BASE_URL: string =
  (import.meta.env.VITE_CHATBOT_BASE_URL as string | undefined) ?? "https://example.invalid/chatbot";

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
  const href = buildChatbotUrl(CHATBOT_BASE_URL, context);

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
