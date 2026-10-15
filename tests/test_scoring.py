"""採点・合否判定のテスト。"""

from __future__ import annotations

import pytest

from conftest import make_question
from quiz.scoring import ExamResult, grade, required_score


@pytest.mark.parametrize(
    ("total", "ratio", "expected"),
    [
        (25, 0.7, 18),  # 17.5 → 切り上げて18
        (10, 0.7, 7),  # ちょうど7（浮動小数点の誤差で8にならないこと）
        (25, 0.6, 15),
        (5, 0.7, 4),
        (25, 1.0, 25),
    ],
)
def test_required_score(total, ratio, expected):
    assert required_score(total, ratio) == expected


@pytest.fixture
def questions():
    return [
        make_question("q1", "内部管理・内部統制", answer=True),
        make_question("q2", "内部管理・内部統制", answer=False),
        make_question("q3", "保険募集規制", answer=True),
        make_question("q4", "生命保険協会ガイドライン", answer=False),
    ]


def test_grade_counts_correct_answers(questions):
    result = grade(questions, {"q1": True, "q2": True, "q3": True, "q4": False}, 0.7)
    assert result.score == 3
    assert result.total == 4
    assert result.ratio == pytest.approx(0.75)


def test_unanswered_is_incorrect(questions):
    result = grade(questions, {"q1": True}, 0.7)
    assert result.score == 1
    assert result.unanswered_count == 3
    assert result.items[1].user_answer is None and not result.items[1].is_correct


def test_pass_boundary(questions):
    # 4問 × 0.7 = 2.8 → 3問以上で合格
    assert grade(questions, {"q1": True, "q2": False, "q3": True}, 0.7).passed
    assert not grade(questions, {"q1": True, "q2": False}, 0.7).passed


def test_empty_exam_is_not_passed():
    assert not grade([], {}, 0.7).passed


def test_keeps_question_order(questions):
    result = grade(list(reversed(questions)), {}, 0.7)
    assert [item.question_id for item in result.items] == ["q4", "q3", "q2", "q1"]


def test_category_scores_in_defined_order(questions):
    result = grade(list(reversed(questions)), {"q1": True, "q2": False, "q4": True}, 0.7)
    scores = {s.category: (s.correct, s.total) for s in result.category_scores()}
    assert list(scores) == ["内部管理・内部統制", "保険募集規制", "生命保険協会ガイドライン"]
    assert scores == {
        "内部管理・内部統制": (2, 2),
        "保険募集規制": (0, 1),
        "生命保険協会ガイドライン": (0, 1),
    }


def test_result_round_trip(questions):
    result = grade(questions, {"q1": True, "q2": True}, 0.7)
    restored = ExamResult.from_dict(result.to_dict())
    assert restored == result
    assert restored.score == result.score
