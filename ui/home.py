"""ホーム画面: 全体の進捗と直近の模試の得点を表示する。"""

from __future__ import annotations

import streamlit as st

from ui.components import format_datetime, row
from ui.context import AppContext

#: 免責文（ホーム画面の下部に表示する）
DISCLAIMER = (
    "本アプリは個人の学習用に作成した非公式アプリであり、生命保険協会とは一切関係ありません。"
    "法令・監督指針・ガイドラインは改正されるため、必ず最新の公式情報を確認してください。"
)


def render(ctx: AppContext, pages: dict) -> None:
    """ホーム画面を描画する。

    Args:
        ctx: アプリの共通データ。
        pages: ページ名 → st.Page の辞書（画面移動ボタンに使う）。
    """
    st.title("法令等遵守責任者 ○×トレーニング")
    st.caption("生命保険協会「法令等遵守責任者等資格試験」対策（非公式・個人学習用）")

    all_ids = {q.id for q in ctx.all_questions}
    total = len(all_ids)
    answered = len(ctx.history.answered_ids() & all_ids)

    # --- 全体の進捗 ---
    st.subheader("学習の進捗")
    st.markdown(f"解いた問題数: **{answered} / {total}問**")
    st.progress(answered / total if total else 0.0)

    with row("home_metrics"):
        col_mock, col_wrong, col_review = st.columns(3)
    latest = ctx.history.latest_mock_record()
    if latest:
        result = latest.result
        col_mock.metric("直近の模試", f"{result.score} / {result.total}")
        verdict = ":green[**✔ 合格**]" if result.passed else ":red[**✘ 不合格**]"
        col_mock.markdown(f"{verdict}  \n{format_datetime(latest.finished_at)}")
    else:
        col_mock.metric("直近の模試", "未受験")
    col_wrong.metric("誤答", f"{len(ctx.history.wrong_ids() & all_ids)}問")
    col_review.metric("要復習", f"{len(ctx.history.review_ids() & all_ids)}問")

    draft_count = sum(1 for q in ctx.all_questions if q.is_draft)
    if draft_count:
        included = "出題に含めています" if ctx.history.include_draft else "出題から除外しています"
        st.caption(f"⚠ 根拠未確認（draft）の問題が {draft_count}問あります（現在の設定: {included}）。")

    # --- 学習の開始 ---
    st.subheader("学習をはじめる")
    if st.button("📝 模試を受ける（本番形式）", type="primary", width="stretch"):
        st.switch_page(pages["mock"])
    if st.button("⭕ 1問1答で学習する", width="stretch"):
        st.switch_page(pages["drill"])

    st.divider()
    st.caption(DISCLAIMER)
