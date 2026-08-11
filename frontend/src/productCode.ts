/**
 * 商品番号（`LL-MM-SS-NNNN`）の入力整形ユーティリティ。
 *
 * 体系は固定桁: 大分類2桁・中分類2桁・小分類2桁・個別番号4桁（計10桁）。
 * 段階B2（実商品データ9,180件への差し替え）: 中分類（＝小分類。実データでは
 * `cat_small = cat_mid`）ごとの商品数が1,000件を超えうる（例: カーテン約2,600件）ため、
 * 個別番号を3桁（001〜999）から4桁（0001〜9999）へ拡張した
 * （`backend/batch/product_codes.py` SEQ_DIGITS と整合）。
 * 桁が固定なので、入力中の数字列に対して 2-2-2-4 の区切りでハイフンを
 * 自動挿入するだけでよい（バックエンドはハイフン有無を正規化して解決する）。
 */

/** 数字のみ・最大10桁に丸める。 */
export function normalizeDigits(raw: string): string {
  return raw.replace(/\D/g, "").slice(0, 10);
}

/**
 * 入力文字列を `LL-MM-SS-NNNN` 形式へ整形する。
 * 数字以外は除去し、2桁・2桁・2桁・4桁の区切りでハイフンを自動挿入する。
 * 次のグループの最初の数字が入力された時点でハイフンが現れる（末尾ハイフンは付けない）。
 *
 * 例: "0103020001" → "01-03-02-0001" / "0103" → "01-03" / "010" → "01-0"
 */
export function formatProductCodeInput(raw: string): string {
  const digits = normalizeDigits(raw);
  const groups: string[] = [];
  if (digits.length > 0) groups.push(digits.slice(0, 2));
  if (digits.length > 2) groups.push(digits.slice(2, 4));
  if (digits.length > 4) groups.push(digits.slice(4, 6));
  if (digits.length > 6) groups.push(digits.slice(6, 10));
  return groups.join("-");
}

/** 整形後文字列の最大長（10桁 + ハイフン3つ）。input の maxLength 用。 */
export const PRODUCT_CODE_MAX_LENGTH = 13;
