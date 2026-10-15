"""問題データ（data/questions/*.json）を読み込むモジュール。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quiz.models import Question
from quiz.validator import ValidationError, validate_records

#: 問題ファイルとして読み込むファイル名のパターン
QUESTION_FILE_PATTERN = "*.json"


@dataclass
class LoadResult:
    """問題読み込みの結果。

    errors が1件でもある場合、questions は空になる
    （不完全なデータのまま出題しないようにするため）。
    """

    questions: list[Question] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """エラーがなければ True。"""
        return not self.errors


def _read_json_file(path: Path) -> tuple[list[Any], list[ValidationError]]:
    """JSON ファイル1つを読み込み、問題データの配列を返す。

    Args:
        path: 読み込むファイル。

    Returns:
        (問題データのリスト, エラーのリスト)
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        message = f"JSON の書式が正しくありません（{exc.lineno}行目 {exc.colno}文字目: {exc.msg}）"
        return [], [ValidationError(path.name, None, message)]
    except UnicodeDecodeError:
        return [], [ValidationError(path.name, None, "文字コードが UTF-8 ではありません")]

    if not isinstance(data, list):
        return [], [ValidationError(path.name, None, "ファイル全体を配列（[ ... ]）にしてください")]
    return data, []


def load_questions(questions_dir: Path) -> LoadResult:
    """フォルダ内のすべての問題ファイルを読み込んで検証する。

    Args:
        questions_dir: 問題 JSON を置いたフォルダ。

    Returns:
        LoadResult。エラーがなければ questions に id 順に並べた問題が入る。
    """
    if not questions_dir.is_dir():
        return LoadResult(errors=[ValidationError(str(questions_dir), None, "問題フォルダが見つかりません")])

    files = sorted(questions_dir.glob(QUESTION_FILE_PATTERN))
    if not files:
        message = "問題ファイル（*.json）が1つもありません"
        return LoadResult(errors=[ValidationError(str(questions_dir), None, message)])

    records: list[tuple[str, Any]] = []
    errors: list[ValidationError] = []
    for path in files:
        items, file_errors = _read_json_file(path)
        errors.extend(file_errors)
        records.extend((path.name, item) for item in items)

    errors.extend(validate_records(records))
    if errors:
        return LoadResult(errors=errors)

    questions = sorted((Question.from_dict(record) for _, record in records), key=lambda q: q.id)
    return LoadResult(questions=questions)
