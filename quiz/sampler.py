"""出題する問題を選ぶモジュール。

- 模試: 問題プール全体のカテゴリ比率に合わせた「層化抽出」
- 1問1答: 出題範囲（全問・カテゴリ・未回答・誤答・要復習）と出題順の指定
"""

from __future__ import annotations

import random
from enum import Enum
from typing import Iterable, Sequence

from quiz.models import CATEGORIES, Question

# ---------------------------------------------------------------
# 模試用: 層化抽出
# ---------------------------------------------------------------


def allocate_by_ratio(pool_counts: dict[str, int], n: int) -> dict[str, int]:
    """問題数 n を、カテゴリごとの問題数の比率に合わせて割り振る（最大剰余法）。

    手順:
      1. 各カテゴリの理想値 = n × (カテゴリの問題数 / 全問題数) を計算する
      2. 理想値の整数部分をまず割り当てる
      3. 足りない分を、小数部分（余り）が大きいカテゴリから1問ずつ追加する
         （余りが同じなら、問題数が多いカテゴリ → カテゴリの定義順を優先）

    例: 60:90:50 の問題プールから25問 → 理想値 7.5 / 11.25 / 6.25
        → 整数部分 7 / 11 / 6（計24）→ 余りが最大の1つ目に+1 → 8 / 11 / 6

    Args:
        pool_counts: カテゴリ → そのカテゴリの問題数。
        n: 抽出したい問題数。全問題数より多い場合は全問題数に切り詰める。

    Returns:
        カテゴリ → 割り当てる問題数。
    """
    total = sum(pool_counts.values())
    n = min(n, total)
    if total == 0 or n <= 0:
        return {category: 0 for category in pool_counts}

    ideal = {c: n * count / total for c, count in pool_counts.items()}
    allocation = {c: int(value) for c, value in ideal.items()}
    shortage = n - sum(allocation.values())

    order = list(pool_counts)  # カテゴリの並び順（同点時の最終的な優先順位）
    by_remainder = sorted(
        pool_counts,
        key=lambda c: (-(ideal[c] - allocation[c]), -pool_counts[c], order.index(c)),
    )
    for category in by_remainder[:shortage]:
        allocation[category] += 1
    return allocation


def _group_by_category(questions: Iterable[Question]) -> dict[str, list[Question]]:
    """問題をカテゴリごとにまとめる（定義済みカテゴリの順に並べる）。"""
    groups: dict[str, list[Question]] = {c: [] for c in CATEGORIES}
    for q in questions:
        groups.setdefault(q.category, []).append(q)
    return {c: qs for c, qs in groups.items() if qs}


def stratified_sample(
    questions: Sequence[Question],
    n: int,
    rng: random.Random,
    answered_ids: set[str] | None = None,
    prefer_unanswered: bool = True,
) -> list[Question]:
    """模試用に、カテゴリ構成比を保って n 問をランダムに選ぶ。

    prefer_unanswered が True の場合、各カテゴリの中で「まだ解いていない問題」を
    先に選び、足りない分だけ解いたことのある問題から補う。

    Args:
        questions: 問題プール。
        n: 出題数。
        rng: 乱数生成器（テストで結果を固定できるよう外から渡す）。
        answered_ids: 過去に回答したことのある問題idの集合。
        prefer_unanswered: 未回答の問題を優先するか。

    Returns:
        選ばれた問題のリスト（カテゴリが偏らないよう最後にシャッフル済み）。
    """
    answered_ids = answered_ids or set()
    groups = _group_by_category(questions)
    allocation = allocate_by_ratio({c: len(qs) for c, qs in groups.items()}, n)

    selected: list[Question] = []
    for category, quota in allocation.items():
        candidates = list(groups[category])
        rng.shuffle(candidates)
        if prefer_unanswered:
            # 並べ替えは安定ソートなので、シャッフルした順序は保ったまま未回答が前に来る
            candidates.sort(key=lambda q: q.id in answered_ids)
        selected.extend(candidates[:quota])

    rng.shuffle(selected)
    return selected


# ---------------------------------------------------------------
# 1問1答用: 出題範囲と出題順
# ---------------------------------------------------------------


class DrillScope(str, Enum):
    """1問1答の出題範囲。"""

    ALL = "all"
    CATEGORY = "category"
    UNANSWERED = "unanswered"
    WRONG = "wrong"
    REVIEW = "review"


#: 出題範囲の画面表示名
DRILL_SCOPE_LABELS: dict[DrillScope, str] = {
    DrillScope.ALL: "全問",
    DrillScope.CATEGORY: "カテゴリ指定",
    DrillScope.UNANSWERED: "未回答のみ",
    DrillScope.WRONG: "誤答のみ（直近の回答が不正解）",
    DrillScope.REVIEW: "要復習フラグのみ",
}


class DrillOrder(str, Enum):
    """1問1答の出題順。"""

    SEQUENTIAL = "sequential"
    RANDOM = "random"


#: 出題順の画面表示名
DRILL_ORDER_LABELS: dict[DrillOrder, str] = {
    DrillOrder.SEQUENTIAL: "順番通り",
    DrillOrder.RANDOM: "ランダム",
}


def select_drill_questions(
    questions: Sequence[Question],
    scope: DrillScope,
    order: DrillOrder,
    rng: random.Random,
    *,
    category: str | None = None,
    answered_ids: set[str] | None = None,
    wrong_ids: set[str] | None = None,
    review_ids: set[str] | None = None,
) -> list[Question]:
    """1問1答で出題する問題を、範囲と順序の指定に従って選ぶ。

    Args:
        questions: 問題プール。
        scope: 出題範囲。
        order: 出題順。順番通りの場合は問題id順。
        rng: 乱数生成器（ランダム順のときに使う）。
        category: scope が CATEGORY のときに対象とするカテゴリ。
        answered_ids: 回答したことのある問題id（UNANSWERED で使う）。
        wrong_ids: 直近の回答が不正解の問題id（WRONG で使う）。
        review_ids: 要復習フラグ付きの問題id（REVIEW で使う）。

    Returns:
        出題する問題のリスト。
    """
    answered_ids = answered_ids or set()
    wrong_ids = wrong_ids or set()
    review_ids = review_ids or set()

    filters = {
        DrillScope.ALL: lambda q: True,
        DrillScope.CATEGORY: lambda q: q.category == category,
        DrillScope.UNANSWERED: lambda q: q.id not in answered_ids,
        DrillScope.WRONG: lambda q: q.id in wrong_ids,
        DrillScope.REVIEW: lambda q: q.id in review_ids,
    }
    selected = sorted((q for q in questions if filters[scope](q)), key=lambda q: q.id)
    if order == DrillOrder.RANDOM:
        rng.shuffle(selected)
    return selected
