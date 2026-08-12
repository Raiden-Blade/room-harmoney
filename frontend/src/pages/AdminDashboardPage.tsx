/**
 * A/B×KPI管理ダッシュボード画面（フェーズ2-B2 / 10章 計測・ログ設計 / 12章 KPI / 20章 PM兼効果検証）。
 *
 * `GET /api/admin/kpi`（P2-B1）を可視化する **内部向け（店舗スタッフ/PM・効果検証担当者）画面**。
 * 来店客向けのS1〜S5フローとは別導線（`/admin` 直リンク前提、顧客向けQR等からはリンクしない）。
 *
 * 認証は17章「管理系（データ投入・ダッシュボード）は認証必須」を受けたバックエンドの
 * 共有トークン方式（`X-Admin-Token`、`backend/app/dependencies.py` 参照）に合わせ、
 * 画面上部のトークン入力欄から取得したトークンをヘッダーに載せて呼び出す。
 * トークンは `sessionStorage`（`state/adminAuth.ts`）に保持し、タブを閉じれば消える
 * （来店客の来店ロック画面とは別のUIで、未入力/認証エラーを案内する）。
 *
 * 因果の扱い（10章コメント／`backend/app/analytics.py` 参照）: 本画面はA/B割付
 * （`experiment_group`）を前提にした群間の記述統計（率・差分）を表示するのみであり、
 * 割付が崩れている場合の解釈上の注意はAPIレスポンスの `note` をそのまま表示して伝える。
 */
import { type FormEvent, useEffect, useState } from "react";

import { ApiError, getAdminKpi } from "../api/client";
import type {
  AdminKpiResponse,
  ExperimentGroupKey,
  KpiFunnel,
  KpiRates,
  PosMetricKey,
} from "../api/types";
import { KpiBarChart } from "../components/KpiBarChart";
import { clearAdminToken, getAdminToken, saveAdminToken } from "../state/adminAuth";

const GROUP_LABEL: Record<ExperimentGroupKey, string> = {
  treatment: "ガイド型チャット群（treatment）",
  control: "既存フロー群（control）",
};

const FUNNEL_STAGES: { key: keyof KpiFunnel; label: string }[] = [
  { key: "scanned", label: "QRスキャン" },
  { key: "related_viewed", label: "関連商品表示" },
  { key: "related_tapped", label: "関連商品タップ" },
  { key: "route_viewed", label: "ルート表示" },
];

const RATE_STAGES: { key: keyof KpiRates; label: string }[] = [
  { key: "related_tap_rate", label: "関連タップ率" },
  { key: "route_reach_rate", label: "ルート到達率" },
  { key: "coordinate_view_rate", label: "コーディネート閲覧率" },
  { key: "sub_passage_rate", label: "サブ通路通過率" },
];

const POS_METRICS: { key: PosMetricKey; label: string }[] = [
  { key: "co_purchase_rate", label: "併売率" },
  { key: "items_per_purchase", label: "買上点数" },
  { key: "spend_per_customer", label: "客単価" },
];

const CHATBOT_RATE_STAGES = [
  { key: "answer_rate", label: "回答到達率" },
  { key: "recommendation_tap_rate", label: "チャット提案タップ率" },
  { key: "completion_rate", label: "3問以内の完了率" },
] as const;

// 現状の感覚値（要件書10章の補足文脈・サブ通路通過率の目安）。実測との比較用の参考線。
const SUB_PASSAGE_REFERENCE_RATE = 0.1;

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatDiffPercentPoint(value: number): string {
  const pct = value * 100;
  const fixed = pct.toFixed(1);
  if (pct > 0) return `+${fixed}pt`;
  if (pct < 0) return `${fixed}pt`;
  return `±0.0pt`;
}

function formatCount(value: number): string {
  return `${value}件`;
}

function formatPosValue(key: PosMetricKey, value: number): string {
  if (key === "co_purchase_rate") return formatPercent(value);
  if (key === "items_per_purchase") return `${value.toFixed(2)}点`;
  return `¥${Math.round(value).toLocaleString("ja-JP")}`;
}

function formatPosDiff(key: PosMetricKey, value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "±";
  const abs = Math.abs(value);
  if (key === "co_purchase_rate") return `${sign}${(abs * 100).toFixed(1)}pt`;
  if (key === "items_per_purchase") return `${sign}${abs.toFixed(2)}点`;
  return `${sign}¥${Math.round(abs).toLocaleString("ja-JP")}`;
}

function diffClassName(value: number): string {
  if (value > 0) return "kpi-diff kpi-diff-positive";
  if (value < 0) return "kpi-diff kpi-diff-negative";
  return "kpi-diff kpi-diff-neutral";
}

function isEmptyResult(kpi: AdminKpiResponse): boolean {
  const groups = Object.values(kpi.groups);
  return groups.every(
    (g) => g.session_count === 0 && Object.values(g.funnel).every((v) => v === 0),
  );
}

