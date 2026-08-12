/**
 * 商品詳細に埋め込むガイド型チャット。
 *
 * 空欄の自由入力から始めず、1問ずつ選択肢を提示する。キーボード入力と音声入力は同じ
 * `text` APIへ合流させ、入力手段によって推薦ロジックを分岐させない。Web Speech APIは
 * 対応ブラウザだけに段階的に表示し、非対応端末でも主要フローを失わない。
 */
import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, postChatTurn } from "../api/client";
import type { ChatMode, ChatState, ChatTurnResponse } from "../api/types";
import { useEventLog } from "../hooks/useEventLog";
import { clearSession } from "../state/session";
import { ImageWithFallback } from "./ImageWithFallback";

interface SpeechRecognitionEventLike {
  results: ArrayLike<{ 0: { transcript: string } }>;
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

const EMPTY_STATE: ChatState = { answered_question_ids: [], preferences: {} };

function speechRecognitionConstructor(): SpeechRecognitionConstructor | undefined {
  if (typeof window === "undefined") return undefined;
  const speechWindow = window as typeof window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
}

export function ChatbotPanel({ productId, sessionId }: { productId: string; sessionId: string }) {
  const navigate = useNavigate();
  const logEvent = useEventLog();
  const [mode, setMode] = useState<ChatMode>("customer");
  const [response, setResponse] = useState<ChatTurnResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const SpeechRecognition = useMemo(() => speechRecognitionConstructor(), []);

  async function send(
    action: "start" | "answer" | "skip" | "finish",
    values: { answerId?: string; textValue?: string } = {},
  ) {
    setLoading(true);
    setError(null);
    try {
      const next = await postChatTurn(sessionId, {
        product_id: productId,
        action,
        question_id: action === "start" ? undefined : response?.question?.question_id,
        answer_id: values.answerId,
        text: values.textValue,
        mode,
        state: action === "start" ? EMPTY_STATE : (response?.state ?? EMPTY_STATE),
      });
      setResponse(next);
      setText("");
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        clearSession();
        setError("来店セッションの有効期限が切れました。店頭QRをもう一度読み取ってください。");
      } else {
        setError(err instanceof ApiError ? err.message : "相談結果の取得に失敗しました。");
      }
    } finally {
      setLoading(false);
    }
  }

  function start() {
    setOpen(true);
    void send("start");
  }

