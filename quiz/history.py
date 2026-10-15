"""学習履歴の読み書きを行うモジュール。

履歴データの構造（JSON）:
{
  "version": 1,
  "question_stats": {               # 問題ごとの記録
    "q001": {
      "attempts": [                 # 回答の履歴（古い順）
        {"id": "…", "at": "2026-10-15T22:00:00+09:00", "mode": "drill", "user_answer": true, "correct": true}
      ],
      "review_flag": false,         # 要復習フラグ
      "review_flag_at": "…"         # 要復習フラグを最後に変更した日時
    }
  },
  "mock_results": [ ... ],          # 模試の結果（古い順）
  "preferences": {"include_draft": true, "updated_at": "…"}
}

保存先（ローカルファイル / GitHub Gist）は quiz/history_backends.py で定義しており、
HistoryStore は保存先の違いを意識せずに使える。

複数のPCで同時に使っても履歴が失われないよう、保存のたびに
「保存先の最新の内容」と「手元の内容」を統合（マージ）してから書き込む。
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from quiz.history_backends import HistoryBackend, HistoryBackendError
from quiz.scoring import ExamResult

#: 履歴データの形式のバージョン（将来形式を変えるときの目印）
HISTORY_VERSION = 1

#: 回答したモード
MODE_DRILL = "drill"  # 1問1答
MODE_MOCK = "mock"  # 模試

#: 設定の既定値
DEFAULT_INCLUDE_DRAFT = True

#: 「一度も変更していない」ことを表す日時（どの日時よりも古いものとして扱う）
NEVER = ""

#: 日本時間（UTC+9）。Windows でも追加パッケージなしで使えるよう、固定のオフセットで定義する
JST = timezone(timedelta(hours=9), "JST")


class HistoryLoadError(Exception):
    """履歴が壊れている・取得できないなどの理由で読み込めないときに送出する例外。"""


def now_iso() -> str:
    """現在時刻を日本時間の ISO 8601 文字列（秒まで）で返す。

    クラウド上のサーバーは協定世界時（UTC）で動いていることが多いため、
    どこで動かしても日本時間で記録されるよう、タイムゾーンを固定している。
    （時刻の文字列をそのまま比較して新旧を判定するため、全端末で同じタイムゾーンにそろえる必要がある）
    """
    return datetime.now(JST).isoformat(timespec="seconds")


def new_record_id() -> str:
    """回答や模試の記録を区別するための一意な id を作る。"""
    return uuid.uuid4().hex


def _empty_history() -> dict[str, Any]:
    """空の履歴データを作る。"""
    return {
        "version": HISTORY_VERSION,
        "question_stats": {},
        "mock_results": [],
        "preferences": {"include_draft": DEFAULT_INCLUDE_DRAFT, "updated_at": NEVER},
    }


def normalize_history(data: dict[str, Any] | None) -> dict[str, Any]:
    """古い形式や手で編集したデータでも扱えるよう、欠けている項目を補った複製を返す。"""
    result = _empty_history()
    if not data:
        return result
    source = copy.deepcopy(data)
    for qid, stats in (source.get("question_stats") or {}).items():
        result["question_stats"][qid] = {
            "attempts": list(stats.get("attempts", [])),
            "review_flag": bool(stats.get("review_flag", False)),
            "review_flag_at": stats.get("review_flag_at", NEVER),
        }
    result["mock_results"] = list(source.get("mock_results") or [])
    result["preferences"].update(source.get("preferences") or {})
    return result


# ---------------------------------------------------------------
# 複数端末の履歴の統合（マージ）
# ---------------------------------------------------------------


def _attempt_key(attempt: dict[str, Any]) -> Any:
    """回答記録を同一と判定するためのキー（id が無い古い記録は内容で判定）。"""
    return attempt.get("id") or (attempt.get("at"), attempt.get("mode"), attempt.get("user_answer"), attempt.get("correct"))


def _mock_key(record: dict[str, Any]) -> Any:
    """模試記録を同一と判定するためのキー（id が無い古い記録は開始・終了時刻で判定）。"""
    return record.get("id") or (record.get("started_at"), record.get("finished_at"))


def _union(first: Iterable[dict[str, Any]], second: Iterable[dict[str, Any]], key: Callable[[dict[str, Any]], Any]) -> list[dict[str, Any]]:
    """2つの記録のリストを、重複を除いて1つにまとめる（先に出てきたものを残す）。"""
    merged: dict[Any, dict[str, Any]] = {}
    for record in [*first, *second]:
        merged.setdefault(key(record), record)
    return list(merged.values())


def merge_history(remote: dict[str, Any] | None, local: dict[str, Any]) -> dict[str, Any]:
    """保存先の履歴（remote）と手元の履歴（local）を統合する。

    統合のルール:
      - 回答記録・模試記録 … 両方の記録を重複なしで合わせ、日時順に並べる（記録は消えない）
      - 要復習フラグ・設定 … 最後に変更されたほうを採用する（同時刻なら手元を優先）

    Args:
        remote: 保存先にある最新の履歴（未保存なら None）。
        local: このアプリが手元に持っている履歴。

    Returns:
        統合後の履歴。
    """
    remote_data = normalize_history(remote)
    local_data = normalize_history(local)
    result = _empty_history()

    remote_stats = remote_data["question_stats"]
    local_stats = local_data["question_stats"]
    for qid in sorted(set(remote_stats) | set(local_stats)):
        r = remote_stats.get(qid, {"attempts": [], "review_flag": False, "review_flag_at": NEVER})
        l = local_stats.get(qid, {"attempts": [], "review_flag": False, "review_flag_at": NEVER})
        attempts = sorted(_union(r["attempts"], l["attempts"], _attempt_key), key=lambda a: a.get("at", ""))
        newer = l if l["review_flag_at"] >= r["review_flag_at"] else r
        result["question_stats"][qid] = {
            "attempts": attempts,
            "review_flag": newer["review_flag"],
            "review_flag_at": newer["review_flag_at"],
        }

    result["mock_results"] = sorted(
        _union(remote_data["mock_results"], local_data["mock_results"], _mock_key),
        key=lambda m: m.get("finished_at", ""),
    )

    remote_pref = remote_data["preferences"]
    local_pref = local_data["preferences"]
    result["preferences"] = dict(local_pref if local_pref["updated_at"] >= remote_pref["updated_at"] else remote_pref)
    return result


# ---------------------------------------------------------------
# 模試の記録
# ---------------------------------------------------------------


@dataclass(frozen=True)
class MockRecord:
    """模試1回分の記録。"""

    started_at: str  # 開始時刻
    finished_at: str  # 終了（採点）時刻
    timed_out: bool  # 時間切れで終了したか
    flagged_ids: tuple[str, ...]  # 「後で見直す」を付けた問題id
    result: ExamResult  # 採点結果

    def to_dict(self) -> dict[str, Any]:
        """履歴保存用の辞書に変換する。"""
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "timed_out": self.timed_out,
            "flagged_ids": list(self.flagged_ids),
            **self.result.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MockRecord":
        """履歴の辞書から復元する。"""
        return cls(
            started_at=data["started_at"],
            finished_at=data["finished_at"],
            timed_out=data.get("timed_out", False),
            flagged_ids=tuple(data.get("flagged_ids", [])),
            result=ExamResult.from_dict(data),
        )


# ---------------------------------------------------------------
# 履歴の管理
# ---------------------------------------------------------------


class HistoryStore:
    """学習履歴を管理するクラス。

    変更系のメソッドを呼ぶと、その都度保存先へ自動保存する。
    保存に失敗しても手元の履歴は残し、失敗理由を last_error に記録する
    （画面側で警告を表示し、次の保存時に再度書き込みを試みる）。
    """

    def __init__(
        self,
        backend: HistoryBackend,
        data: dict[str, Any] | None = None,
        clock: Callable[[], str] = now_iso,
        id_factory: Callable[[], str] = new_record_id,
    ):
        """
        Args:
            backend: 履歴の保存先（FileHistoryBackend / GistHistoryBackend など）。
            data: 読み込み済みの履歴データ（None なら空の履歴）。
            clock: 現在時刻の文字列を返す関数（テストで時刻を固定するために差し替え可能）。
            id_factory: 記録の id を作る関数（テストで id を固定するために差し替え可能）。
        """
        self.backend = backend
        self._clock = clock
        self._new_id = id_factory
        self._data = normalize_history(data)
        self.last_error: str | None = None

    # -----------------------------------------------------------
    # 読み込み・保存
    # -----------------------------------------------------------

    @classmethod
    def load(
        cls,
        backend: HistoryBackend,
        clock: Callable[[], str] = now_iso,
        id_factory: Callable[[], str] = new_record_id,
    ) -> "HistoryStore":
        """保存先から履歴を読み込む。まだ何も保存されていなければ空の履歴を返す。

        Raises:
            HistoryLoadError: 保存内容が壊れている・通信できない場合（勝手に上書きしないよう、エラーにする）。
        """
        try:
            data = backend.load()
        except HistoryBackendError as exc:
            raise HistoryLoadError(str(exc)) from exc
        return cls(backend, data, clock=clock, id_factory=id_factory)

    def save(self) -> bool:
        """保存先の最新の履歴と手元の履歴を統合して保存する。

        Returns:
            保存に成功したら True、失敗したら False（理由は last_error に入る）。
        """
        try:
            merged = merge_history(self.backend.load(), self._data)
            self.backend.save(merged)
        except HistoryBackendError as exc:
            self.last_error = str(exc)
            return False
        self._data = merged
        self.last_error = None
        return True

    def reload(self) -> None:
        """保存先の最新の履歴を読み込み直し、手元の履歴と統合する（保存はしない）。

        Raises:
            HistoryLoadError: 保存先から読み込めない場合。
        """
        try:
            remote = self.backend.load()
        except HistoryBackendError as exc:
            raise HistoryLoadError(str(exc)) from exc
        self._data = merge_history(remote, self._data)

    def pop_last_error(self) -> str | None:
        """直近の保存エラーを取り出して消去する（画面に一度だけ表示するため）。"""
        error, self.last_error = self.last_error, None
        return error

    @property
    def storage_description(self) -> str:
        """保存先の説明（画面表示用）。"""
        return self.backend.describe()

    # -----------------------------------------------------------
    # 問題ごとの記録
    # -----------------------------------------------------------

    def _stats(self, question_id: str) -> dict[str, Any]:
        """問題ごとの記録を取得する（無ければ作る）。"""
        return self._data["question_stats"].setdefault(
            question_id, {"attempts": [], "review_flag": False, "review_flag_at": NEVER}
        )

    def _append_attempt(self, question_id: str, user_answer: bool, correct: bool, mode: str) -> None:
        """回答を1件追加する（保存はしない）。"""
        self._stats(question_id)["attempts"].append(
            {"id": self._new_id(), "at": self._clock(), "mode": mode, "user_answer": user_answer, "correct": correct}
        )

    def record_attempt(self, question_id: str, user_answer: bool, correct: bool, mode: str = MODE_DRILL) -> None:
        """回答を1件記録して保存する。

        Args:
            question_id: 問題id。
            user_answer: 回答（True=○ / False=✕）。
            correct: 正解だったか。
            mode: 回答したモード（MODE_DRILL / MODE_MOCK）。
        """
        self._append_attempt(question_id, user_answer, correct, mode)
        self.save()

    def attempts(self, question_id: str) -> list[dict[str, Any]]:
        """問題の回答履歴（古い順）を返す。"""
        stats = self._data["question_stats"].get(question_id, {})
        return list(stats.get("attempts", []))

    def answered_ids(self) -> set[str]:
        """1回以上回答したことのある問題idの集合。"""
        return {qid for qid, stats in self._data["question_stats"].items() if stats.get("attempts")}

    def wrong_ids(self) -> set[str]:
        """直近の回答が不正解だった問題idの集合（後で正解すれば外れる）。"""
        return {
            qid
            for qid, stats in self._data["question_stats"].items()
            if stats.get("attempts") and not stats["attempts"][-1]["correct"]
        }

    def review_ids(self) -> set[str]:
        """要復習フラグが付いている問題idの集合。"""
        return {qid for qid, stats in self._data["question_stats"].items() if stats.get("review_flag")}

    def is_review_flagged(self, question_id: str) -> bool:
        """要復習フラグが付いていれば True。"""
        return question_id in self.review_ids()

    def set_review_flag(self, question_id: str, flagged: bool) -> None:
        """要復習フラグを付け外しして保存する（変更日時も記録し、端末間の統合に使う）。"""
        stats = self._stats(question_id)
        stats["review_flag"] = flagged
        stats["review_flag_at"] = self._clock()
        self.save()

    # -----------------------------------------------------------
    # 模試の記録
    # -----------------------------------------------------------

    def add_mock_record(self, record: MockRecord) -> None:
        """模試の結果を保存する。

        回答した問題は「解いた問題」として問題ごとの記録にも追加する
        （未回答の問題は追加しない）。
        """
        for item in record.result.items:
            if item.user_answer is not None:
                self._append_attempt(item.question_id, item.user_answer, item.is_correct, MODE_MOCK)
        self._data["mock_results"].append({"id": self._new_id(), **record.to_dict()})
        self.save()

    def mock_records(self) -> list[MockRecord]:
        """模試の記録を古い順に返す。"""
        return [MockRecord.from_dict(raw) for raw in self._data["mock_results"]]

    def latest_mock_record(self) -> MockRecord | None:
        """直近の模試の記録（無ければ None）。"""
        records = self._data["mock_results"]
        return MockRecord.from_dict(records[-1]) if records else None

    # -----------------------------------------------------------
    # 設定
    # -----------------------------------------------------------

    @property
    def include_draft(self) -> bool:
        """draft（根拠未確認）の問題を出題に含めるか。"""
        return bool(self._data["preferences"]["include_draft"])

    def set_include_draft(self, include: bool) -> None:
        """draft を出題に含めるかを変更して保存する。"""
        self._data["preferences"]["include_draft"] = include
        self._data["preferences"]["updated_at"] = self._clock()
        self.save()
