/**
 * 管理ダッシュボード（`/admin`）向けトークンの保存（フェーズ2-B2）。
 *
 * 来店客のセッション（`state/session.ts`）とは責務・保存対象が異なるため別モジュールにする。
 * `sessionStorage` を使う理由は来店客セッションと同様（タブを閉じれば消える。共有PCでの
 * トークン漏えいを避けるため `localStorage` は使わない）。
 */

const KEY = "rh_admin_token";

function hasSessionStorage(): boolean {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

export function saveAdminToken(token: string): void {
  if (!hasSessionStorage()) return;
  sessionStorage.setItem(KEY, token);
}

export function getAdminToken(): string | null {
  if (!hasSessionStorage()) return null;
  return sessionStorage.getItem(KEY);
}

export function clearAdminToken(): void {
  if (!hasSessionStorage()) return;
  sessionStorage.removeItem(KEY);
}
