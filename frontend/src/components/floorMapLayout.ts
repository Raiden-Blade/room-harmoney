const MAP_MARGIN = 4;
const DESTINATION_LABEL_FONT_SIZE = 5;
const DESTINATION_LABEL_GAP = 9;
const MAX_DESTINATION_LABEL_CHARS = 7;

interface DestinationLabelSource {
  name: string;
  x: number;
  y: number;
}

interface LabelBounds {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DestinationLabelLayout {
  text: string;
  x: number;
  y: number;
  textAnchor: "start" | "middle" | "end";
}

/**
 * 商品名をピンの空いている側へ置き、長い名称はマップ内に収まる長さへ省略する。
 * 完全な商品名はSVGの<title>に残すため、一覧とアクセシビリティ情報からは失われない。
 */
export function getDestinationLabelLayout(
  destination: DestinationLabelSource,
  width: number,
  height: number,
  containingZone?: LabelBounds,
): DestinationLabelLayout {
  const left = containingZone ? containingZone.x + 2 : MAP_MARGIN;
  const right = containingZone ? containingZone.x + containingZone.w - 2 : width - MAP_MARGIN;
  const bottom = containingZone
    ? containingZone.y + containingZone.h - 2
    : height - MAP_MARGIN;
  const availableWidth = Math.max(DESTINATION_LABEL_FONT_SIZE * 3, right - left);
  const maxChars = Math.max(
    3,
    Math.min(MAX_DESTINATION_LABEL_CHARS, Math.floor(availableWidth / DESTINATION_LABEL_FONT_SIZE)),
  );
  const text =
    destination.name.length > maxChars
      ? `${destination.name.slice(0, Math.max(1, maxChars - 1))}…`
      : destination.name;
  const estimatedWidth = text.length * DESTINATION_LABEL_FONT_SIZE;
  const halfWidth = estimatedWidth / 2;
  const x = Math.min(right - halfWidth, Math.max(left + halfWidth, destination.x));

  return {
    text,
    x,
    y: Math.min(bottom, Math.max(MAP_MARGIN + DESTINATION_LABEL_FONT_SIZE, destination.y + DESTINATION_LABEL_GAP)),
    textAnchor: "middle",
  };
}
