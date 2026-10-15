"""pytest の共通設定とテスト用のデータ作成ヘルパー。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# リポジトリのルートを import の検索パスに追加し、quiz パッケージを読み込めるようにする
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from quiz.models import Question  # noqa: E402  (パス追加後に import する必要がある)


def make_record(**overrides: Any) -> dict[str, Any]:
    """スキーマを満たす1問分の辞書を作る。引数で一部の項目を上書きできる。"""
    record: dict[str, Any] = {
        "id": "q001",
        "category": "保険募集規制",
        "subcategory": "テスト",
        "statement": "テスト用の問題文",
        "answer": True,
        "explanation": "テスト用の解説",
        "reference": "テスト用の根拠",
        "tip": "テスト用のtips",
        "status": "draft",
    }
    record.update(overrides)
    return record


def make_question(qid: str, category: str = "保険募集規制", answer: bool = True, status: str = "draft") -> Question:
    """テスト用の Question を作る。"""
    return Question.from_dict(make_record(id=qid, category=category, answer=answer, status=status))


@pytest.fixture
def question_pool() -> list[Question]:
    """本番と同じ比率（60:90:50）の問題プール200問。"""
    counts = {"内部管理・内部統制": 60, "保険募集規制": 90, "生命保険協会ガイドライン": 50}
    pool = []
    number = 1
    for category, count in counts.items():
        for _ in range(count):
            pool.append(make_question(f"q{number:03d}", category))
            number += 1
    return pool
