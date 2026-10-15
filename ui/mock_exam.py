"""模試モード（本番形式）の画面。

画面の状態（session_state）:
    なし      … 開始前の説明画面
    answering … 回答中（正誤は表示しない。前の問題へ戻る・後で見直すが可能）
    result    … 採点結果

制限時間はブラウザ側ではなくサーバー側の時刻（締切時刻）で管理し、
1秒ごとに残り時間の表示だけを更新する。時間切れになると自動で採点する。
"""

from __future__ import annotations

import random
import time

import streamlit as st

from quiz.history import MockRecord, now_iso
from quiz.models import answer_symbol
from quiz.sampler import stratified_sample
from quiz.scoring import grade
from ui.components import (
    render_answer_buttons,
    render_empty_pool_warning,
    render_explanation,
    render_question,
    render_review_toggle,
    render_table,
    row,
)
from ui.context import AppContext

#: session_state に保存するキー
STATE_KEY = "mock_state"

#: 画面の状態
PHASE_ANSWERING = "answering"
PHASE_RESULT = "result"

#: 残り時間の表示を更新する間隔（秒）
TIMER_REFRESH_SECONDS = 1
#: 残り時間がこの秒数を切ったら、表示を警告色にする
TIME_WARNING_SECONDS = 5 * 60
#: 1分あたりの秒数
SECONDS_PER_MINUTE = 60
#: 問題一覧（パレット）の1行あたりのボタン数
PALETTE_COLUMNS = 5

#: 問題一覧での印
MARK_ANSWERED = "✔"
MARK_FLAGGED = "🚩"


# ---------------------------------------------------------------
# 開始前の画面
# ---------------------------------------------------------------


def _render_setup(ctx: AppContext) -> None:
    """模試の説明と開始ボタンを描画する。"""
    config = ctx.config
    num_questions = min(config.num_questions, len(ctx.questions))

    st.markdown(
        f"- 出題数: **{num_questions}問**（カテゴリの比率は問題全体に合わせます）\n"
        f"- 制限時間: **{config.time_limit_minutes}分**\n"
        f"- 合格ライン: **{config.pass_ratio:.0%}**\n"
        "- 回答中は正誤・解説を表示しません。前の問題に戻ったり「後で見直す」印を付けたりできます。"
    )
    if num_questions < config.num_questions:
        st.info(f"出題できる問題が {len(ctx.questions)}問のため、{num_questions}問で実施します。")

    prefer_unanswered = st.checkbox("まだ解いていない問題を優先して出題する", value=True)
    if st.button("模試を開始する", type="primary", width="stretch"):
        selected = stratified_sample(
            ctx.questions,
            num_questions,
            random.Random(),
            answered_ids=ctx.history.answered_ids(),
            prefer_unanswered=prefer_unanswered,
        )
        st.session_state[STATE_KEY] = {
            "phase": PHASE_ANSWERING,
            "question_ids": [q.id for q in selected],
            "answers": {},  # 問題id → 回答（True=○ / False=✕）
            "flagged": set(),  # 「後で見直す」を付けた問題id
            "index": 0,  # 表示中の問題（0始まり）
            "started_at": now_iso(),
            "deadline": time.time() + config.time_limit_minutes * SECONDS_PER_MINUTE,  # 締切（UNIX時刻）
            "confirm_submit": False,  # 未回答ありで採点しようとしたときの確認表示中か
        }
        st.rerun()


# ---------------------------------------------------------------
# 回答中の画面
# ---------------------------------------------------------------


@st.fragment(run_every=TIMER_REFRESH_SECONDS)
def _render_timer(deadline: float) -> None:
    """残り時間を表示する（この部分だけ1秒ごとに再描画される）。

    時間切れになったら画面全体を再実行し、採点処理（render 内のチェック）に進ませる。
    """
    remaining = int(deadline - time.time())
    if remaining <= 0:
        st.rerun(scope="app")
    minutes, seconds = divmod(remaining, SECONDS_PER_MINUTE)
    css_class = "exam-timer warning" if remaining < TIME_WARNING_SECONDS else "exam-timer"
    st.markdown(f'<div class="{css_class}">⏱ 残り {minutes:02d}:{seconds:02d}</div>', unsafe_allow_html=True)


