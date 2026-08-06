import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock, route } from "../../test/mockFetch";
import { AdminDashboardPage } from "../AdminDashboardPage";

const VALID_TOKEN = "correct-admin-token";

function kpiResponse(overrides: Record<string, unknown> = {}) {
  return {
    groups: {
      treatment: {
        session_count: 40,
        funnel: {
          scanned: 40,
          related_viewed: 30,
          related_tapped: 18,
          route_viewed: 12,
          coordinate_viewed: 5,
          chatbot_opened: 2,
        },
        rates: {
          related_tap_rate: 0.6,
          route_reach_rate: 0.3,
          coordinate_view_rate: 0.125,
          sub_passage_rate: 0.25,
        },
      },
      control: {
        session_count: 35,
        funnel: {
          scanned: 35,
          related_viewed: 20,
          related_tapped: 8,
          route_viewed: 7,
          coordinate_viewed: 2,
          chatbot_opened: 1,
        },
        rates: {
          related_tap_rate: 0.4,
          route_reach_rate: 0.2,
          coordinate_view_rate: 0.0571,
          sub_passage_rate: 0.1,
        },
      },
    },
    diff: {
      related_tap_rate: 0.2,
      route_reach_rate: 0.1,
      coordinate_view_rate: 0.0679,
      sub_passage_rate: 0.15,
    },
    pos_metrics: null,
    note: "この集計は experiment_group による A/B割付を前提とした群間比較です。",
    ...overrides,
  };
}

