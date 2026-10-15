"""Streamlit の Secrets（秘密情報の設定）を安全に読み出すモジュール。

Secrets は、ローカルでは .streamlit/secrets.toml（Git管理外）、
Streamlit Community Cloud ではアプリ設定画面の「Secrets」に記述する。
設定が無い場合でもアプリが動くよう、読み出しに失敗したら空として扱う。

使う設定（secrets.toml の例は .streamlit/secrets.toml.example を参照）:
    [app]
    password = "..."        # アプリのパスワード（未設定ならパスワードなし）

    [github]
    token = "..."           # Gist の読み書き権限を持つトークン
    gist_id = "..."         # 履歴を保存する Gist の id
    filename = "history.json"   # 省略可
"""

from __future__ import annotations

from typing import Any

import streamlit as st

#: Secrets のセクション名
APP_SECTION = "app"
GITHUB_SECTION = "github"


def read_section(name: str) -> dict[str, Any]:
    """Secrets の指定セクションを辞書で返す（設定ファイルが無い・セクションが無い場合は空の辞書）。"""
    try:
        section = st.secrets.get(name)
    except Exception:  # noqa: BLE001  secrets.toml が無い場合など、Streamlit が送出する例外は複数ある
        return {}
    return dict(section) if section else {}


def app_password() -> str:
    """アプリのパスワード（未設定なら空文字）。"""
    return str(read_section(APP_SECTION).get("password", ""))