export function AdminDashboardPage() {
  const [tokenInput, setTokenInput] = useState("");
  const [kpi, setKpi] = useState<AdminKpiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [authRequired, setAuthRequired] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [otherError, setOtherError] = useState<string | null>(null);

  function fetchKpi(token: string) {
    setLoading(true);
    setAuthError(null);
    setOtherError(null);
    getAdminKpi(token)
      .then((data) => {
        setKpi(data);
        setAuthRequired(false);
        saveAdminToken(token);
      })
      .catch((err: unknown) => {
        setKpi(null);
        if (err instanceof ApiError && err.status === 401) {
          clearAdminToken();
          setAuthRequired(true);
          setAuthError(err.message);
        } else {
          setAuthRequired(false);
          setOtherError(err instanceof ApiError ? err.message : "KPIの取得に失敗しました。");
        }
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    const saved = getAdminToken();
    if (saved) {
      setTokenInput(saved);
      fetchKpi(saved);
    }
    // 初回マウント時のみ（保存済みトークンがあれば自動取得）。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = tokenInput.trim();
    if (!trimmed) {
      setKpi(null);
      setAuthRequired(true);
      setAuthError(null);
      return;
    }
    fetchKpi(trimmed);
  }

  return (
    <main className="app-shell admin-dashboard" data-testid="admin-dashboard-page">
      <h1>A/B×KPI管理ダッシュボード</h1>
      <p className="admin-notice" role="note" data-testid="admin-notice">
        この画面は店舗スタッフ・PM／効果検証担当者向けの内部管理画面です。来店されたお客様向けの画面ではありません。
      </p>

      <form className="admin-token-form" data-testid="admin-token-form" onSubmit={handleSubmit}>
        <label htmlFor="admin-token-input">管理トークン</label>
        <div className="admin-token-form-row">
          <input
            id="admin-token-input"
            data-testid="admin-token-input"
            type="password"
            autoComplete="off"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="X-Admin-Token"
          />
          <button type="submit" className="btn-primary" data-testid="admin-token-submit">
            KPIを取得
          </button>
        </div>
      </form>

      {loading && (
        <p data-testid="admin-kpi-loading" aria-live="polite">
          KPIを取得しています…
        </p>
      )}

      {!loading && authError && (
        <div className="admin-auth-error" role="alert" data-testid="admin-auth-error">
          <p>入力された管理トークンが正しくありません。管理トークンを入力してください。</p>
          <p className="hint">{authError}</p>
        </div>
      )}

      {!loading && !authError && authRequired && !kpi && (
        <p data-testid="admin-token-prompt">管理トークンを入力してください。</p>
      )}

      {!loading && otherError && (
        <div className="admin-kpi-error" role="alert" data-testid="admin-kpi-error">
          <p>{otherError}</p>
        </div>
      )}

      {!loading && kpi && (
        <div className="admin-kpi-content" data-testid="admin-kpi-content">
          {isEmptyResult(kpi) ? (
            <p data-testid="admin-kpi-empty">
              対象期間のイベントデータがありません（利用群・非利用群とも0件）。
            </p>
          ) : (
            <>
              <section data-testid="admin-session-counts">
                <h2>セッション数</h2>
                <ul>
                  {(Object.keys(kpi.groups) as ExperimentGroupKey[]).map((group) => (
                    <li key={group} data-testid={`session-count-${group}`}>
                      {GROUP_LABEL[group]}: {kpi.groups[group].session_count}件
                    </li>
                  ))}
                </ul>
              </section>

              <section data-testid="admin-funnel-section">
                <h2>ファネル（QRスキャン→関連商品表示→タップ→ルート表示）</h2>
                <KpiBarChart
                  title="群別ファネル（件数）"
                  testIdPrefix="kpi-funnel"
                  formatValue={formatCount}
                  items={FUNNEL_STAGES.map((stage) => ({
                    key: stage.key,
                    label: stage.label,
                    treatment: kpi.groups.treatment.funnel[stage.key],
                    control: kpi.groups.control.funnel[stage.key],
                  }))}
                />
              </section>

              <section data-testid="admin-rates-section">
                <h2>主要な率（A/B差分）</h2>
                <KpiBarChart
                  title="群別の主要な率"
                  testIdPrefix="kpi-rates"
                  formatValue={formatPercent}
                  maxValue={1}
                  items={RATE_STAGES.map((stage) => ({
                    key: stage.key,
                    label: stage.label,
                    treatment: kpi.groups.treatment.rates[stage.key],
                    control: kpi.groups.control.rates[stage.key],
                  }))}
                />

                <table className="kpi-table" data-testid="kpi-rates-table">
                  <thead>
                    <tr>
                      <th scope="col">指標</th>
                      <th scope="col">{GROUP_LABEL.treatment}</th>
                      <th scope="col">{GROUP_LABEL.control}</th>
                      <th scope="col">差分（treatment − control）</th>
                    </tr>
                  </thead>
                  <tbody>
                    {RATE_STAGES.map((stage) => {
                      const diff = kpi.diff[stage.key];
                      return (
                        <tr key={stage.key} data-testid={`rate-row-${stage.key}`}>
                          <th scope="row">{stage.label}</th>
                          <td data-testid={`rate-row-${stage.key}-treatment`}>
                            {formatPercent(kpi.groups.treatment.rates[stage.key])}
                          </td>
                          <td data-testid={`rate-row-${stage.key}-control`}>
                            {formatPercent(kpi.groups.control.rates[stage.key])}
                          </td>
                          <td
                            className={diffClassName(diff)}
                            data-testid={`rate-row-${stage.key}-diff`}
                          >
                            {formatDiffPercentPoint(diff)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </section>

              <section
                className="sub-passage-highlight"
                data-testid="sub-passage-highlight"
                aria-label="サブ通路通過率（現状の感覚値10%との比較）"
              >
                <h2>サブ通路通過率</h2>
                <p className="hint">
                  ルート案内を表示したセッションのうち、サブ通路（関連商品集積エリア）を経由した割合。
                  現状の感覚値（{formatPercent(SUB_PASSAGE_REFERENCE_RATE)}）との比較用に大きく表示しています。
                </p>
                <div className="sub-passage-values">
                  {(Object.keys(kpi.groups) as ExperimentGroupKey[]).map((group) => (
                    <div key={group} className="sub-passage-value" data-testid={`sub-passage-rate-${group}`}>
                      <span className="sub-passage-value-label">{GROUP_LABEL[group]}</span>
                      <span className="sub-passage-value-number">
                        {formatPercent(kpi.groups[group].rates.sub_passage_rate)}
                      </span>
                      <span className="hint">
                        感覚値比:{" "}
                        {formatDiffPercentPoint(
                          kpi.groups[group].rates.sub_passage_rate - SUB_PASSAGE_REFERENCE_RATE,
                        )}
                      </span>
                    </div>
                  ))}
                  <div className="sub-passage-value" data-testid="sub-passage-rate-diff">
                    <span className="sub-passage-value-label">A/B差分</span>
                    <span className={diffClassName(kpi.diff.sub_passage_rate)}>
                      {formatDiffPercentPoint(kpi.diff.sub_passage_rate)}
                    </span>
                  </div>
                </div>
              </section>

              <section data-testid="admin-pos-section">
                <h2>POS突合（併売率・買上点数・客単価）</h2>
                {(() => {
                  const posMetrics = kpi.pos_metrics;
                  if (!posMetrics) {
                    return <p data-testid="pos-metrics-na">POSデータ未連携（N/A）</p>;
                  }
                  return (
                    <table className="kpi-table" data-testid="pos-metrics">
                      <thead>
                        <tr>
                          <th scope="col">指標</th>
                          <th scope="col">{GROUP_LABEL.treatment}</th>
                          <th scope="col">{GROUP_LABEL.control}</th>
                          <th scope="col">差分</th>
                        </tr>
                      </thead>
                      <tbody>
                        {POS_METRICS.map((metric) => {
                          const treatmentValue = posMetrics.groups.treatment[metric.key];
                          const controlValue = posMetrics.groups.control[metric.key];
                          const diff = posMetrics.diff[metric.key];
                          return (
                          <tr key={metric.key} data-testid={`pos-row-${metric.key}`}>
                            <th scope="row">{metric.label}</th>
                            <td data-testid={`pos-row-${metric.key}-treatment`}>
                              {treatmentValue == null ? "N/A" : formatPosValue(metric.key, treatmentValue)}
                            </td>
                            <td data-testid={`pos-row-${metric.key}-control`}>
                              {controlValue == null ? "N/A" : formatPosValue(metric.key, controlValue)}
                            </td>
                            <td
                              className={diff == null ? "kpi-diff" : diffClassName(diff)}
                              data-testid={`pos-row-${metric.key}-diff`}
                            >
                              {diff == null ? "N/A" : formatPosDiff(metric.key, diff)}
                            </td>
                          </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  );
                })()}
              </section>

              {kpi.chatbot_metrics && (
                <section data-testid="admin-chatbot-section">
                  <h2>ガイド型チャットの中間指標</h2>
                  <KpiBarChart
                    title="群別チャット指標"
                    testIdPrefix="kpi-chatbot"
                    formatValue={formatPercent}
                    maxValue={1}
                    items={CHATBOT_RATE_STAGES.map((stage) => ({
                      key: stage.key,
                      label: stage.label,
                      treatment: kpi.chatbot_metrics!.groups.treatment.rates[stage.key],
                      control: kpi.chatbot_metrics!.groups.control.rates[stage.key],
                    }))}
                  />
                  <p className="hint">{kpi.chatbot_metrics.note}</p>
                </section>
              )}

              <p className="causal-note hint" data-testid="causal-note">
                {kpi.note}
              </p>
            </>
          )}
        </div>
      )}
    </main>
  );
}
