"""1問1答モード: ○✕を押すとすぐに正誤と解説を表示する学習用の画面。

画面の状態（session_state）:
    setup     … 出題範囲・出題順を選ぶ
    answering … 問題を1問ずつ解く
    finished  … 最後まで解き終わった
"""

from __future__ import annotations

import random

import streamlit as st

from quiz.history import MODE_DRILL
from quiz.models import CATEGORIES
from quiz.sampler import DRILL_ORDER_LABELS, DRILL_SCOPE_LABELS, DrillOrder, DrillScope, select_drill_questions
from ui.components import (
    render_answer_buttons,
    render_empty_pool_warning,
    render_explanation,
    render_feedback,
    render_question,
    render_review_toggle,
    row,
)
from ui.context import AppContext

#: session_state に保存するキー
STATE_KEY = "drill_state"

#: 画面の状態
PHASE_SETUP = "setup"
PHASE_ANSWERING = "answering"
PHASE_FINISHED = "finished"


def _select(ctx: AppContext, scope: DrillScope, order: DrillOrder, category: str | None) -> list[str]:
    """出題範囲・出題順に合う問題idのリストを返す。"""
    questions = select_drill_questions(
        ctx.questions,
        scope,
        order,
        random.Random(),
        category=category,
        answered_ids=ctx.history.answered_ids(),
        wrong_ids=ctx.history.wrong_ids(),
        review_ids=ctx.history.review_ids(),
    )
    return [q.id for q in questions]


def _start(question_ids: list[str], conditions: dict) -> None:
    """1問1答を開始する（状態を answering にする）。"""
    st.session_state[STATE_KEY] = {
        "phase": PHASE_ANSWERING,
        "question_ids": question_ids,
        "index": 0,  # 今何問目か（0始まり）
        "user_answer": None,  # 今の問題への回答（None = まだ回答していない）
        "correct_count": 0,
        "answered_count": 0,
        "conditions": conditions,  # 「同じ条件でもう一度」用に保存する
    }


def _render_setup(ctx: AppContext) -> None:
    """出題範囲・出題順の選択画面を描画する。"""
    st.subheader("出題条件を選ぶ")
    scope = st.radio("出題範囲", list(DrillScope), format_func=lambda s: DRILL_SCOPE_LABELS[s])
    category = None
    if scope == DrillScope.CATEGORY:
        category = st.selectbox("カテゴリ", CATEGORIES)
    order = st.radio("出題順", list(DrillOrder), format_func=lambda o: DRILL_ORDER_LABELS[o], horizontal=True)

    question_ids = _select(ctx, scope, order, category)
    st.markdown(f"対象: **{len(question_ids)}問**")
    if st.button("はじめる", type="primary", width="stretch", disabled=not question_ids):
        _start(question_ids, {"scope": scope, "order": order, "category": category})
        st.rerun()


def _render_answering(ctx: AppContext, state: dict) -> None:
    """1問分の出題・正誤表示を描画する。"""
    question_ids = state["question_ids"]
    index = state["index"]
    question = ctx.question_by_id(question_ids[index])
    if question is None:
        # 学習中に問題データが変更・削除された場合
        st.warning("この問題は問題データから削除されたため表示できません。")
        _render_next_button(state, index, len(question_ids))
        return

    st.progress((index + 1) / len(question_ids), text=f"{index + 1} / {len(question_ids)}問　正解 {state['correct_count']}問")
    render_question(question, index + 1, len(question_ids))

    def on_answer(value: bool) -> None:
        # 回答を記録し、正誤表示に切り替える
        correct = value == question.answer
        ctx.history.record_attempt(question.id, value, correct, MODE_DRILL)
        state["user_answer"] = value
        state["answered_count"] += 1
        state["correct_count"] += int(correct)

    if state["user_answer"] is None:
        render_answer_buttons(f"drill_{index}_{question.id}", None, on_answer)
    else:
        render_feedback(question, state["user_answer"])
        render_explanation(question)
        render_review_toggle(ctx, question.id, key=f"drill_review_{index}_{question.id}")
        _render_next_button(state, index, len(question_ids))

    st.divider()
    if st.button("学習を終了する", width="stretch"):
        state["phase"] = PHASE_FINISHED
        st.rerun()


def _render_next_button(state: dict, index: int, total: int) -> None:
    """「次へ」ボタン（最後の問題では「結果を見る」）を描画する。"""
    is_last = index + 1 >= total
    if st.button("結果を見る" if is_last else "次へ ▶", type="primary", width="stretch"):
        if is_last:
            state["phase"] = PHASE_FINISHED
        else:
            state["index"] += 1
            state["user_answer"] = None
        st.rerun()


def _render_finished(ctx: AppContext, state: dict) -> None:
    """解き終わったときのまとめ画面を描画する。"""
    answered = state["answered_count"]
    correct = state["correct_count"]
    st.subheader("おつかれさまでした")
    if answered:
        st.markdown(f"**{answered}問中 {correct}問 正解**（正答率 {correct / answered:.0%}）")
    else:
        st.markdown("回答した問題はありません。")

    with row("drill_finish"):
        col_again, col_change = st.columns(2)
        if col_again.button("同じ条件でもう一度", type="primary", width="stretch"):
            conditions = state["conditions"]
            question_ids = _select(ctx, conditions["scope"], conditions["order"], conditions["category"])
            if question_ids:
                _start(question_ids, conditions)
            else:
                # 「誤答のみ」などで、対象の問題が無くなった場合
                st.session_state[STATE_KEY] = None
                st.toast("条件に合う問題がなくなりました。条件を選び直してください。")
            st.rerun()
        if col_change.button("条件を変える", width="stretch"):
            st.session_state[STATE_KEY] = None
            st.rerun()


def render(ctx: AppContext) -> None:
    """1問1答画面を描画する。"""
    st.title("1問1答")
    if not ctx.questions:
        render_empty_pool_warning()
        return

    state = st.session_state.get(STATE_KEY)
    if state is None:
        _render_setup(ctx)
    elif state["phase"] == PHASE_ANSWERING:
        _render_answering(ctx, state)
    else:
        _render_finished(ctx, state)
