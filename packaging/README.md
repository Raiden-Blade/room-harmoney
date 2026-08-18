# Room Harmony デスクトップ配布

## 配布方針

`start-demo.cmd` はソース開発用の補助起動器であり、Python/Node.js本体は含まない。非開発者向け成果物はPyInstallerのone-folder形式で、Python実行環境、FastAPI、構築済みReact、必要なサンプルJSONだけを同梱する。

one-fileにしない理由は、9,180商品とフロント資源を起動のたび一時展開する待ち時間、ウイルス対策ソフトによる誤検知、障害時の調査難度を避けるためである。利用者はZIPを一度解凍し、フォルダ内のアプリだけを起動する。

## ローカルビルド

ビルド機にはPython 3.11以上、Node.js 22以上が必要。生成したアプリの利用者には不要である。PyInstallerはクロスコンパイラではないため、Windows版はWindows、macOS版は各CPUアーキテクチャのmacOSで生成する。

```powershell
# Windows
backend\.venv\Scripts\python.exe -m pip install -r packaging\requirements-build.txt
backend\.venv\Scripts\python.exe packaging\build_release.py
```

```bash
# macOS
python3 -m pip install -r backend/requirements.txt -r packaging/requirements-build.txt
python3 packaging/build_release.py
```

処理は次の順で失敗時に停止する。

1. npm lockfileどおりに依存関係を取得し、本番Reactを構築
2. 同梱する8 JSONとデモ商品を検査
3. OSネイティブのone-folderアプリを生成
4. `.db`、`.env`、`.log`、秘密鍵等が成果物へ混入していないことを監査
5. パッケージ自身を起動し、QR Session → 商品 → 既存推薦 → Guided Chat → 店内ルートを実HTTPで通す
6. OS/CPU別ZIPとSHA-256ファイルを `release/` に生成

## 自動ビルド

`.github/workflows/desktop-release.yml` は次の独立runnerでテスト・構築する。

- `windows-latest`: Windows x64
- `macos-15`: macOS Apple Silicon arm64
- `macos-15-intel`: macOS Intel x64

手動実行ではActions artifactを作る。署名されていない成果物は `-unsigned` と明記される。`v*` タグでは全3ジョブが成功し、かつ全成果物が署名済みの場合だけGitHub Releaseを作成する。ソースZIPを初心者向け配布物として案内してはならない。

## 署名・公証ゲート

現在のリポジトリに証明書やApple資格情報は保存しない。正式な一般配布前には、次をGitHub Secretsまたは組織の安全な署名基盤へ登録し、署名後の成果物を再度スモークテストする。

- Windows: Authenticodeコード署名証明書とタイムスタンプ
- macOS: Developer ID Application証明書、hardened runtime、notarytoolによるnotarization、stapling

成果物名から `-unsigned` を外す判定は環境変数ではなく、Windowsでは実際のAuthenticode検証、macOSではDeveloper ID署名とstapled notarizationの検証結果を使う。署名されていないActions artifactは内部検証用である。自己完結して動くことは確認できても、SmartScreen/Gatekeeperの警告なしで一般利用者が起動できることまでは証明しない。

## 実行時の境界

- サーバーは `127.0.0.1` のみにbindし、LANへ公開しない。
- 8000番が使用中なら、所有者を終了せずOS割当の空きポートへ退避する。
- 多重起動は状態ファイルだけで信じず、`/health` のinstance ID一致まで確認する。
- 読み取り専用マスタはアプリ内、SQLite・ログ・診断はユーザーのApplication Dataへ分離する。
- 商品画像は現状ニトリネットのURL参照であり、画像まで完全オフラインにするには利用許諾済み画像の同梱またはキャッシュ設計が別途必要である。
