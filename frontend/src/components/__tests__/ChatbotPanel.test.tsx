import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock, route } from "../../test/mockFetch";
import { ChatbotPanel } from "../ChatbotPanel";

const PRODUCT = {
  product_id: "P033",
  name: "収納ボックス",
  cat_large: "収納",
  cat_mid: "収納ボックス",
  cat_small: "衣装収納",
  color: "グレー",
  price: 2980,
  image_url: "https://dummyimage.com/80x80",
  floor: 4,
  zone: "C",
  x: 77,
  y: 18,
  sub_passage_flag: false,
};

function chatResponse(overrides: Record<string, unknown> = {}) {
  return {
    message: "条件を教えてください。",
    recognized: true,
    completed: false,
    question: {
      question_id: "focus",
      text: "何を優先しますか？",
      reason: "方向を決めます。",
      options: [
        { option_id: "budget", label: "価格", description: "価格を重視します。" },
        { option_id: "discovery", label: "発見", description: "新しい候補を探します。" },
      ],
    },
    state: { answered_question_ids: [], preferences: {} },
    recommendations: [
      {
        product: PRODUCT,
        cat_mid: "収納ボックス",
        lift: 1.4,
        high_lift_low_corate: false,
        base_score: 1.4,
        guided_score: 0.7,
        reasons: ["カテゴリ間の関連性を基に選定"],
      },
    ],
    route_product_ids: ["P033"],
    coordinates: [],
    data_notice: "実習用の仮想値を含みます。",
    ...overrides,
  };
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<ChatbotPanel productId="P001" sessionId="sess-1" />} />
        <Route path="/route" element={<div data-testid="route-page">route</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ChatbotPanel", () => {
  it("自由入力を要求する前に開始ボタンと利用モードを表示する", () => {
    renderPanel();

    expect(screen.getByTestId("chatbot-start")).toBeInTheDocument();
    expect(screen.getByText("お客様向け")).toBeInTheDocument();
    expect(screen.queryByLabelText("短い言葉で入力する")).not.toBeInTheDocument();
  });

  it("開始後は一問と上位候補を表示し、選択回答を構造化APIへ送る", async () => {
    const second = chatResponse({
      message: "回答を反映しました。",
      question: null,
      completed: true,
      state: { answered_question_ids: ["focus"], preferences: { focus: "budget" } },
    });
    const { calls } = installFetchMock([
      route("POST", "/api/chat/turn", () => ({
        body: calls.filter((call) => call.url.includes("/api/chat/turn")).length === 1
          ? chatResponse()
          : second,
      })),
    ]);
    renderPanel();

    fireEvent.click(screen.getByTestId("chatbot-start"));
    const question = await screen.findByTestId("chatbot-question");
    expect(within(question).getByText("何を優先しますか？")).toBeInTheDocument();
    expect(screen.getByText("収納ボックス")).toBeInTheDocument();

    fireEvent.click(within(question).getByText("価格"));
    await screen.findByText("回答を反映しました。");
    const answerCall = calls.filter((call) => call.url.includes("/api/chat/turn"))[1];
    expect((answerCall.body as { answer_id?: string }).answer_id).toBe("budget");
    expect((answerCall.body as { question_id?: string }).question_id).toBe("focus");
  });

  it("まとめて売場を見ると起点商品と候補を複数目的地としてルートへ渡す", async () => {
    installFetchMock([
      route("POST", "/api/chat/turn", () => ({ body: chatResponse({ route_product_ids: ["P033", "P034"] }) })),
      route("POST", "/api/events", () => ({ body: { ok: true } })),
    ]);
    renderPanel();
    fireEvent.click(screen.getByTestId("chatbot-start"));

    fireEvent.click(await screen.findByTestId("chatbot-bundle-route"));

    expect(await screen.findByTestId("route-page")).toBeInTheDocument();
  });
});
