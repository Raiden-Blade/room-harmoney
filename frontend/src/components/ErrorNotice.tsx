/**
 * 汎用エラー表示（19章 エッジケース: 破損QR・存在しない商品・経路なし・オフライン等）。
 * ユーザーに分かる案内＋チャットボット導線でリカバリできるようにする。
 */
import { ChatbotLink } from "./ChatbotLink";

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="error-notice" role="alert" data-testid="error-notice">
      <p>{message}</p>
      <ChatbotLink label="チャットボットに問い合わせる" />
    </div>
  );
}
