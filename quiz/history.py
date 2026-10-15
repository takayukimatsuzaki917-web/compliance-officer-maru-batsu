"""学習履歴（history.json）の読み書きを行うモジュール。

history.json の構造:
{
  "version": 1,
  "question_stats": {               # 問題ごとの記録
    "q001": {
      "attempts": [                 # 回答の履歴（古い順）
        {"at": "2026-10-15T22:00:00+09:00", "mode": "drill", "user_answer": true, "correct": true}
      ],
      "review_flag": false          # 要復習フラグ
    }
  },
  "mock_results": [ ... ],          # 模試の結果（古い順）
  "preferences": {"include_draft": true}
}
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from quiz.scoring import ExamResult

#: history.json のデータ形式のバージョン（将来形式を変えるときの目印）
HISTORY_VERSION = 1

#: 回答したモード
MODE_DRILL = "drill"  # 1問1答
MODE_MOCK = "mock"  # 模試

#: 設定の既定値
DEFAULT_INCLUDE_DRAFT = True


class HistoryLoadError(Exception):
    """history.json が壊れていて読み込めないときに送出する例外。"""


def now_iso() -> str:
    """現在時刻をタイムゾーン付きの ISO 8601 文字列（秒まで）で返す。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _empty_history() -> dict[str, Any]:
    """空の履歴データを作る。"""
    return {
        "version": HISTORY_VERSION,
        "question_stats": {},
        "mock_results": [],
        "preferences": {"include_draft": DEFAULT_INCLUDE_DRAFT},
    }


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


class HistoryStore:
    """学習履歴を管理するクラス。

    変更系のメソッドを呼ぶと、その都度ファイルへ自動保存する。
    """

    def __init__(self, path: Path, data: dict[str, Any] | None = None, clock: Callable[[], str] = now_iso):
        """
        Args:
            path: 保存先の history.json のパス。
            data: 読み込み済みの履歴データ（None なら空の履歴）。
            clock: 現在時刻の文字列を返す関数（テストで時刻を固定するために差し替え可能）。
        """
        self.path = path
        self._clock = clock
        self._data = _empty_history()
        if data:
            self._data.update(data)
        # 古いファイルや手で編集したファイルでも動くよう、欠けている項目を補う
        self._data["preferences"] = {"include_draft": DEFAULT_INCLUDE_DRAFT, **self._data.get("preferences", {})}

    # -----------------------------------------------------------
    # 読み込み・保存
    # -----------------------------------------------------------

    @classmethod
    def load(cls, path: Path, clock: Callable[[], str] = now_iso) -> "HistoryStore":
        """history.json を読み込む。ファイルが無ければ空の履歴を返す。

        Raises:
            HistoryLoadError: ファイルが壊れている場合（勝手に上書きしないよう、エラーにする）。
        """
        if not path.exists():
            return cls(path, clock=clock)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HistoryLoadError(f"{path.name} を読み込めません: {exc}") from exc
        if not isinstance(data, dict):
            raise HistoryLoadError(f"{path.name} の形式が正しくありません（オブジェクトではありません）")
        return cls(path, data, clock=clock)

    def save(self) -> None:
        """履歴をファイルに保存する。

        書き込み途中でアプリが止まってもファイルが壊れないよう、
        一時ファイルに書いてから本来のファイル名に置き換える。
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)

    # -----------------------------------------------------------
    # 問題ごとの記録
    # -----------------------------------------------------------

    def _stats(self, question_id: str) -> dict[str, Any]:
        """問題ごとの記録を取得する（無ければ作る）。"""
        stats = self._data["question_stats"].setdefault(question_id, {})
        stats.setdefault("attempts", [])
        stats.setdefault("review_flag", False)
        return stats

    def _append_attempt(self, question_id: str, user_answer: bool, correct: bool, mode: str) -> None:
        """回答を1件追加する（保存はしない）。"""
        self._stats(question_id)["attempts"].append(
            {"at": self._clock(), "mode": mode, "user_answer": user_answer, "correct": correct}
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
        """要復習フラグを付け外しして保存する。"""
        self._stats(question_id)["review_flag"] = flagged
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
        self._data["mock_results"].append(record.to_dict())
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
        self.save()
