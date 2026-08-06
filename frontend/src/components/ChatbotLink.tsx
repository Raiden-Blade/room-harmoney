/**
 * 既存チャットボットへの導線（4.4章 / S5）。
 *
 * `VITE_CHATBOT_BASE_URL`（既定は `.env.example` の `CHATBOT_BASE_URL` 相当のダミー値）へ
 * `?product_id=` / `?coordinate_id=` のディープリンクで遷移する。個人情報・購入情報は
 * URLに含めない（9章プライバシー方針）。クリック時に `chatbot_open` を記録する。
 */
import { useEventLog } from "../hooks/useEventLog";

const CHATBOT_BASE_URL: string =
  (import.meta.env.VITE_CHATBOT_BASE_URL as string | undefined) ?? "https://example.invalid/chatbot";

function buildChatbotUrl(productId?: string, coordinateId?: string): string {
  const params = new URLSearchParams();
  if (productId) params.set("product_id", productId);
  if (coordinateId) params.set("coordinate_id", coordinateId);
  const qs = params.toString();
  return qs ? `${CHATBOT_BASE_URL}?${qs}` : CHATBOT_BASE_URL;
}

export function ChatbotLink({
  productId,
  coordinateId,
  label = "チャットボットに相談する",
}: {
  productId?: string;
  coordinateId?: string;
  label?: string;
}) {
  const logEvent = useEventLog();
  const href = buildChatbotUrl(productId, coordinateId);

  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="chatbot-link"
      data-testid="chatbot-link"
      onClick={() => {
        void logEvent("chatbot_open", { product_id: productId ?? null, coordinate_id: coordinateId ?? null });
      }}
    >
      {label}
    </a>
  );
}
