/**
 * 壊れた画像URL（19章 エッジケース想定）時の代替表示。
 * サンプルデータの `image_url` はダミーURL（dummyimage.com 等）だが、通信不可・URL失効時にも
 * レイアウトが崩れないようにする。
 */
import { useState } from "react";

const PLACEHOLDER_SVG =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300">' +
      '<rect width="100%" height="100%" fill="#eeeeee"/>' +
      '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#999999" font-size="16">画像を表示できません</text>' +
      "</svg>",
  );

type Props = Omit<React.ImgHTMLAttributes<HTMLImageElement>, "onError"> & {
  src?: string | null;
};

export function ImageWithFallback({ src, alt, ...rest }: Props) {
  const [errored, setErrored] = useState(false);
  const resolvedSrc = !src || errored ? PLACEHOLDER_SVG : src;
  return (
    <img
      src={resolvedSrc}
      alt={alt}
      onError={() => setErrored(true)}
      loading="lazy"
      {...rest}
    />
  );
}
