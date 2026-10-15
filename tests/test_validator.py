"""スキーマ検証（validator / loader）のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import ROOT_DIR, make_record
from quiz.loader import load_questions
from quiz.validator import validate_records


def _errors_for(record) -> list[str]:
    """1問だけを検証し、エラーメッセージのリストを返す。"""
    return [e.message for e in validate_records([("test.json", record)])]


def test_valid_record_has_no_errors():
    assert _errors_for(make_record()) == []


def test_valid_record_with_difficulty_has_no_errors():
    assert _errors_for(make_record(difficulty="hard")) == []


@pytest.mark.parametrize("field", ["id", "category", "subcategory", "statement", "answer", "explanation", "reference", "tip", "status"])
def test_missing_required_field(field):
    record = make_record()
    del record[field]
    errors = _errors_for(record)
    assert any(f"必須項目 '{field}' がありません" in e for e in errors)


@pytest.mark.parametrize("bad_answer", ["true", 1, 0, None])
def test_answer_must_be_boolean(bad_answer):
    # 文字列の "true" や 数値の 1 は bool ではないのでエラーにする
    errors = _errors_for(make_record(answer=bad_answer))
    assert any("'answer'" in e for e in errors)


def test_invalid_category():
    errors = _errors_for(make_record(category="保険業法"))
    assert any("'category' の値が不正" in e for e in errors)


def test_invalid_status():
    errors = _errors_for(make_record(status="done"))
    assert any("'status' の値が不正" in e for e in errors)


def test_invalid_difficulty():
    errors = _errors_for(make_record(difficulty="easy"))
    assert any("'difficulty' の値が不正" in e for e in errors)


def test_empty_string_is_error():
    errors = _errors_for(make_record(explanation="   "))
    assert any("'explanation' が空" in e for e in errors)


def test_unknown_field_is_error():
    # 項目名のタイプミス（explaination）を見逃さない
    errors = _errors_for(make_record(explaination="typo"))
    assert any("未定義の項目 'explaination'" in e for e in errors)


def test_invalid_id_characters():
    errors = _errors_for(make_record(id="q 001"))
    assert any("'id' には英数字" in e for e in errors)


def test_non_object_record():
    errors = _errors_for("not a dict")
    assert len(errors) == 1 and "オブジェクト" in errors[0]


def test_duplicate_ids_across_files():
    records = [("a.json", make_record(id="q001")), ("b.json", make_record(id="q001"))]
    errors = validate_records(records)
    assert len(errors) == 1
    assert "重複" in errors[0].message and "a.json" in errors[0].message and "b.json" in errors[0].message


def test_error_message_contains_file_and_id():
    error = validate_records([("internal.json", make_record(id="q123", status="x"))])[0]
    assert str(error).startswith("[internal.json / id=q123]")


# ---------------------------------------------------------------
# loader（ファイル読み込み）
# ---------------------------------------------------------------


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_load_questions_success_sorted_by_id(tmp_path):
    _write_json(tmp_path / "a.json", [make_record(id="q002"), make_record(id="q001", answer=False)])
    result = load_questions(tmp_path)
    assert result.ok
    assert [q.id for q in result.questions] == ["q001", "q002"]
    assert result.questions[0].answer is False


def test_load_questions_reports_json_syntax_error(tmp_path):
    (tmp_path / "broken.json").write_text("[{,}]", encoding="utf-8")
    result = load_questions(tmp_path)
    assert not result.ok
    assert "JSON の書式" in result.errors[0].message
    assert result.questions == []


def test_load_questions_requires_array(tmp_path):
    _write_json(tmp_path / "obj.json", make_record())
    result = load_questions(tmp_path)
    assert not result.ok and "配列" in result.errors[0].message


def test_load_questions_missing_dir(tmp_path):
    result = load_questions(tmp_path / "nothing")
    assert not result.ok


def test_any_error_blocks_all_questions(tmp_path):
    # 1問でも不正があれば、正しい問題も含めて出題しない
    _write_json(tmp_path / "a.json", [make_record(id="q001"), make_record(id="q002", category="不正")])
    result = load_questions(tmp_path)
    assert not result.ok and result.questions == []


def test_repository_question_data_is_valid():
    """リポジトリに含まれる実際の問題データがスキーマ検証に合格すること。"""
    result = load_questions(ROOT_DIR / "data" / "questions")
    assert result.ok, "\n".join(map(str, result.errors))
    assert result.questions
