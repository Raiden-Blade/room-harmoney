/**
 * カメラでのQR読取（4.1章）。`html5-qrcode` を使う。
 *
 * 自動テスト（Vitest/jsdom）にはカメラが無いため、このコンポーネントは
 * ユーザーが明示的に「カメラで読み取る」を選んだ場合にのみマウントされる設計にし
 * （`ScanPage` 側で条件付きレンダリング）、単体テストの対象外とする。
 * E2E（G4）ではカメラの代わりに URL直リンク・フォールバック（`/s/:qr_id`）を使う
 * （HARNESS.md 「カメラQR読取のE2E」の既定方式）。
 * カメラ初期化に失敗しても（非対応端末・権限拒否）例外でアプリを壊さず、
 * `onError` でユーザーに案内できるようにする。
 */
import { useEffect, useRef } from "react";

export interface QrCameraScannerProps {
  onDecoded: (text: string) => void;
  onError: (message: string) => void;
}

export function QrCameraScanner({ onDecoded, onError }: QrCameraScannerProps) {
  const containerId = "rh-qr-camera-region";
  const scannerRef = useRef<import("html5-qrcode").Html5Qrcode | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    stoppedRef.current = false;
    let cancelled = false;

    async function start() {
      try {
        const { Html5Qrcode } = await import("html5-qrcode");
        if (cancelled) return;
        const scanner = new Html5Qrcode(containerId);
        scannerRef.current = scanner;
        await scanner.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 220, height: 220 } },
          (decodedText) => {
            onDecoded(decodedText);
          },
          () => {
            // フレームごとの読み取り失敗はエラー扱いにしない（QRが視野に無いだけのため）。
          },
        );
      } catch {
        // 19章 エッジケース: カメラ非対応・権限拒否。URL直リンクへの案内はScanPage側で行う。
        onError("カメラを起動できませんでした。URLから直接お進みください。");
      }
    }

    void start();

    return () => {
      cancelled = true;
      const scanner = scannerRef.current;
      if (scanner && !stoppedRef.current) {
        stoppedRef.current = true;
        scanner.stop().catch(() => undefined);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div id={containerId} data-testid="qr-camera-region" />;
}
