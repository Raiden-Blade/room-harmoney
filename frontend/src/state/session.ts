/**
 * 来店セッションの保存（9章 来店ロック / 10章 計測の基盤）。
 *
 * `sessionStorage` を使う前提（要件7章・9章のプライバシー方針: 個人情報/購入情報を
 * URLに載せない）。タブを閉じれば消える＝来店ごとにQR起点からやり直す設計に自然に合致する。
 */

const KEYS = {
  sessionId: "rh_session_id",
  experimentGroup: "rh_experiment_group",
  start: "rh_start",
  qrId: "rh_qr_id",
} as const;

export interface StoredSession {
  sessionId: string;
  experimentGroup: string;
  qrId: string;
  start: { floor: number; x: number; y: number };
}

function hasSessionStorage(): boolean {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

export function saveSession(session: StoredSession): void {
  if (!hasSessionStorage()) return;
  sessionStorage.setItem(KEYS.sessionId, session.sessionId);
  sessionStorage.setItem(KEYS.experimentGroup, session.experimentGroup);
  sessionStorage.setItem(KEYS.qrId, session.qrId);
  sessionStorage.setItem(KEYS.start, JSON.stringify(session.start));
}

export function getSession(): StoredSession | null {
  if (!hasSessionStorage()) return null;
  const sessionId = sessionStorage.getItem(KEYS.sessionId);
  const experimentGroup = sessionStorage.getItem(KEYS.experimentGroup);
  const qrId = sessionStorage.getItem(KEYS.qrId);
  const startRaw = sessionStorage.getItem(KEYS.start);
  if (!sessionId || !experimentGroup || !qrId || !startRaw) return null;
  try {
    const start = JSON.parse(startRaw) as StoredSession["start"];
    return { sessionId, experimentGroup, qrId, start };
  } catch {
    return null;
  }
}

export function clearSession(): void {
  if (!hasSessionStorage()) return;
  for (const key of Object.values(KEYS)) sessionStorage.removeItem(key);
}
