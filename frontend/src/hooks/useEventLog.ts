/**
 * 計測ログ送信の共通フック（10章 計測・ログ設計）。
 *
 * `POST /api/events` は `session_id` 必須。`experiment_group` はサーバ側が
 * セッションから引いて付与する（AC-4）ため、フロントからは送らない。
 * 来店セッションが無い状態（＝来店ロック中）はそもそも計測対象の操作ができないため、
 * セッション未確立時は静かに送信をスキップする（19章: 計測失敗でユーザー体験を止めない）。
 */
import { useCallback } from "react";

import { postEvent } from "../api/client";
import { getSession } from "../state/session";

export type LogEvent = (eventType: string, payload?: Record<string, unknown>) => Promise<void>;

export function useEventLog(): LogEvent {
  return useCallback(async (eventType: string, payload: Record<string, unknown> = {}) => {
    const session = getSession();
    if (!session) return;
    try {
      await postEvent(session.sessionId, eventType, payload);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn(`[useEventLog] failed to log ${eventType}`, err);
    }
  }, []);
}