def _finish(ctx: AppContext, state: dict, timed_out: bool) -> None:
    """模試を採点し、履歴に保存して結果画面に切り替える。"""
    questions = [q for q in map(ctx.question_by_id, state["question_ids"]) if q is not None]
    result = grade(questions, state["answers"], ctx.config.pass_ratio)
    record = MockRecord(
        started_at=state["started_at"],
        finished_at=now_iso(),
        timed_out=timed_out,
        flagged_ids=tuple(qid for qid in state["question_ids"] if qid in state["flagged"]),
        result=result,
    )
    ctx.history.add_mock_record(record)
    st.session_state[STATE_KEY] = {"phase": PHASE_RESULT, "record": record}


def _render_palette(state: dict) -> None:
    """問題一覧（番号ボタン）を描画する。押すとその問題へ移動する。"""
    question_ids = state["question_ids"]
    answered = len(state["answers"])
    with st.expander(f"問題一覧（回答済み {answered} / {len(question_ids)}・{MARK_FLAGGED} 見直し {len(state['flagged'])}）"):
        for start in range(0, len(question_ids), PALETTE_COLUMNS):
            with row(f"palette_{start}"):
                columns = st.columns(PALETTE_COLUMNS)
                for offset, column in enumerate(columns):
                    index = start + offset
                    if index >= len(question_ids):
                        break
                    qid = question_ids[index]
                    mark = MARK_FLAGGED if qid in state["flagged"] else (MARK_ANSWERED if qid in state["answers"] else "")
                    column.button(
                        f"{index + 1}{mark}",
                        key=f"mock_jump_{index}",
                        type="primary" if index == state["index"] else "secondary",
                        width="stretch",
                        on_click=lambda i=index: state.update(index=i, confirm_submit=False),
                    )


def _render_answering(ctx: AppContext, state: dict) -> None:
    """回答中の画面を描画する。"""
    question_ids = state["question_ids"]
    index = state["index"]
    qid = question_ids[index]
    question = ctx.question_by_id(qid)

    _render_timer(state["deadline"])

    if question is None:
        st.warning("この問題は問題データから削除されたため表示できません（採点では不正解扱いになります）。")
    else:
        render_question(question, index + 1, len(question_ids))
        render_answer_buttons(
            f"mock_{index}_{qid}",
            state["answers"].get(qid),
            lambda value: state["answers"].__setitem__(qid, value),
        )
        st.caption(f"あなたの回答: {answer_symbol(state['answers'].get(qid))}")

    # 「後で見直す」印
    flag_key = f"mock_flag_{index}_{qid}"

    def on_flag_change() -> None:
        if st.session_state[flag_key]:
            state["flagged"].add(qid)
        else:
            state["flagged"].discard(qid)

    st.checkbox(f"{MARK_FLAGGED} 後で見直す", value=qid in state["flagged"], key=flag_key, on_change=on_flag_change)

    # 前へ・次へ
    with row("mock_nav"):
        col_prev, col_next = st.columns(2)
        col_prev.button("◀ 前へ", width="stretch", disabled=index == 0,
                        on_click=lambda: state.update(index=index - 1, confirm_submit=False))
        col_next.button("次へ ▶", width="stretch", disabled=index + 1 >= len(question_ids),
                        on_click=lambda: state.update(index=index + 1, confirm_submit=False))

    _render_palette(state)
    _render_submit(ctx, state)