function renderAdminPage() {
  return render(
    <MemoryRouter initialEntries={["/admin"]}>
      <Routes>
        <Route path="/admin" element={<AdminDashboardPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function enterTokenAndSubmit(token: string) {
  fireEvent.change(screen.getByTestId("admin-token-input"), { target: { value: token } });
  fireEvent.click(screen.getByTestId("admin-token-submit"));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AdminDashboardPage（フェーズ2-B2 A/B×KPI管理ダッシュボード）", () => {
  it("トークン未入力時はKPIを取得せず、来店客向けロック画面とは別の入力促しUIを表示する", () => {
    const { fetchMock } = installFetchMock([]);

    renderAdminPage();

    expect(screen.getByTestId("admin-notice")).toHaveTextContent(
      "店舗スタッフ・PM／効果検証担当者向けの内部管理画面です",
    );
    expect(screen.getByTestId("admin-token-prompt")).toHaveTextContent("管理トークンを入力してください。");
    expect(screen.queryByTestId("admin-kpi-content")).not.toBeInTheDocument();
    expect(screen.queryByTestId("visit-lock")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("正しいトークンでKPIを取得し、群別ファネル・率・diff（符号付き）・サブ通路通過率が描画される", async () => {
    installFetchMock([
      route("GET", "/api/admin/kpi", (_url, init) => {
        const headers = (init?.headers ?? {}) as Record<string, string>;
        if (headers["X-Admin-Token"] !== VALID_TOKEN) {
          return {
            status: 401,
            body: { code: "ADMIN_UNAUTHORIZED", message: "管理系APIの認証に失敗しました。" },
          };
        }
        return { body: kpiResponse() };
      }),
    ]);

    renderAdminPage();
    enterTokenAndSubmit(VALID_TOKEN);

    expect(await screen.findByTestId("admin-kpi-content")).toBeInTheDocument();

    // セッション数
    expect(screen.getByTestId("session-count-treatment")).toHaveTextContent("40件");
    expect(screen.getByTestId("session-count-control")).toHaveTextContent("35件");

    // 率テーブル＋diff（正=改善方向、符号付き）
    expect(screen.getByTestId("rate-row-related_tap_rate-treatment")).toHaveTextContent("60.0%");
    expect(screen.getByTestId("rate-row-related_tap_rate-control")).toHaveTextContent("40.0%");
    expect(screen.getByTestId("rate-row-related_tap_rate-diff")).toHaveTextContent("+20.0pt");
    expect(screen.getByTestId("rate-row-related_tap_rate-diff")).toHaveClass("kpi-diff-positive");

    // サブ通路通過率（現状感覚値10%との比較ができるよう大きく表示）
    expect(screen.getByTestId("sub-passage-rate-treatment")).toHaveTextContent("25.0%");
    expect(screen.getByTestId("sub-passage-rate-control")).toHaveTextContent("10.0%");
    expect(screen.getByTestId("sub-passage-rate-diff")).toHaveTextContent("+15.0pt");

    // POS未連携時はN/A表示
    expect(screen.getByTestId("pos-metrics-na")).toHaveTextContent("POSデータ未連携（N/A）");
    expect(screen.queryByTestId("pos-metrics")).not.toBeInTheDocument();

    // 因果注記（A/B前提・単純比較でない旨）
    expect(screen.getByTestId("causal-note")).toHaveTextContent("A/B割付を前提とした群間比較");
  });

  it("インラインSVG棒グラフがファネル・率それぞれ群数×指標数ぶん描画される（外部ライブラリ不使用）", async () => {
    installFetchMock([route("GET", "/api/admin/kpi", () => ({ body: kpiResponse() }))]);

    renderAdminPage();
    enterTokenAndSubmit(VALID_TOKEN);
    await screen.findByTestId("admin-kpi-content");

    const funnelSvg = screen.getByTestId("kpi-funnel-svg");
    expect(funnelSvg.tagName.toLowerCase()).toBe("svg");
    // ファネル4段階 × (treatment/control) = 8本のバー
    expect(funnelSvg.querySelectorAll("rect[data-testid^='kpi-funnel-bar-']")).toHaveLength(8);
    expect(screen.getByTestId("kpi-funnel-bar-treatment-scanned")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("40件"),
    );
    expect(screen.getByTestId("kpi-funnel-bar-control-scanned")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("35件"),
    );

    const ratesSvg = screen.getByTestId("kpi-rates-svg");
    // 主要な率4指標 × (treatment/control) = 8本のバー
    expect(ratesSvg.querySelectorAll("rect[data-testid^='kpi-rates-bar-']")).toHaveLength(8);
    expect(screen.getByTestId("kpi-rates-bar-treatment-related_tap_rate")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("60.0%"),
    );
  });

  it("POSデータがある場合は併売率・買上点数・客単価とdiffが群別に表示される", async () => {
    installFetchMock([
      route("GET", "/api/admin/kpi", () => ({
        body: kpiResponse({
          pos_metrics: {
            groups: {
              treatment: { co_purchase_rate: 0.32, items_per_purchase: 2.4, spend_per_customer: 8200 },
              control: { co_purchase_rate: 0.2, items_per_purchase: 2.1, spend_per_customer: 7600 },
            },
            diff: {
              co_purchase_rate: 0.12,
              items_per_purchase: 0.3,
              spend_per_customer: 600,
            },
          },
        }),
      })),
    ]);

    renderAdminPage();
    enterTokenAndSubmit(VALID_TOKEN);

    expect(await screen.findByTestId("pos-metrics")).toBeInTheDocument();
    expect(screen.getByTestId("pos-row-co_purchase_rate-treatment")).toHaveTextContent("32.0%");
    expect(screen.getByTestId("pos-row-co_purchase_rate-control")).toHaveTextContent("20.0%");
    expect(screen.getByTestId("pos-row-co_purchase_rate-diff")).toHaveTextContent("+12.0pt");
    expect(screen.getByTestId("pos-row-items_per_purchase-treatment")).toHaveTextContent("2.40点");
    expect(screen.getByTestId("pos-row-items_per_purchase-diff")).toHaveTextContent("+0.30点");
    expect(screen.getByTestId("pos-row-spend_per_customer-treatment")).toHaveTextContent("¥8,200");
    expect(screen.getByTestId("pos-row-spend_per_customer-diff")).toHaveTextContent("+¥600");
  });

  it("POSの一部指標のみ欠損している場合はその指標だけN/Aになる", async () => {
    installFetchMock([
      route("GET", "/api/admin/kpi", () => ({
        body: kpiResponse({
          pos_metrics: {
            groups: {
              treatment: { co_purchase_rate: 0.32, items_per_purchase: null, spend_per_customer: 8200 },
              control: { co_purchase_rate: 0.2, items_per_purchase: 2.1, spend_per_customer: 7600 },
            },
            diff: {
              co_purchase_rate: 0.12,
              items_per_purchase: null,
              spend_per_customer: 600,
            },
          },
        }),
      })),
    ]);

    renderAdminPage();
    enterTokenAndSubmit(VALID_TOKEN);

    expect(await screen.findByTestId("pos-metrics")).toBeInTheDocument();
    expect(screen.getByTestId("pos-row-items_per_purchase-treatment")).toHaveTextContent("N/A");
    expect(screen.getByTestId("pos-row-items_per_purchase-diff")).toHaveTextContent("N/A");
    expect(screen.getByTestId("pos-row-co_purchase_rate-treatment")).toHaveTextContent("32.0%");
  });

  it("誤ったトークン（401）では取得失敗UIを表示し、KPIは描画されない", async () => {
    const { fetchMock } = installFetchMock([
      route("GET", "/api/admin/kpi", () => ({
        status: 401,
        body: { code: "ADMIN_UNAUTHORIZED", message: "管理系APIの認証に失敗しました。" },
      })),
    ]);

    renderAdminPage();
    enterTokenAndSubmit("wrong-token");

    expect(await screen.findByTestId("admin-auth-error")).toBeInTheDocument();
    expect(screen.getByTestId("admin-auth-error")).toHaveTextContent("管理トークンを入力してください");
    expect(screen.queryByTestId("admin-kpi-content")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("両群とも0件（空データ）の場合は空状態を表示する", async () => {
    installFetchMock([
      route("GET", "/api/admin/kpi", () => ({
        body: kpiResponse({
          groups: {
            treatment: {
              session_count: 0,
              funnel: {
                scanned: 0,
                related_viewed: 0,
                related_tapped: 0,
                route_viewed: 0,
                coordinate_viewed: 0,
                chatbot_opened: 0,
              },
              rates: {
                related_tap_rate: 0,
                route_reach_rate: 0,
                coordinate_view_rate: 0,
                sub_passage_rate: 0,
              },
            },
            control: {
              session_count: 0,
              funnel: {
                scanned: 0,
                related_viewed: 0,
                related_tapped: 0,
                route_viewed: 0,
                coordinate_viewed: 0,
                chatbot_opened: 0,
              },
              rates: {
                related_tap_rate: 0,
                route_reach_rate: 0,
                coordinate_view_rate: 0,
                sub_passage_rate: 0,
              },
            },
          },
          diff: {
            related_tap_rate: 0,
            route_reach_rate: 0,
            coordinate_view_rate: 0,
            sub_passage_rate: 0,
          },
        }),
      })),
    ]);

    renderAdminPage();
    enterTokenAndSubmit(VALID_TOKEN);

    expect(await screen.findByTestId("admin-kpi-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("kpi-funnel-svg")).not.toBeInTheDocument();
  });
});
