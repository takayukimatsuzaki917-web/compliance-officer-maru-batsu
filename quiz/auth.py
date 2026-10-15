"""パスワード認証の判定を行うモジュール（画面に依存しない部分）。"""

from __future__ import annotations

import hmac


def is_password_valid(entered: str, expected: str) -> bool:
    """入力されたパスワードが正しいかを判定する。

    文字列の比較にかかる時間からパスワードを推測される攻撃（タイミング攻撃）を防ぐため、
    通常の == ではなく hmac.compare_digest で比較する。

    Args:
        entered: 画面で入力されたパスワード。
        expected: 設定（Secrets）に登録されたパスワード。

    Returns:
        一致すれば True。設定側が空の場合は常に False。
    """
    if not expected:
        return False
    return hmac.compare_digest(entered.encode("utf-8"), expected.encode("utf-8"))
