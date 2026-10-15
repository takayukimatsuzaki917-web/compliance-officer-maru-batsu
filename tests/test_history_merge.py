"""複数端末の履歴の統合（merge_history）のテスト。"""

from __future__ import annotations

from quiz.history import merge_history, normalize_history


def _attempt(aid, at, correct=True):
    return {"id": aid, "at": at, "mode": "drill", "user_answer": True, "correct": correct}


def test_merge_with_no_remote_returns_local():
    local = {"question_stats": {"q1": {"attempts": [_attempt("a", "2026-10-15T10:00:00+09:00")]}}}
    merged = merge_history(None, local)
    assert merged["question_stats"]["q1"]["attempts"] == local["question_stats"]["q1"]["attempts"]


def test_attempts_are_unioned_without_duplicates_and_sorted():
    remote = {"question_stats": {"q1": {"attempts": [_attempt("a", "2026-10-15T10:00:00+09:00"), _attempt("c", "2026-10-15T12:00:00+09:00")]}}}
    local = {"question_stats": {"q1": {"attempts": [_attempt("a", "2026-10-15T10:00:00+09:00"), _attempt("b", "2026-10-15T11:00:00+09:00", correct=False)]}}}
    attempts = merge_history(remote, local)["question_stats"]["q1"]["attempts"]
    assert [a["id"] for a in attempts] == ["a", "b", "c"]


def test_questions_only_on_one_side_are_kept():
    remote = {"question_stats": {"q1": {"attempts": [_attempt("a", "2026-10-15T10:00:00+09:00")]}}}
    local = {"question_stats": {"q2": {"attempts": [_attempt("b", "2026-10-15T11:00:00+09:00")]}}}
    assert set(merge_history(remote, local)["question_stats"]) == {"q1", "q2"}


def test_newer_review_flag_wins():
    remote = {"question_stats": {"q1": {"attempts": [], "review_flag": True, "review_flag_at": "2026-10-15T12:00:00+09:00"}}}
    local = {"question_stats": {"q1": {"attempts": [], "review_flag": False, "review_flag_at": "2026-10-15T10:00:00+09:00"}}}
    assert merge_history(remote, local)["question_stats"]["q1"]["review_flag"] is True
    # 手元のほうが新しければ手元を採用
    local["question_stats"]["q1"]["review_flag_at"] = "2026-10-15T13:00:00+09:00"
    assert merge_history(remote, local)["question_stats"]["q1"]["review_flag"] is False


def test_mock_results_are_unioned_and_sorted_by_finish_time():
    remote = {"mock_results": [{"id": "m2", "finished_at": "2026-10-15T12:00:00+09:00"}]}
    local = {"mock_results": [{"id": "m1", "finished_at": "2026-10-15T10:00:00+09:00"}, {"id": "m2", "finished_at": "2026-10-15T12:00:00+09:00"}]}
    assert [m["id"] for m in merge_history(remote, local)["mock_results"]] == ["m1", "m2"]


def test_newer_preferences_win():
    remote = {"preferences": {"include_draft": False, "updated_at": "2026-10-15T12:00:00+09:00"}}
    local = {"preferences": {"include_draft": True, "updated_at": ""}}
    assert merge_history(remote, local)["preferences"]["include_draft"] is False


def test_records_without_id_are_deduplicated_by_content():
    old = {"at": "2026-10-15T10:00:00+09:00", "mode": "drill", "user_answer": True, "correct": True}
    remote = {"question_stats": {"q1": {"attempts": [dict(old)]}}}
    local = {"question_stats": {"q1": {"attempts": [dict(old)]}}}
    assert len(merge_history(remote, local)["question_stats"]["q1"]["attempts"]) == 1


def test_normalize_fills_missing_fields():
    data = normalize_history({"question_stats": {"q1": {}}})
    assert data["question_stats"]["q1"] == {"attempts": [], "review_flag": False, "review_flag_at": ""}
    assert data["preferences"]["include_draft"] is True
