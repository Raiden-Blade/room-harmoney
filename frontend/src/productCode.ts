/**
 * 商品番号（`LL-MM-SS-NNN`）の入力整形ユーティリティ。
 *
 * 体系は固定桁: 大分類2桁・中分類2桁・小分類2桁・個別番号3桁（計9桁）。
 * 桁が固定なので、入力中の数字列に対して 2-2-2-3 の区切りでハイフンを
 * 自動挿入するだけでよい（バックエンドはハイフン有無を正規化して解決する）。
 */

/** 数字のみ・最大9桁に丸める。 */
export function normalizeDigits(raw: string): string {
  return raw.replace(/\D/g, "").slice(0, 9);
}

/**
 * 入力文字列を `LL-MM-SS-NNN` 形式へ整形する。
 * 数字以外は除去し、2桁・2桁・2桁・3桁の区切りでハイフンを自動挿入する。
 * 次のグループの最初の数字が入力された時点でハイフンが現れる（末尾ハイフンは付けない）。
 *
 * 例: "030201001" → "03-02-01-001" / "0302" → "03-02" / "030" → "03-0"
 */
export function formatProductCodeInput(raw: string): string {
  const digits = normalizeDigits(raw);
  const groups: string[] = [];
  if (digits.length > 0) groups.push(digits.slice(0, 2));
  if (digits.length > 2) groups.push(digits.slice(2, 4));
  if (digits.length > 4) groups.push(digits.slice(4, 6));
  if (digits.length > 6) groups.push(digits.slice(6, 9));
  return groups.join("-");
}

/** 整形後文字列の最大長（9桁 + ハイフン3つ）。input の maxLength 用。 */
export const PRODUCT_CODE_MAX_LENGTH = 12;