def _render_submit(ctx: AppContext, state: dict) -> None:
    """採点ボタンを描画する。未回答があれば確認を挟む。"""
    st.divider()
    unanswered = len(state["question_ids"]) - len(state["answers"])
    if not state["confirm_submit"]:
        if st.button("採点する", type="primary", width="stretch"):
            if unanswered:
                state["confirm_submit"] = True
            else:
                _finish(ctx, state, timed_out=False)
            st.rerun()
        return

    st.warning(f"未回答の問題が {unanswered}問あります。未回答は不正解として採点されます。")
    with row("mock_confirm"):
        col_back, col_submit = st.columns(2)
        if col_back.button("回答に戻る", width="stretch"):
            state["confirm_submit"] = False
            st.rerun()
        if col_submit.button("このまま採点する", type="primary", width="stretch"):
            _finish(ctx, state, timed_out=False)
            st.rerun()


# ---------------------------------------------------------------
# 結果画面
# ---------------------------------------------------------------


def _render_result(ctx: AppContext, record: MockRecord) -> None:
    """採点結果（得点・合否・カテゴリ別正答率・全問の一覧）を描画する。"""
    result = record.result
    st.subheader("模試の結果")
    if record.timed_out:
        st.warning("⏱ 時間切れのため、自動で採点しました。")

    st.metric("得点", f"{result.score} / {result.total}問（{result.ratio:.0%}）")
    pass_line = f"合格ライン {result.pass_ratio:.0%}（{result.required_score}問以上）"
    if result.passed:
        st.success(f"**✔ 合格**　{pass_line}")
    else:
        st.error(f"**✘ 不合格**　{pass_line}　あと{result.required_score - result.score}問")

    # --- カテゴリ別正答率 ---
    st.markdown("**カテゴリ別の正答率**")
    render_table(
        ["カテゴリ", "正答 / 出題", "正答率"],
        [[s.category, f"{s.correct} / {s.total}", f"{s.ratio:.0%}"] for s in result.category_scores()],
    )

    # --- 全問の一覧 ---
    st.markdown("**全問の振り返り**")
    only_wrong = st.toggle("不正解・見直し印の問題だけ表示する")
    flagged = set(record.flagged_ids)
    for number, item in enumerate(result.items, start=1):
        if only_wrong and item.is_correct and item.question_id not in flagged:
            continue
        verdict = "✔ 正解" if item.is_correct else "✘ 不正解"
        flag_mark = f" {MARK_FLAGGED}" if item.question_id in flagged else ""
        label = f"第{number}問　{verdict}　（あなた {answer_symbol(item.user_answer)} / 正解 {answer_symbol(item.correct_answer)}）{flag_mark}"
        with st.expander(label):
            question = ctx.question_by_id(item.question_id)
            if question is None:
                st.caption("この問題は問題データから削除されています。")
                continue
            render_question(question, number, result.total)
            if item.is_correct:
                st.success(f"**✔ 正解**　あなたの回答「{answer_symbol(item.user_answer)}」")
            else:
                st.error(f"**✘ 不正解**　あなたの回答「{answer_symbol(item.user_answer)}」／正解は「{answer_symbol(item.correct_answer)}」")
            render_explanation(question)
            render_review_toggle(ctx, question.id, key=f"mock_result_review_{number}_{question.id}")

    st.divider()
    if st.button("もう一度模試を受ける", type="primary", width="stretch"):
        st.session_state[STATE_KEY] = None
        st.rerun()


# ---------------------------------------------------------------
# 入口
# ---------------------------------------------------------------


def render(ctx: AppContext) -> None:
    """模試画面を描画する。"""
    st.title("模試（本番形式）")
    state = st.session_state.get(STATE_KEY)

    if state is None:
        if not ctx.questions:
            render_empty_pool_warning()
            return
        _render_setup(ctx)
        return

    if state["phase"] == PHASE_ANSWERING:
        # 時間切れ（他の画面に移っていた間に過ぎた場合も含む）なら自動で採点する
        if time.time() >= state["deadline"]:
            _finish(ctx, state, timed_out=True)
            st.rerun()
        _render_answering(ctx, state)
    else:
        _render_result(ctx, state["record"])
