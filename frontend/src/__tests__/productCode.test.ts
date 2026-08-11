import { describe, expect, it } from "vitest";

import { formatProductCodeInput, normalizeDigits } from "../productCode";

describe("formatProductCodeInput", () => {
  it("桁入力ごとに 2-2-2-4 の位置でハイフンを自動挿入する", () => {
    expect(formatProductCodeInput("")).toBe("");
    expect(formatProductCodeInput("0")).toBe("0");
    expect(formatProductCodeInput("03")).toBe("03");
    // 3桁目を入力した瞬間に区切りが現れる
    expect(formatProductCodeInput("030")).toBe("03-0");
    expect(formatProductCodeInput("0302")).toBe("03-02");
    expect(formatProductCodeInput("03020")).toBe("03-02-0");
    expect(formatProductCodeInput("030201")).toBe("03-02-01");
    expect(formatProductCodeInput("0302010")).toBe("03-02-01-0");
    expect(formatProductCodeInput("0302010001")).toBe("03-02-01-0001");
  });

  it("数字以外（ハイフン等）は除去して整形する（冪等）", () => {
    expect(formatProductCodeInput("03-02-01-0001")).toBe("03-02-01-0001");
    expect(formatProductCodeInput("03-02")).toBe("03-02");
    expect(formatProductCodeInput("abc03x02")).toBe("03-02");
  });

  it("10桁を超える入力は10桁に丸める（末尾ハイフンは付けない）", () => {
    expect(formatProductCodeInput("03020100019999")).toBe("03-02-01-0001");
    expect(normalizeDigits("03020100019999")).toBe("0302010001");
  });
});
