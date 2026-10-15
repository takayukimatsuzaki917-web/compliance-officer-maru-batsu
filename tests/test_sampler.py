"""出題選択（層化抽出・1問1答の範囲指定）のテスト。"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from conftest import make_question
from quiz.sampler import DrillOrder, DrillScope, allocate_by_ratio, select_drill_questions, stratified_sample

# ---------------------------------------------------------------
# allocate_by_ratio（比率に応じた問題数の割り振り）
# ---------------------------------------------------------------


def test_allocate_matches_planned_ratio():
    # 60:90:50 から25問 → 7.5 / 11.25 / 6.25 → 余りが最大の内部管理に+1
    allocation = allocate_by_ratio({"内部管理・内部統制": 60, "保険募集規制": 90, "生命保険協会ガイドライン": 50}, 25)
    assert allocation == {"内部管理・内部統制": 8, "保険募集規制": 11, "生命保険協会ガイドライン": 6}


@pytest.mark.parametrize("n", [1, 7, 24, 25, 26, 100, 199, 200])
def test_allocate_total_equals_n(n):
    allocation = allocate_by_ratio({"A": 60, "B": 90, "C": 50}, n)
    assert sum(allocation.values()) == n


def test_allocate_never_exceeds_pool():
    allocation = allocate_by_ratio({"A": 1, "B": 3, "C": 1}, 25)
    assert allocation == {"A": 1, "B": 3, "C": 1}


def test_allocate_empty_pool():
    assert allocate_by_ratio({"A": 0}, 25) == {"A": 0}


def test_allocate_tie_breaks_by_pool_size():
    # 理想値 0.5 / 1.5 で余りが同じ（各0.5）→ 問題数の多い B を優先する
    assert allocate_by_ratio({"A": 10, "B": 30}, 2) == {"A": 0, "B": 2}


def test_allocate_tie_breaks_by_definition_order():
    # 余りも問題数も同じなら、先に定義されたカテゴリを優先する
    assert allocate_by_ratio({"A": 10, "B": 10, "C": 20}, 2) == {"A": 1, "B": 0, "C": 1}


# ---------------------------------------------------------------
# stratified_sample（模試の層化抽出）
# ---------------------------------------------------------------


def test_stratified_sample_category_composition(question_pool):
    selected = stratified_sample(question_pool, 25, random.Random(0))
    counts = Counter(q.category for q in selected)
    assert counts == {"内部管理・内部統制": 8, "保険募集規制": 11, "生命保険協会ガイドライン": 6}


def test_stratified_sample_has_no_duplicates(question_pool):
    selected = stratified_sample(question_pool, 25, random.Random(1))
    assert len({q.id for q in selected}) == 25


def test_stratified_sample_prefers_unanswered(question_pool):
    # 各カテゴリで未回答の問題が十分あるので、回答済みは1問も選ばれないはず
    answered = {q.id for q in question_pool[::2]}  # 半分を回答済みにする
    for seed in range(20):
        selected = stratified_sample(question_pool, 25, random.Random(seed), answered_ids=answered)
        assert all(q.id not in answered for q in selected)


def test_stratified_sample_fills_with_answered_when_unanswered_is_short(question_pool):
    # 未回答が5問しかない場合、その5問は必ず含まれ、残りは回答済みから補う
    unanswered = {"q001", "q061", "q062", "q151", "q152"}
    answered = {q.id for q in question_pool} - unanswered
    selected = stratified_sample(question_pool, 25, random.Random(3), answered_ids=answered)
    assert unanswered <= {q.id for q in selected}
    assert len(selected) == 25


def test_stratified_sample_without_preference_can_pick_answered(question_pool):
    answered = {q.id for q in question_pool[::2]}
    picked_answered = False
    for seed in range(20):
        selected = stratified_sample(question_pool, 25, random.Random(seed), answered_ids=answered, prefer_unanswered=False)
        picked_answered |= any(q.id in answered for q in selected)
    assert picked_answered


def test_stratified_sample_small_pool():
    pool = [make_question("s001"), make_question("s002", "内部管理・内部統制")]
    selected = stratified_sample(pool, 25, random.Random(0))
    assert {q.id for q in selected} == {"s001", "s002"}


def test_stratified_sample_is_reproducible_with_seed(question_pool):
    first = stratified_sample(question_pool, 25, random.Random(42))
    second = stratified_sample(question_pool, 25, random.Random(42))
    assert [q.id for q in first] == [q.id for q in second]


# ---------------------------------------------------------------
# select_drill_questions（1問1答の出題範囲・出題順）
# ---------------------------------------------------------------


@pytest.fixture
def drill_pool():
    return [
        make_question("q003", "保険募集規制"),
        make_question("q001", "内部管理・内部統制"),
        make_question("q002", "生命保険協会ガイドライン"),
        make_question("q004", "保険募集規制"),
    ]


def _ids(questions):
    return [q.id for q in questions]


def test_drill_all_sequential_sorted_by_id(drill_pool):
    selected = select_drill_questions(drill_pool, DrillScope.ALL, DrillOrder.SEQUENTIAL, random.Random(0))
    assert _ids(selected) == ["q001", "q002", "q003", "q004"]


def test_drill_random_contains_same_questions(drill_pool):
    selected = select_drill_questions(drill_pool, DrillScope.ALL, DrillOrder.RANDOM, random.Random(0))
    assert sorted(_ids(selected)) == ["q001", "q002", "q003", "q004"]


def test_drill_category(drill_pool):
    selected = select_drill_questions(drill_pool, DrillScope.CATEGORY, DrillOrder.SEQUENTIAL, random.Random(0), category="保険募集規制")
    assert _ids(selected) == ["q003", "q004"]


def test_drill_unanswered(drill_pool):
    selected = select_drill_questions(drill_pool, DrillScope.UNANSWERED, DrillOrder.SEQUENTIAL, random.Random(0), answered_ids={"q001", "q003"})
    assert _ids(selected) == ["q002", "q004"]


def test_drill_wrong(drill_pool):
    selected = select_drill_questions(drill_pool, DrillScope.WRONG, DrillOrder.SEQUENTIAL, random.Random(0), wrong_ids={"q004"})
    assert _ids(selected) == ["q004"]


def test_drill_review(drill_pool):
    selected = select_drill_questions(drill_pool, DrillScope.REVIEW, DrillOrder.SEQUENTIAL, random.Random(0), review_ids={"q002", "q999"})
    assert _ids(selected) == ["q002"]
