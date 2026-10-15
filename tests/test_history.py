"""学習履歴（history.json）の保存・読み込みのテスト。"""

from __future__ import annotations

import json

import pytest

from conftest import make_question
from quiz.history import MODE_DRILL, MODE_MOCK, HistoryLoadError, HistoryStore, MockRecord
from quiz.scoring import grade

FIXED_TIME = "2026-10-15T10:00:00+09:00"


def _fixed_clock() -> str:
    """テストで時刻を固定するための関数。"""
    return FIXED_TIME


@pytest.fixture
def history_path(tmp_path):
    return tmp_path / "history.json"


@pytest.fixture
def store(history_path):
    return HistoryStore.load(history_path, clock=_fixed_clock)


def _reload(path):
    """ファイルから読み直した HistoryStore を返す（保存されているかの確認用）。"""
    return HistoryStore.load(path, clock=_fixed_clock)


def test_missing_file_gives_empty_history(store, history_path):
    assert store.answered_ids() == set()
    assert store.mock_records() == []
    assert store.latest_mock_record() is None
    assert store.include_draft is True
    assert not history_path.exists()  # 読み込むだけではファイルを作らない


def test_record_attempt_is_saved(store, history_path):
    store.record_attempt("q001", True, True, MODE_DRILL)
    reloaded = _reload(history_path)
    assert reloaded.answered_ids() == {"q001"}
    assert reloaded.attempts("q001") == [{"at": FIXED_TIME, "mode": MODE_DRILL, "user_answer": True, "correct": True}]


def test_wrong_ids_uses_latest_attempt(store):
    store.record_attempt("q001", False, False)
    store.record_attempt("q002", True, True)
    assert store.wrong_ids() == {"q001"}
    store.record_attempt("q001", True, True)  # 後で正解したら誤答から外れる
    assert store.wrong_ids() == set()


def test_review_flag(store, history_path):
    store.set_review_flag("q001", True)
    assert _reload(history_path).review_ids() == {"q001"}
    store.set_review_flag("q001", False)
    assert not _reload(history_path).is_review_flagged("q001")


def test_review_flag_alone_does_not_count_as_answered(store):
    store.set_review_flag("q001", True)
    assert store.answered_ids() == set()


def test_add_mock_record(store, history_path):
    questions = [make_question("q1", answer=True), make_question("q2", answer=False), make_question("q3")]
    result = grade(questions, {"q1": True, "q2": True}, 0.7)  # q3 は未回答
    record = MockRecord(
        started_at="2026-10-15T09:30:00+09:00",
        finished_at=FIXED_TIME,
        timed_out=True,
        flagged_ids=("q2",),
        result=result,
    )
    store.add_mock_record(record)

    reloaded = _reload(history_path)
    assert reloaded.mock_records() == [record]
    assert reloaded.latest_mock_record() == record
    # 回答した問題だけが「解いた問題」として記録される
    assert reloaded.answered_ids() == {"q1", "q2"}
    assert reloaded.wrong_ids() == {"q2"}
    assert reloaded.attempts("q1")[0]["mode"] == MODE_MOCK


def test_mock_records_keep_order(store):
    for score in (1, 2):
        answers = {"q1": True} if score == 2 else {}
        result = grade([make_question("q1"), make_question("q2")], answers, 0.7)
        store.add_mock_record(MockRecord(FIXED_TIME, FIXED_TIME, False, (), result))
    assert [r.result.score for r in store.mock_records()] == [0, 1]
    assert store.latest_mock_record().result.score == 1


def test_include_draft_preference(store, history_path):
    store.set_include_draft(False)
    assert _reload(history_path).include_draft is False


def test_corrupted_file_raises(history_path):
    history_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(HistoryLoadError):
        HistoryStore.load(history_path)


def test_non_object_file_raises(history_path):
    history_path.write_text("[]", encoding="utf-8")
    with pytest.raises(HistoryLoadError):
        HistoryStore.load(history_path)


def test_save_leaves_no_temp_file(store, history_path):
    store.record_attempt("q001", True, True)
    assert history_path.exists()
    assert not history_path.with_name(history_path.name + ".tmp").exists()


def test_saved_file_is_readable_json(store, history_path):
    store.record_attempt("q001", True, True)
    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert "q001" in data["question_stats"]


def test_old_file_without_preferences_gets_defaults(history_path):
    history_path.write_text(json.dumps({"version": 1, "question_stats": {}, "mock_results": []}), encoding="utf-8")
    assert HistoryStore.load(history_path).include_draft is True
