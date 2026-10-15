"""問題データを表すデータクラスと、アプリ全体で使う定数を定義するモジュール。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------
# 定数
# ---------------------------------------------------------------

#: 出題カテゴリ（この3つ以外は不正値としてスキーマ検証でエラーにする）
#: 並び順は画面表示や層化抽出の順番にも使う。
CATEGORIES: tuple[str, ...] = (
    "内部管理・内部統制",
    "保険募集規制",
    "生命保険協会ガイドライン",
)

#: 問題の確認状態。
#:   draft    = 根拠を一次情報で確認できていない（画面に「要確認」バッジを出す）
#:   reviewed = 根拠を一次情報で確認済み
STATUS_DRAFT = "draft"
STATUS_REVIEWED = "reviewed"
STATUSES: tuple[str, ...] = (STATUS_DRAFT, STATUS_REVIEWED)

#: 難易度（任意項目）。基本:標準:難 = 7:2:1 を目安に作成する。
DIFFICULTY_LABELS: dict[str, str] = {
    "basic": "基本",
    "standard": "標準",
    "hard": "難",
}

#: ○×の表示記号
MARU = "○"
BATSU = "✕"


def answer_symbol(answer: bool | None) -> str:
    """真偽値の解答を画面表示用の記号（○ / ✕）に変換する。

    Args:
        answer: True なら○、False なら✕。None（未回答）なら「未回答」。

    Returns:
        表示用の文字列。
    """
    if answer is None:
        return "未回答"
    return MARU if answer else BATSU


# ---------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------


@dataclass(frozen=True)
class Question:
    """1問分の問題データ。

    JSON の1要素をそのまま表したもの。frozen=True にしているので、
    読み込んだ後に誤って書き換えてしまうことを防げる。
    """

    id: str
    category: str
    subcategory: str
    statement: str  # 問題文
    answer: bool  # 正解（True = ○ / False = ✕）
    explanation: str  # 解説
    reference: str  # 根拠（法令・条番号など）
    tip: str  # 一言で覚えるtips
    status: str  # draft / reviewed
    difficulty: str | None = None  # basic / standard / hard（任意）

    @property
    def is_draft(self) -> bool:
        """根拠が未確認（draft）の問題なら True を返す。"""
        return self.status == STATUS_DRAFT

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Question":
        """スキーマ検証済みの辞書から Question を作る。

        Args:
            data: JSON から読み込んだ1問分の辞書（validator で検証済みであること）。

        Returns:
            Question オブジェクト。
        """
        return cls(
            id=data["id"],
            category=data["category"],
            subcategory=data["subcategory"],
            statement=data["statement"],
            answer=data["answer"],
            explanation=data["explanation"],
            reference=data["reference"],
            tip=data["tip"],
            status=data["status"],
            difficulty=data.get("difficulty"),
        )
