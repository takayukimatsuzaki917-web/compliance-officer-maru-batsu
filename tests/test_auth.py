"""パスワード判定のテスト。"""

from __future__ import annotations

from quiz.auth import is_password_valid


def test_correct_password():
    assert is_password_valid("secret-pass", "secret-pass")


def test_wrong_password():
    assert not is_password_valid("wrong", "secret-pass")


def test_empty_expected_password_never_matches():
    # 設定が空のときに空入力で通ってしまわないこと
    assert not is_password_valid("", "")


def test_japanese_password():
    assert is_password_valid("合格する", "合格する")
