/**
 * A/B×KPIダッシュボード用の横棒グラフ（フェーズ2-B2）。
 *
 * 外部チャートライブラリは追加せず、既存の `FloorMap`（SVGマップ）と同じ方針で
 * インラインSVGで描画する。treatment（利用群）/ control（非利用群）を1指標につき
 * 2本のバーで比較する。色だけに依存しないよう、
 * - 各バーに数値ラベルと `aria-label`（群名＋指標名＋値）を付ける
 * - control群のバーは塗りつぶし（treatment）ではなく斜線パターンにする
 * - 凡例にも記号（■/▨）を添える
 * ことでアクセシビリティに配慮する。
 */
export interface KpiBarChartItem {
  key: string;
  label: string;
  treatment: number;
  control: number;
}

export interface KpiBarChartProps {
  title: string;
  items: KpiBarChartItem[];
  /** バー横の数値ラベル・aria-label用の値フォーマッタ（例: 件数 or %表示）。 */
  formatValue: (value: number) => string;
  /** バーの長さのスケール上限。省略時は表示データの最大値を使う。 */
  maxValue?: number;
  /** data-testid の接頭辞（テストから群・指標を特定できるようにする）。 */
  testIdPrefix: string;
}

const LABEL_WIDTH = 46;
const CHART_WIDTH = 100;
const PLOT_WIDTH = CHART_WIDTH - LABEL_WIDTH - 4;
const BAR_HEIGHT = 6;
const BAR_GAP = 2;
const ROW_HEIGHT = BAR_HEIGHT * 2 + BAR_GAP + 6;

export function KpiBarChart({ title, items, formatValue, maxValue, testIdPrefix }: KpiBarChartProps) {
  const patternId = `${testIdPrefix}-control-pattern`;
  const dataMax = Math.max(0, ...items.flatMap((item) => [item.treatment, item.control]));
  const scaleMax = maxValue ?? (dataMax > 0 ? dataMax : 1);
  const scale = (value: number) => (Math.max(value, 0) / scaleMax) * PLOT_WIDTH;
  const height = items.length * ROW_HEIGHT + 4;

  return (
    <figure className="kpi-bar-chart" data-testid={`${testIdPrefix}-chart`}>
      <figcaption>{title}</figcaption>
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${height}`}
        width="100%"
        role="img"
        aria-label={`${title}（利用群と非利用群の比較棒グラフ）`}
        data-testid={`${testIdPrefix}-svg`}
      >
        <defs>
          <pattern
            id={patternId}
            width={2}
            height={2}
            patternTransform="rotate(45)"
            patternUnits="userSpaceOnUse"
          >
            <line x1={0} y1={0} x2={0} y2={2} stroke="#b6b6b6" strokeWidth={1} />
          </pattern>
        </defs>
        {items.map((item, index) => {
          const rowY = index * ROW_HEIGHT;
          const treatmentWidth = Math.max(scale(item.treatment), 0.5);
          const controlWidth = Math.max(scale(item.control), 0.5);
          return (
            <g key={item.key} data-testid={`${testIdPrefix}-row-${item.key}`}>
              <text x={0} y={rowY + 4} fontSize={4} fill="#14293a">
                {item.label}
              </text>
              {/* treatment（利用群）= --rh-brand（docs/DESIGN_SYSTEM.md §4） */}
              <rect
                x={LABEL_WIDTH}
                y={rowY + 6}
                width={treatmentWidth}
                height={BAR_HEIGHT}
                fill="#009e96"
                role="img"
                aria-label={`利用群（treatment） ${item.label}: ${formatValue(item.treatment)}`}
                data-testid={`${testIdPrefix}-bar-treatment-${item.key}`}
              />
              <text x={LABEL_WIDTH + treatmentWidth + 1} y={rowY + 6 + BAR_HEIGHT - 1.2} fontSize={3.6} fill="#009e96">
                {formatValue(item.treatment)}
              </text>
              {/* control（非利用群）= 灰(--rh-control-gray)。斜線パターンは色覚配慮のため維持。 */}
              <rect
                x={LABEL_WIDTH}
                y={rowY + 6 + BAR_HEIGHT + BAR_GAP}
                width={controlWidth}
                height={BAR_HEIGHT}
                fill={`url(#${patternId})`}
                stroke="#b6b6b6"
                strokeWidth={0.3}
                role="img"
                aria-label={`非利用群（control） ${item.label}: ${formatValue(item.control)}`}
                data-testid={`${testIdPrefix}-bar-control-${item.key}`}
              />
              <text
                x={LABEL_WIDTH + controlWidth + 1}
                y={rowY + 6 + BAR_HEIGHT + BAR_GAP + BAR_HEIGHT - 1.2}
                fontSize={3.6}
                fill="#6d6d6d"
              >
                {formatValue(item.control)}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="kpi-bar-chart-legend" data-testid={`${testIdPrefix}-legend`}>
        <span className="legend-item legend-treatment">■ 利用群（treatment）</span>
        <span className="legend-item legend-control">▨ 非利用群（control）</span>
      </div>
    </figure>
  );
}
