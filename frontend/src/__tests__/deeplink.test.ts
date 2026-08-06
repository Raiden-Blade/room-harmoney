import { describe, expect, it } from "vitest";

import {
  buildChatbotDeepLinkParams,
  buildChatbotOpenPayload,
  buildChatbotUrl,
  buildRoutePath,
  parseInboundDeepLink,
  parseToProducts,
} from "../deeplink";

/**
 * チャットボット双方向ディープリンク（4.4章・フェーズ2-C）のURLスキームを担う
 * 純粋関数の単体テスト。inbound（パース）/outbound（生成）双方、複数値・欠損を検証する。
 */
describe("parseToProducts", () => {
  it("同名パラメータの繰り返しから複数値を読み取る", () => {
    const params = new URLSearchParams("to_product=P001&to_product=P002");
    expect(parseToProducts(params)).toEqual(["P001", "P002"]);
  });

  it("カンマ区切り単一パラメータからも複数値を読み取る", () => {
    const params = new URLSearchParams("to_product=P001,P002,P003");
    expect(parseToProducts(params)).toEqual(["P001", "P002", "P003"]);
  });

  it("両形式が混在していても正しく読み取り、重複は除去する", () => {
    const params = new URLSearchParams("to_product=P001,P002&to_product=P002&to_product=P003");
    expect(parseToProducts(params)).toEqual(["P001", "P002", "P003"]);
  });

  it("欠損時は空配列", () => {
    const params = new URLSearchParams("");
    expect(parseToProducts(params)).toEqual([]);
  });

  it("空白・空文字の要素は除去する", () => {
    const params = new URLSearchParams("to_product=P001,%20,P002,");
    expect(parseToProducts(params)).toEqual(["P001", "P002"]);
  });
});

describe("parseInboundDeepLink", () => {
  it("product_id / coordinate_id / to_product をまとめて解析する", () => {
    const params = new URLSearchParams("product_id=P001&coordinate_id=C001&to_product=P002,P003");
    expect(parseInboundDeepLink(params)).toEqual({
      productId: "P001",
      coordinateId: "C001",
      toProducts: ["P002", "P003"],
    });
  });

  it("すべて欠損時はnull/空配列", () => {
    const params = new URLSearchParams("");
    expect(parseInboundDeepLink(params)).toEqual({
      productId: null,
      coordinateId: null,
      toProducts: [],
    });
  });
});

describe("buildRoutePath", () => {
  it("複数のto_productを同名パラメータの繰り返しとして組み立てる（RoutePageの読み取り形式に合わせる）", () => {
    expect(buildRoutePath(["P001", "P002"])).toBe("/route?to_product=P001&to_product=P002");
  });

  it("単一のto_productでも同じ形式で組み立てる", () => {
    expect(buildRoutePath(["P001"])).toBe("/route?to_product=P001");
  });

  it("空配列の場合はクエリなしのパス", () => {
    expect(buildRoutePath([])).toBe("/route?");
  });
});

describe("buildChatbotDeepLinkParams / buildChatbotUrl", () => {
  it("product_id/coordinate_id/to_product/screenをすべて含める", () => {
    const params = buildChatbotDeepLinkParams({
      productId: "P001",
      coordinateId: "C001",
      toProducts: ["P002", "P003"],
      screen: "product_detail",
    });
    expect(params.get("product_id")).toBe("P001");
    expect(params.get("coordinate_id")).toBe("C001");
    expect(params.get("to_product")).toBe("P002,P003");
    expect(params.get("screen")).toBe("product_detail");
  });

  it("未指定の項目はパラメータに含めない", () => {
    const params = buildChatbotDeepLinkParams({ productId: "P001" });
    expect(params.has("coordinate_id")).toBe(false);
    expect(params.has("to_product")).toBe(false);
    expect(params.has("screen")).toBe(false);
  });

  it("buildChatbotUrlはベースURLにクエリを付与する（往復導線: inboundと同じパラメータ名）", () => {
    const url = buildChatbotUrl("https://example.invalid/chatbot", {
      productId: "P001",
      screen: "product_detail",
    });
    expect(url).toBe("https://example.invalid/chatbot?product_id=P001&screen=product_detail");
  });

  it("コンテキストが空の場合はクエリを付与しない", () => {
    const url = buildChatbotUrl("https://example.invalid/chatbot", {});
    expect(url).toBe("https://example.invalid/chatbot");
  });
});

describe("buildChatbotOpenPayload", () => {
  it("文脈（product_id/coordinate_id/to_product/screen）を含み、個人情報は含まない", () => {
    const payload = buildChatbotOpenPayload({
      productId: "P001",
      coordinateId: null,
      toProducts: ["P002", "P003"],
      screen: "route",
    });
    expect(payload).toEqual({
      product_id: "P001",
      coordinate_id: null,
      to_product: ["P002", "P003"],
      screen: "route",
    });
  });

  it("未指定の項目はnullで埋める", () => {
    const payload = buildChatbotOpenPayload({});
    expect(payload).toEqual({
      product_id: null,
      coordinate_id: null,
      to_product: null,
      screen: null,
    });
  });
});
