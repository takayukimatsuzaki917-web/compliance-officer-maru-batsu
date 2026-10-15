"""模試の採点・合否判定・カテゴリ別正答率の集計を行うモジュール。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from quiz.models import CATEGORIES, Question

#: 浮動小数点の誤差対策（例: 25 × 0.7 が 17.499999... になっても 18 と判定するため）
FLOAT_TOLERANCE = 1e-9


def required_score(total: int, pass_ratio: float) -> int:
    """合格に必要な正答数を返す。

    例: 25問・合格ライン70% → 25 × 0.7 = 17.5 → 切り上げて18問。

    Args:
        total: 出題数。
        pass_ratio: 合格ライン（0〜1）。

    Returns:
        合格に必要な最低正答数。
    """
    return math.ceil(total * pass_ratio - FLOAT_TOLERANCE)


@dataclass(frozen=True)
class QuestionResult:
    """1問分の採点結果。"""

    question_id: str
    category: str
    user_answer: bool | None  # 受験者の回答（None = 未回答）
    correct_answer: bool  # 正解

    @property
    def is_correct(self) -> bool:
        """正解なら True。未回答は不正解として扱う。"""
        return self.user_answer is not None and self.user_answer == self.correct_answer

    def to_dict(self) -> dict[str, Any]:
        """履歴保存用の辞書に変換する。"""
        return {
            "id": self.question_id,
            "category": self.category,
            "user_answer": self.user_answer,
            "correct_answer": self.correct_answer,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "QuestionResult":
        """履歴の辞書から復元する。"""
        return cls(
            question_id=data["id"],
            category=data["category"],
            user_answer=data["user_answer"],
            correct_answer=data["correct_answer"],
        )


@dataclass(frozen=True)
class CategoryScore:
    """カテゴリ1つ分の正答数。"""

    category: str
    correct: int
    total: int

    @property
    def ratio(self) -> float:
        """正答率（0〜1）。出題0問のときは0。"""
        return self.correct / self.total if self.total else 0.0


@dataclass(frozen=True)
class ExamResult:
    """模試1回分の採点結果。"""

    items: tuple[QuestionResult, ...]  # 出題順の採点結果
    pass_ratio: float  # 採点時の合格ライン

    @property
    def total(self) -> int:
        """出題数。"""
        return len(self.items)

    @property
    def score(self) -> int:
        """正答数。"""
        return sum(1 for item in self.items if item.is_correct)

    @property
    def ratio(self) -> float:
        """正答率（0〜1）。"""
        return self.score / self.total if self.total else 0.0

    @property
    def required_score(self) -> int:
        """合格に必要な正答数。"""
        return required_score(self.total, self.pass_ratio)

    @property
    def passed(self) -> bool:
        """合格ラインに達していれば True。"""
        return self.total > 0 and self.score >= self.required_score

    @property
    def unanswered_count(self) -> int:
        """未回答の問題数。"""
        return sum(1 for item in self.items if item.user_answer is None)

    def category_scores(self) -> list[CategoryScore]:
        """カテゴリ別の正答数を、定義済みカテゴリの順に返す（出題0問のカテゴリは除く）。"""
        tally: dict[str, list[int]] = {}  # カテゴリ → [正答数, 出題数]
        for item in self.items:
            counts = tally.setdefault(item.category, [0, 0])
            counts[0] += int(item.is_correct)
            counts[1] += 1

        # 既知のカテゴリを先に、それ以外（通常は無い）を後ろに並べる
        ordered = [c for c in CATEGORIES if c in tally] + [c for c in tally if c not in CATEGORIES]
        return [CategoryScore(c, tally[c][0], tally[c][1]) for c in ordered]

    def to_dict(self) -> dict[str, Any]:
        """履歴保存用の辞書に変換する。"""
        return {
            "pass_ratio": self.pass_ratio,
            "score": self.score,
            "total": self.total,
            "passed": self.passed,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExamResult":
        """履歴の辞書から復元する（score などは items から再計算する）。"""
        return cls(
            items=tuple(QuestionResult.from_dict(item) for item in data["items"]),
            pass_ratio=data["pass_ratio"],
        )


def grade(questions: Sequence[Question], answers: Mapping[str, bool | None], pass_ratio: float) -> ExamResult:
    """模試を採点する。

    Args:
        questions: 出題した問題（出題順）。
        answers: 問題id → 受験者の回答（True=○ / False=✕ / None・キー無し=未回答）。
        pass_ratio: 合格ライン（0〜1）。

    Returns:
        ExamResult。
    """
    items = tuple(
        QuestionResult(
            question_id=q.id,
            category=q.category,
            user_answer=answers.get(q.id),
            correct_answer=q.answer,
        )
        for q in questions
    )
    return ExamResult(items=items, pass_ratio=pass_ratio)
