"""設定画面: draft 問題の出題可否の切り替えと、現在の設定値・問題構成の確認。"""

from __future__ import annotations

from collections import Counter

import streamlit as st

from quiz.models import CATEGORIES, STATUS_DRAFT, STATUS_REVIEWED
from ui.components import render_table
from ui.context import AppContext

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