  function submitText(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || !response?.question) return;
    void send("answer", { textValue: text.trim() });
  }

  function startVoiceInput() {
    if (!SpeechRecognition || listening) return;
    const recognition = new SpeechRecognition();
    recognition.lang = "ja-JP";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript ?? "";
      setText(transcript);
    };
    recognition.onerror = () => {
      setListening(false);
      setError("音声を認識できませんでした。選択肢またはキーボード入力をご利用ください。");
    };
    recognition.onend = () => setListening(false);
    setListening(true);
    recognition.start();
  }

  function openRoute(productIds: string[]) {
    const uniqueIds = Array.from(new Set([productId, ...productIds])).slice(0, 4);
    void logEvent("chatbot_recommendation_tap", {
      from_product_id: productId,
      to_product_ids: uniqueIds,
      source: "guided_chatbot",
    });
    const params = new URLSearchParams();
    for (const id of uniqueIds) params.append("to_product", id);
    navigate(`/route?${params.toString()}`);
  }

  if (!open) {
    return (
      <section className="chatbot-panel chatbot-panel-intro" aria-labelledby="chatbot-heading">
        <div>
          <p className="chatbot-eyebrow">お部屋コーディネートガイド</p>
          <h2 id="chatbot-heading">3問以内でコーディネート相談</h2>
          <p>選択肢に答えるだけで、関連商品と売場ルートを絞り込みます。</p>
        </div>
        <fieldset className="chatbot-mode" aria-label="利用モード">
          <legend>利用モード</legend>
          <button
            type="button"
            className={mode === "customer" ? "btn-primary" : "btn-secondary"}
            onClick={() => setMode("customer")}
          >
            お客様向け
          </button>
          <button
            type="button"
            className={mode === "staff" ? "btn-primary" : "btn-secondary"}
            onClick={() => setMode("staff")}
          >
            スタッフ向け
          </button>
        </fieldset>
        <button type="button" className="btn-primary" data-testid="chatbot-start" onClick={start}>
          相談を始める
        </button>
      </section>
    );
  }

  return (
    <section className="chatbot-panel" aria-labelledby="chatbot-heading" data-testid="chatbot-panel">
      <header className="chatbot-header">
        <div>
          <p className="chatbot-eyebrow">お部屋コーディネートガイド</p>
          <h2 id="chatbot-heading">コーディネート相談</h2>
        </div>
        <span className="chatbot-mode-label">{mode === "staff" ? "スタッフ向け" : "お客様向け"}</span>
      </header>

      {loading && !response && <p role="status">候補を準備しています…</p>}
      {error && <p className="chatbot-error" role="alert">{error}</p>}

      {response && (
        <>
          <div className="chatbot-message" aria-live="polite">
            <p>{response.message}</p>
          </div>

          {response.question && !response.completed && (
            <div className="chatbot-question" data-testid="chatbot-question">
              <p className="chatbot-progress">
                質問 {response.state.answered_question_ids.length + 1} / 最大3
              </p>
              <h3>{response.question.text}</h3>
              <p className="hint">{response.question.reason}</p>
              <div className="chatbot-options">
                {response.question.options.map((option) => (
                  <button
                    type="button"
                    key={option.option_id}
                    disabled={loading}
                    onClick={() => void send("answer", { answerId: option.option_id })}
                  >
                    <strong>{option.label}</strong>
                    <span>{option.description}</span>
                  </button>
                ))}
              </div>
              <form className="chatbot-free-input" onSubmit={submitText}>
                <label htmlFor="chatbot-text">短い言葉で入力する</label>
                <div>
                  <input
                    id="chatbot-text"
                    value={text}
                    maxLength={200}
                    placeholder="例：価格を抑えたい"
                    onChange={(event) => setText(event.target.value)}
                  />
                  {SpeechRecognition && (
                    <button
                      type="button"
                      className="btn-secondary"
                      aria-label="音声で入力"
                      onClick={startVoiceInput}
                      disabled={listening}
                    >
                      {listening ? "聞き取り中…" : "音声"}
                    </button>
                  )}
                  <button type="submit" className="btn-secondary" disabled={!text.trim() || loading}>
                    送信
                  </button>
                </div>
              </form>
              <div className="chatbot-secondary-actions">
                <button type="button" onClick={() => void send("skip")} disabled={loading}>
                  この質問をスキップ
                </button>
                <button type="button" onClick={() => void send("finish")} disabled={loading}>
                  ここで候補を見る
                </button>
              </div>
            </div>
          )}

          {response.recommendations.length > 0 && (
            <div className="chatbot-results">
              <h3>{response.completed ? "現在のおすすめ" : "現在の候補（回答するたびに更新）"}</h3>
              <ul className="chatbot-product-list">
                {response.recommendations.slice(0, 3).map((item) => (
                  <li key={item.product.product_id}>
                    <ImageWithFallback
                      src={item.product.image_url}
                      alt={item.product.name}
                      width={72}
                      height={72}
                    />
                    <div>
                      <strong>{item.product.name}</strong>
                      <p className="price">¥{item.product.price.toLocaleString("ja-JP")}</p>
                      <p className="chatbot-reason">{item.reasons.slice(0, 2).join("／")}</p>
                      <button
                        type="button"
                        className="chatbot-text-button"
                        onClick={() => openRoute([item.product.product_id])}
                      >
                        この売場を見る
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {response.route_product_ids.length > 0 && (
            <button
              type="button"
              className="btn-primary chatbot-route-button"
              data-testid="chatbot-bundle-route"
              onClick={() => openRoute(response.route_product_ids)}
            >
              おすすめをまとめて売場で見る
            </button>
          )}

          <details className="chatbot-data-notice">
            <summary>提案データについて</summary>
            <p>{response.data_notice}</p>
          </details>
          <button type="button" className="chatbot-restart" onClick={() => void send("start")} disabled={loading}>
            条件を最初から選び直す
          </button>
        </>
      )}
    </section>
  );
}
