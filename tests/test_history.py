"""学習履歴（HistoryStore）の保存・読み込みのテスト。"""

from __future__ import annotations

import itertools
import json

import pytest

from conftest import make_question
from quiz.history import MODE_DRILL, MODE_MOCK, HistoryLoadError, HistoryStore, MockRecord
from quiz.history_backends import FileHistoryBackend, HistoryBackendError
from quiz.scoring import grade

FIXED_TIME = "2026-10-15T10:00:00+09:00"


def _fixed_clock() -> str:
    """テストで時刻を固定するための関数。"""
    return FIXED_TIME


def _id_factory():
    """テストで記録の id を固定するための関数（a1, a2, ... を順に返す）。"""
    counter = itertools.count(1)
    return lambda: f"a{next(counter)}"


@pytest.fixture
def history_path(tmp_path):
    return tmp_path / "history.json"


@pytest.fixture
def backend(history_path):
    return FileHistoryBackend(history_path)


@pytest.fixture
def store(backend):
    return HistoryStore.load(backend, clock=_fixed_clock, id_factory=_id_factory())


def _reload(backend):
    """保存先から読み直した HistoryStore を返す（保存されているかの確認用）。"""
    return HistoryStore.load(backend, clock=_fixed_clock)


def test_missing_file_gives_empty_history(store, history_path):
    assert store.answered_ids() == set()
    assert store.mock_records() == []
    assert store.latest_mock_record() is None
    assert store.include_draft is True
    assert not history_path.exists()  # 読み込むだけではファイルを作らない


def test_record_attempt_is_saved(store, backend):
    store.record_attempt("q001", True, True, MODE_DRILL)
    reloaded = _reload(backend)
    assert reloaded.answered_ids() == {"q001"}
    assert reloaded.attempts("q001") == [
        {"id": "a1", "at": FIXED_TIME, "mode": MODE_DRILL, "user_answer": True, "correct": True}
    ]


def test_wrong_ids_uses_latest_attempt(store):
    store.record_attempt("q001", False, False)
    store.record_attempt("q002", True, True)
    assert store.wrong_ids() == {"q001"}
    store.record_attempt("q001", True, True)  # 後で正解したら誤答から外れる
    assert store.wrong_ids() == set()


def test_review_flag(store, backend):
    store.set_review_flag("q001", True)
    assert _reload(backend).review_ids() == {"q001"}
    store.set_review_flag("q001", False)
    assert not _reload(backend).is_review_flagged("q001")


def test_review_flag_alone_does_not_count_as_answered(store):
    store.set_review_flag("q001", True)
    assert store.answered_ids() == set()


def test_add_mock_record(store, backend):
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

    reloaded = _reload(backend)
    assert reloaded.mock_records() == [record]
    assert reloaded.latest_mock_record() == record
    # 回答した問題だけが「解いた問題」として記録される
    assert reloaded.answered_ids() == {"q1", "q2"}
    assert reloaded.wrong_ids() == {"q2"}
    assert reloaded.attempts("q1")[0]["mode"] == MODE_MOCK


def test_mock_records_keep_order(backend):
    times = iter(["2026-10-15T10:00:00+09:00", "2026-10-15T11:00:00+09:00"])
    store = HistoryStore.load(backend, clock=_fixed_clock, id_factory=_id_factory())
    for score in (1, 2):
        answers = {"q1": True} if score == 2 else {}
        result = grade([make_question("q1"), make_question("q2")], answers, 0.7)
        finished = next(times)
        store.add_mock_record(MockRecord(finished, finished, False, (), result))
    assert [r.result.score for r in store.mock_records()] == [0, 1]
    assert store.latest_mock_record().result.score == 1


def test_include_draft_preference(store, backend):
    store.set_include_draft(False)
    assert _reload(backend).include_draft is False


def test_corrupted_file_raises(history_path):
    history_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(HistoryLoadError):
        HistoryStore.load(FileHistoryBackend(history_path))


def test_non_object_file_raises(history_path):
    history_path.write_text("[]", encoding="utf-8")
    with pytest.raises(HistoryLoadError):
        HistoryStore.load(FileHistoryBackend(history_path))


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
    assert HistoryStore.load(FileHistoryBackend(history_path)).include_draft is True


def test_old_attempts_without_id_are_still_readable(history_path):
    # 以前の形式（attempt に id が無い）の履歴も読み込める
    old = {"question_stats": {"q1": {"attempts": [{"at": FIXED_TIME, "mode": "drill", "user_answer": True, "correct": False}]}}}
    history_path.write_text(json.dumps(old), encoding="utf-8")
    store = HistoryStore.load(FileHistoryBackend(history_path))
    assert store.wrong_ids() == {"q1"}


class _FailingBackend:
    """保存に必ず失敗する保存先（通信エラーの再現用）。"""

    def load(self):
        return None

    def save(self, data):
        raise HistoryBackendError("通信エラー")

    def describe(self):
        return "テスト用"


def test_save_failure_keeps_local_data_and_reports_error():
    store = HistoryStore.load(_FailingBackend(), clock=_fixed_clock)
    store.record_attempt("q001", True, True)
    # 保存に失敗しても手元の履歴は残る
    assert store.answered_ids() == {"q001"}
    # 失敗理由は一度だけ取り出せる
    assert store.pop_last_error() == "通信エラー"
    assert store.pop_last_error() is None


def test_save_merges_records_written_by_another_device(backend):
    # 端末A・Bが同じ保存先を使い、それぞれ別の問題に回答した場合
    device_a = HistoryStore.load(backend, clock=_fixed_clock, id_factory=lambda: "from-a")
    device_b = HistoryStore.load(backend, clock=_fixed_clock, id_factory=lambda: "from-b")
    device_a.record_attempt("q001", True, True)
    device_b.record_attempt("q002", False, False)  # A の記録を上書きせず統合して保存される

    reloaded = _reload(backend)
    assert reloaded.answered_ids() == {"q001", "q002"}
    # 保存した側（B）にも A の記録が取り込まれている
    assert device_b.answered_ids() == {"q001", "q002"}


def test_reload_brings_in_other_device_records(backend):
    device_a = HistoryStore.load(backend, clock=_fixed_clock, id_factory=lambda: "from-a")
    device_b = HistoryStore.load(backend, clock=_fixed_clock, id_factory=lambda: "from-b")
    device_a.record_attempt("q001", True, True)
    assert device_b.answered_ids() == set()
    device_b.reload()
    assert device_b.answered_ids() == {"q001"}
