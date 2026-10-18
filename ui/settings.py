"""設定画面: draft 問題の出題可否の切り替えと、現在の設定値・問題構成の確認。"""

from __future__ import annotations

from collections import Counter

import streamlit as st

from quiz.history import HistoryLoadError
from quiz.history_backends import GistHistoryBackend
from quiz.models import CATEGORIES, STATUS_DRAFT, STATUS_REVIEWED
from ui.auth import logout, password_required
from ui.components import render_table, row
from ui.context import AppContext, reload_history

#: トグルの識別名
INCLUDE_DRAFT_KEY = "settings_include_draft"


def render(ctx: AppContext) -> None:
    """設定画面を描画する。"""
    st.title("設定")

    # --- draft 問題の出題可否（履歴ファイルに保存する） ---
    st.subheader("出題対象")

    def on_change() -> None:
        ctx.history.set_include_draft(st.session_state[INCLUDE_DRAFT_KEY])

    st.toggle(
        "draft（要確認）の問題を出題に含める",
        value=ctx.history.include_draft,
        key=INCLUDE_DRAFT_KEY,
        on_change=on_change,
    )
    st.caption("draft は根拠を一次情報で確認できていない問題です。オフにすると reviewed の問題だけを出題します。")

    # --- 問題の構成 ---
    st.subheader("問題の構成")
    counts = Counter((q.category, q.status) for q in ctx.all_questions)
    render_table(
        ["カテゴリ", "reviewed", "draft", "合計"],
        [
            [
                category,
                counts[(category, STATUS_REVIEWED)],
                counts[(category, STATUS_DRAFT)],
                counts[(category, STATUS_REVIEWED)] + counts[(category, STATUS_DRAFT)],
            ]
            for category in CATEGORIES
        ],
    )
    st.markdown(f"現在の出題対象: **{len(ctx.questions)}問** / 全{len(ctx.all_questions)}問")

    # --- config.yaml の値（表示のみ） ---
    st.subheader("模試の設定（config.yaml）")
    config = ctx.config
    st.markdown(
        f"- 出題数: {config.num_questions}問\n"
        f"- 合格ライン: {config.pass_ratio:.0%}\n"
        f"- 制限時間: {config.time_limit_minutes}分"
    )
    st.caption("合格ライン・制限時間は仮の値です。公式の試験要項で確認し、config.yaml を編集してアプリを再読み込みしてください。")

    _render_storage_section(ctx)


def _render_storage_section(ctx: AppContext) -> None:
    """学習履歴の保存先の表示と、最新の履歴の読み込み・ログアウトのボタンを描画する。"""
    st.subheader("学習履歴の保存先")
    st.markdown(f"保存先: **{ctx.history.storage_description}**")
    st.caption("別のPCで解いた内容は、このボタンで読み込むか、ブラウザを開き直すと反映されます。")

    with row("settings_storage"):
        col_reload, col_logout = st.columns(2)
        if col_reload.button("🔄 最新の履歴を読み込む", width="stretch"):
            try:
                reload_history()
            except HistoryLoadError as exc:
                st.error(f"履歴を読み込めませんでした: {exc}")
            else:
                st.toast("最新の履歴を読み込みました。")
        if password_required() and col_logout.button("ログアウト", width="stretch"):
            logout()
            st.rerun()

    if isinstance(ctx.history.backend, GistHistoryBackend):
        _render_gist_diagnosis(ctx.history.backend)


def _render_gist_diagnosis(backend: GistHistoryBackend) -> None:
    """Gist への接続診断ボタンと、その結果を描画する。"""
    st.caption("保存できないエラーが出るときは、次のボタンで原因を確認できます（履歴の内容は変わりません）。")
    if not st.button("🩺 Gist への接続を診断する", width="stretch"):
        return

    with st.spinner("GitHub に問い合わせています…"):
        results = backend.diagnose()
    for result in results:
        mark = "✔ OK" if result.ok else "✘ NG"
        message = f"**{mark}　{result.name}**  \n{result.detail}"
        if result.ok:
            st.success(message)
        else:
            st.error(message)
    if all(result.ok for result in results):
        st.info("すべての確認項目に問題はありません。")
