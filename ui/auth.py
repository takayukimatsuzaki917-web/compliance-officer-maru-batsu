"""パスワード入力画面（ログイン）を表示するモジュール。"""

from __future__ import annotations

import streamlit as st

from quiz.auth import is_password_valid
from ui.app_secrets import app_password

#: ログイン済みかどうかを session_state に保存するキー
AUTHENTICATED_KEY = "authenticated"


def password_required() -> bool:
    """パスワードが設定されていれば True（設定が無ければ誰でも使える）。"""
    return bool(app_password())


def require_login() -> None:
    """パスワードが設定されている場合、ログインするまで以降の画面を表示しない。

    ログイン状態はブラウザのセッションごとに保持される（タブを閉じると再度入力が必要）。
    """
    if not password_required() or st.session_state.get(AUTHENTICATED_KEY):
        return

    st.title("法令等遵守責任者 ○×トレーニング")
    with st.form("login_form"):
        entered = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン", type="primary", width="stretch")

    if submitted:
        if is_password_valid(entered, app_password()):
            st.session_state[AUTHENTICATED_KEY] = True
            st.rerun()
        st.error("パスワードが違います。")
    st.stop()


def logout() -> None:
    """ログイン状態を解除する。"""
    st.session_state[AUTHENTICATED_KEY] = False
