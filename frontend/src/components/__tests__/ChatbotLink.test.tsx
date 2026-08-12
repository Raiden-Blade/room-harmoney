import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installFetchMock, route } from "../../test/mockFetch";
import { saveSession } from "../../state/session";
import { ChatbotLink } from "../ChatbotLink";

/**
 * チャットボット導線（S5・4.4章／フェーズ2-C）: outboundリンクへのディープリンク付与と
 * `chatbot_open` イベントpayloadへの文脈付与（product_id/coordinate_id/to_product/screen）。
 */
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

beforeEach(() => {
  vi.stubEnv("VITE_CHATBOT_BASE_URL", "https://chatbot.example.com");
});

function withSession() {
  saveSession({
    sessionId: "sess-chatbot",
    experimentGroup: "A",
    qrId: "QR-ENTRANCE-001",
    start: { floor: 1, x: 3, y: 50 },
  });
}

describe("ChatbotLink", () => {
  it("接続先が未設定の場合は無効なリンクを出さず、接続準備中と表示する", () => {
    vi.stubEnv("VITE_CHATBOT_BASE_URL", "https://example.invalid/chatbot");
    render(<ChatbotLink productId="P001" screen="product_detail" />);

    expect(screen.getByTestId("chatbot-link-unavailable")).toHaveTextContent(
      "既存チャットボットは接続準備中です",
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("outboundリンクのhrefに product_id/screen のディープリンクパラメータが付与される", () => {
    render(<ChatbotLink productId="P001" screen="product_detail" />);
    const link = screen.getByTestId("chatbot-link") as HTMLAnchorElement;
    const url = new URL(link.href);
    expect(url.searchParams.get("product_id")).toBe("P001");
    expect(url.searchParams.get("screen")).toBe("product_detail");
  });

  it("outboundリンクのhrefに coordinate_id が付与される", () => {
    render(<ChatbotLink coordinateId="C001" screen="coordinate_detail" />);
    const link = screen.getByTestId("chatbot-link") as HTMLAnchorElement;
    const url = new URL(link.href);
    expect(url.searchParams.get("coordinate_id")).toBe("C001");
  });

  it("outboundリンクのhrefに to_product（複数）が付与される（往復導線: inboundと同じパラメータ名）", () => {
    render(<ChatbotLink toProducts={["P001", "P002"]} screen="route" />);
    const link = screen.getByTestId("chatbot-link") as HTMLAnchorElement;
    const url = new URL(link.href);
    expect(url.searchParams.get("to_product")).toBe("P001,P002");
  });

  it("文脈が無い場合はクエリなしのベースURLになる", () => {
    render(<ChatbotLink />);
    const link = screen.getByTestId("chatbot-link") as HTMLAnchorElement;
    expect(link.href).not.toContain("?");
  });

  it("クリック時に chatbot_open イベントのpayloadへ現在の文脈（product_id/coordinate_id/screen）を含める", async () => {
    withSession();
    const { calls } = installFetchMock([route("POST", "/api/events", () => ({ body: { ok: true } }))]);

    render(<ChatbotLink productId="P001" coordinateId={undefined} screen="product_detail" />);
    fireEvent.click(screen.getByTestId("chatbot-link"));

    await vi.waitFor(() => {
      expect(calls.some((c) => c.method === "POST" && c.url.includes("/api/events"))).toBe(true);
    });

    const eventCall = calls.find((c) => c.method === "POST" && c.url.includes("/api/events"));
    const body = eventCall!.body as {
      event_type?: string;
      payload?: Record<string, unknown>;
    };
    expect(body.event_type).toBe("chatbot_open");
    expect(body.payload).toEqual({
      product_id: "P001",
      coordinate_id: null,
      to_product: null,
      screen: "product_detail",
    });
  });

  it("to_product文脈でのクリックはpayloadのto_productに配列が入る", async () => {
    withSession();
    const { calls } = installFetchMock([route("POST", "/api/events", () => ({ body: { ok: true } }))]);

    render(<ChatbotLink toProducts={["P001", "P002"]} screen="route" />);
    fireEvent.click(screen.getByTestId("chatbot-link"));

    await vi.waitFor(() => {
      expect(calls.some((c) => c.method === "POST" && c.url.includes("/api/events"))).toBe(true);
    });

    const eventCall = calls.find((c) => c.method === "POST" && c.url.includes("/api/events"));
    const body = eventCall!.body as { payload?: Record<string, unknown> };
    expect(body.payload?.to_product).toEqual(["P001", "P002"]);
    expect(body.payload?.screen).toBe("route");
  });
});
