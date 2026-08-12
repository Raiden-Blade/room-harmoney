# Windows ワンクリックデモ起動

このディレクトリは、リポジトリルートの `start-demo.cmd` / `stop-demo.cmd` から呼ばれる内部スクリプトを格納する。通常はこの中のPowerShellファイルを直接操作する必要はない。

## 利用方法

1. GitHubからリポジトリをダウンロードまたはcloneする。
2. リポジトリルートの `start-demo.cmd` をダブルクリックする。
3. 初回だけPython・Node.js依存関係のインストール完了を待つ。
4. Chromeまたは既定ブラウザでRoom Harmonyの商品QRデモが自動的に開く。
5. 終了時は `stop-demo.cmd` をダブルクリックする。

デモ起動では `EXPERIMENT_GROUP_RATIO=1.0` をバックエンド子プロセスにだけ設定し、ガイド型チャットを必ず表示する。PC全体の永続的な環境変数は変更しない。

初回セットアップではPython 3.11以上を使用する。`py.exe` がない環境でも、利用可能な `python.exe` があれば自動的に選択する。

フロントエンドは `package-lock.json` の固定バージョンを `npm ci --legacy-peer-deps` で導入する。これにより、Node.js 24 / npm 11で厳格化された既知のpeer依存判定でも同じ構成を再現できる。

実行中のPIDとログは、Git管理対象外の `.room-harmony-demo/` に保存する。停止スクリプトはPID・起動時刻・コマンド内容を照合し、この起動器が開始したプロセスだけを停止する。

自動検証等でブラウザを開きたくない場合は、次のように内部スクリプトへ `-NoBrowser` を渡せる。

```powershell
start-demo.cmd -NoBrowser
```
