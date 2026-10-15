"""類似・重複チェックのテスト。"""

from __future__ import annotations

from conftest import make_record
from quiz.models import Question
from quiz.similarity import find_similar_pairs, normalize_statement


def _q(qid: str, statement: str) -> Question:
    return Question.from_dict(make_record(id=qid, statement=statement))


def test_normalize_removes_label_and_punctuation():
    assert normalize_statement("【サンプル】保険募集人は、 特別利益を（提供）できない。") == "保険募集人は特別利益を提供できない"


def test_finds_near_duplicate():
    questions = [
        _q("q1", "保険募集人は、保険料の割引を約束してはならない。"),
        _q("q2", "保険募集人は保険料の割引を約束してはならない"),
        _q("q3", "内部監査部門は第3線に位置づけられる。"),
    ]
    pairs = find_similar_pairs(questions, threshold=0.8)
    assert [(p.first.id, p.second.id) for p in pairs] == [("q1", "q2")]
    assert pairs[0].ratio == 1.0


def test_no_pairs_for_different_questions():
    questions = [_q("q1", "意向把握・確認義務の問題"), _q("q2", "反社会的勢力への対応の問題文")]
    assert find_similar_pairs(questions, threshold=0.75) == []
