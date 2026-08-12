"""応答文生成の差し替え境界。

初版は外部APIを呼ばないテンプレート実装を使う。将来、ニトリの既存Bot等へ接続する
場合はこのProtocolを実装し、API契約・質問ポリシー・推薦器を変更せずに差し替える。
"""
from __future__ import annotations

from typing import Protocol


class ResponseComposer(Protocol):
    def opening(self, product_name: str, *, staff_mode: bool) -> str: ...

    def accepted(self, *, staff_mode: bool) -> str: ...

    def completed(self, *, staff_mode: bool) -> str: ...

    def unrecognized(self) -> str: ...


class TemplateResponseComposer:
    """外部通信なしで一定時間・一定品質の日本語を返す。"""

    def opening(self, product_name: str, *, staff_mode: bool) -> str:
        if staff_mode:
            return f"「{product_name}」を起点に、提案根拠を確認しながら候補を絞ります。"
        return f"「{product_name}」に合わせる商品を、3問以内で一緒に探します。"

    def accepted(self, *, staff_mode: bool) -> str:
        return "回答を反映して候補を並べ替えました。" if not staff_mode else "回答信号を後段スコアへ反映しました。"

    def completed(self, *, staff_mode: bool) -> str:
        if staff_mode:
            return "絞り込みは完了です。根拠を確認し、必要に応じて複数商品の売場ルートをご案内ください。"
        return "候補をまとめました。気になる商品を選ぶか、まとめて売場ルートを確認できます。"

    def unrecognized(self) -> str:
        return "入力から条件を特定できませんでした。近い選択肢を選ぶか、短い言葉で入力してください。"
