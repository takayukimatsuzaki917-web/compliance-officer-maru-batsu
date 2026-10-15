"""問題データ（JSON）のスキーマ検証を行うモジュール。

起動時にすべての問題を検証し、問題があれば「どのファイルの・どの問題の・何が悪いか」
を分かりやすいメッセージで返す。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from quiz.models import CATEGORIES, DIFFICULTY_LABELS, STATUSES

#: 必須項目と、その値の型
REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "category": str,
    "subcategory": str,
    "statement": str,
    "answer": bool,
    "explanation": str,
    "reference": str,
    "tip": str,
    "status": str,
}

#: 任意項目と、その値の型
OPTIONAL_FIELDS: dict[str, type] = {
    "difficulty": str,
}

#: id に使える文字（英数字・ハイフン・アンダースコアのみ）
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

#: 型名を日本語で表示するための対応表
TYPE_NAMES_JA: dict[type, str] = {
    str: "文字列",
    bool: "true / false",
}


@dataclass(frozen=True)
class ValidationError:
    """スキーマ検証エラー1件分の情報。"""

    source: str  # エラーが見つかったファイル名
    question_id: str | None  # 問題id（読み取れなかった場合は None）
    message: str  # エラー内容

    def __str__(self) -> str:
        """画面やコンソールに表示する1行の文字列を返す。"""
        where = self.source
        if self.question_id:
            where += f" / id={self.question_id}"
        return f"[{where}] {self.message}"


def _is_type(value: Any, expected: type) -> bool:
    """値が期待する型かどうかを判定する。

    Python では bool は int の一種なので isinstance(True, int) が True になってしまう。
    そのため bool は厳密に判定し、それ以外の型では bool を除外する。
    """
    if expected is bool:
        return isinstance(value, bool)
    return isinstance(value, expected) and not isinstance(value, bool)


def validate_record(record: Any, source: str, index: int) -> list[ValidationError]:
    """1問分のデータを検証する。

    Args:
        record: JSON から読み込んだ1要素（本来は辞書のはず）。
        source: ファイル名（エラーメッセージ用）。
        index: ファイル内での位置（0始まり）。id が読めないときの目印に使う。

    Returns:
        見つかったエラーのリスト（問題がなければ空リスト）。
    """
    position = f"{index + 1}番目の要素"

    if not isinstance(record, dict):
        return [ValidationError(source, None, f"{position}がオブジェクト（{{...}}）ではありません")]

    raw_id = record.get("id")
    qid = raw_id if isinstance(raw_id, str) and raw_id else None
    errors: list[ValidationError] = []

    def add(message: str) -> None:
        # id が読めない場合は位置情報をメッセージに含めて、場所を特定しやすくする
        prefix = "" if qid else f"{position}: "
        errors.append(ValidationError(source, qid, prefix + message))

    # --- 必須項目の欠落・型・空文字のチェック ---
    for field, expected in REQUIRED_FIELDS.items():
        if field not in record:
            add(f"必須項目 '{field}' がありません")
            continue
        value = record[field]
        if not _is_type(value, expected):
            add(f"'{field}' は{TYPE_NAMES_JA[expected]}で指定してください（現在の値: {value!r}）")
        elif expected is str and not value.strip():
            add(f"'{field}' が空です")

    # --- 任意項目の型チェック ---
    for field, expected in OPTIONAL_FIELDS.items():
        if field in record and not _is_type(record[field], expected):
            add(f"'{field}' は{TYPE_NAMES_JA[expected]}で指定してください（現在の値: {record[field]!r}）")

    # --- 想定外の項目（項目名のタイプミス対策） ---
    known_fields = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    for field in record:
        if field not in known_fields:
            add(f"未定義の項目 '{field}' があります（項目名の誤りではありませんか？）")

    # --- 値の内容チェック ---
    if qid and not ID_PATTERN.match(qid):
        add("'id' には英数字・ハイフン・アンダースコアのみ使えます")

    category = record.get("category")
    if isinstance(category, str) and category and category not in CATEGORIES:
        add(f"'category' の値が不正です: {category!r}（使える値: {' / '.join(CATEGORIES)}）")

    status = record.get("status")
    if isinstance(status, str) and status and status not in STATUSES:
        add(f"'status' の値が不正です: {status!r}（使える値: {' / '.join(STATUSES)}）")

    difficulty = record.get("difficulty")
    if isinstance(difficulty, str) and difficulty not in DIFFICULTY_LABELS:
        add(f"'difficulty' の値が不正です: {difficulty!r}（使える値: {' / '.join(DIFFICULTY_LABELS)}）")

    return errors


def find_duplicate_ids(records: Iterable[tuple[str, Any]]) -> list[ValidationError]:
    """全ファイルを通して id が重複していないか調べる。

    Args:
        records: (ファイル名, 1問分のデータ) の組の並び。

    Returns:
        重複している id ごとに1件のエラー。
    """
    sources_by_id: dict[str, list[str]] = {}
    for source, record in records:
        if isinstance(record, dict) and isinstance(record.get("id"), str) and record["id"]:
            sources_by_id.setdefault(record["id"], []).append(source)

    errors = []
    for qid, sources in sources_by_id.items():
        if len(sources) > 1:
            places = "、".join(sources)
            errors.append(ValidationError(sources[0], qid, f"id が重複しています（{len(sources)}件: {places}）"))
    return errors


def validate_records(records: list[tuple[str, Any]]) -> list[ValidationError]:
    """全問題データをまとめて検証する。

    Args:
        records: (ファイル名, 1問分のデータ) の組のリスト。

    Returns:
        すべてのエラーのリスト（問題がなければ空リスト）。
    """
    errors: list[ValidationError] = []
    # ファイルごとに「何番目の要素か」を数える
    position_in_file: dict[str, int] = {}
    for source, record in records:
        index = position_in_file.get(source, 0)
        position_in_file[source] = index + 1
        errors.extend(validate_record(record, source, index))
    errors.extend(find_duplicate_ids(records))
    return errors
