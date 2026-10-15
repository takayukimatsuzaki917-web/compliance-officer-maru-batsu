"""法令等遵守責任者等資格試験 ○×学習アプリの入口。

起動方法:
    streamlit run app.py

処理の流れ:
    1. パスワードが設定されていれば、ログイン画面を表示する
    2. 設定・問題データ・学習履歴を読み込む（問題データはスキーマ検証も行う）
       → エラーがあれば内容を表示して止まる
    3. 画面上部のメニュー（ホーム／模試／1問1答／履歴／設定）を作る
    4. 選ばれた画面を描画する
"""

from __future__ import annotations

import streamlit as st

from ui import drill, history_view, home, mock_exam, settings
from ui.auth import require_login
from ui.components import inject_global_css
from ui.context import build_context

st.set_page_config(page_title="法令等遵守責任者 ○×トレーニング", page_icon="⭕", layout="centered")
inject_global_css()

require_login()
ctx = build_context()

# 直前の操作で履歴の保存に失敗していたら知らせる（手元の履歴は残っており、次の保存時に再度書き込む）
save_error = ctx.history.pop_last_error()
if save_error:
    st.warning(f"学習履歴を保存できませんでした。次の操作のときに再度保存を試みます。（{save_error}）")

# ページ名 → ページ。ホーム画面のボタンから他の画面へ移動するためにも使う。
# st.Page には引数なしの関数を渡す必要があるため、lambda で ctx を渡している。
pages: dict[str, st.Page] = {
    "home": st.Page(lambda: home.render(ctx, pages), title="ホーム", icon="🏠", url_path="home", default=True),
    "mock": st.Page(lambda: mock_exam.render(ctx), title="模試", icon="📝", url_path="mock"),
    "drill": st.Page(lambda: drill.render(ctx), title="1問1答", icon="⭕", url_path="drill"),
    "history": st.Page(lambda: history_view.render(ctx), title="履歴", icon="📈", url_path="history"),
    "settings": st.Page(lambda: settings.render(ctx), title="設定", icon="⚙️", url_path="settings"),
}

st.navigation(list(pages.values()), position="top").run()
