"""複数の画面で使う部品（問題カード・○✕ボタン・解説表示など）をまとめたモジュール。"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Callable

import streamlit as st

from quiz.models import BATSU, DIFFICULTY_LABELS, MARU, Question, answer_symbol
from ui.context import AppContext

#: 横並びを保つ行コンテナの key の接頭辞（CSS でスマホでも縦に崩れないようにする）
ROW_KEY_PREFIX = "row_"

#: 日時の表示形式
DATETIME_FORMAT = "%Y/%m/%d %H:%M"

# スマホで押しやすい縦長レイアウトにするための CSS
GLOBAL_CSS = """
<style>
/* 画面の左右の余白を狭くして、スマホでも横幅を広く使う */
.block-container { padding-top: 3.5rem; padding-left: 1rem; padding-right: 1rem; max-width: 720px; }

/* スマホで見出しが大きくなりすぎないようにする */
h1 { font-size: 1.7rem !important; }
h3 { font-size: 1.2rem !important; }
div[data-testid="stMetricValue"] { font-size: 1.5rem; }

/* ボタンを大きく、押しやすくする */
div.stButton > button { min-height: 3rem; font-size: 1.05rem; }

/* key が row_ で始まるコンテナ内の列は、スマホでも縦に積まず横に並べる */
div[class*="st-key-row_"] div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.5rem; }
div[class*="st-key-row_"] div[data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }

/* ○✕ボタンは特に大きくする */
div[class*="st-key-row_answer"] div.stButton > button { min-height: 5rem; }
div[class*="st-key-row_answer"] div.stButton > button p { font-size: 2.4rem; font-weight: 700; }

/* 問題一覧（パレット）のボタンは小さめ */
div[class*="st-key-row_palette"] div.stButton > button { min-height: 2.6rem; font-size: 0.9rem; padding: 0 0.2rem; }

/* 問題文 */
.question-statement { font-size: 1.15rem; line-height: 1.8; padding: 0.8rem 1rem;
  border: 1px solid rgba(128,128,128,0.35); border-radius: 0.6rem; margin: 0.4rem 0 1rem; }

/* 模試の残り時間 */
.exam-timer { font-size: 1.3rem; font-weight: 700; text-align: center; padding: 0.4rem;
  border-radius: 0.5rem; background: rgba(28,131,225,0.1); }
.exam-timer.warning { background: rgba(255,43,43,0.12); color: #c00; }
</style>
"""


def inject_global_css() -> None:
    """アプリ全体の CSS を読み込む（各ページの描画前に1回呼ぶ）。"""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def format_datetime(iso_text: str) -> str:
    """ISO 8601 形式の日時文字列を「2026/10/15 22:00」の形に整える。"""
    try:
        return datetime.fromisoformat(iso_text).strftime(DATETIME_FORMAT)
    except ValueError:
        return iso_text


def row(key: str):
    """スマホでも横並びを保つ行コンテナを作る。

    Args:
        key: コンテナの識別名（同じ画面内で一意にすること）。

    Returns:
        with 文で使うコンテナ。
    """
    return st.container(key=ROW_KEY_PREFIX + key)


def render_table(headers: list[str], rows: list[list[object]]) -> None:
    """Markdown の表を表示する。

    st.dataframe はスマホ幅だと列が見切れて横スクロールになるため、
    列数の少ない表はこちらを使い、画面幅に合わせて折り返して表示する。

    Args:
        headers: 見出し行。
        rows: データ行（各要素は文字列に変換して表示する）。
    """

    def to_cell(value: object) -> str:
        # 「|」は表の区切りと解釈されるのでエスケープする
        return str(value).replace("|", "\\|")

    lines = [
        "| " + " | ".join(map(to_cell, headers)) + " |",
        "|" + "---|" * len(headers),
        *("| " + " | ".join(map(to_cell, r)) + " |" for r in rows),
    ]
    st.markdown("\n".join(lines))


def _badge_text(text: str) -> str:
    """バッジ記法を壊す角かっこを全角に置き換える。"""
    return text.replace("[", "［").replace("]", "］")


def render_question(question: Question, number: int, total: int) -> None:
    """問題番号・バッジ・問題文を表示する。

    Args:
        question: 表示する問題。
        number: 何問目か（1始まり）。
        total: 全体の問題数。
    """
    badges = [
        f":blue-badge[{_badge_text(question.category)}]",
        f":gray-badge[{_badge_text(question.subcategory)}]",
    ]
    if question.difficulty:
        badges.append(f":violet-badge[{DIFFICULTY_LABELS[question.difficulty]}]")
    if question.is_draft:
        badges.append(":orange-badge[⚠ 要確認]")

    st.markdown(f"**第{number}問** / {total}問　" + " ".join(badges))
    st.markdown(f'<div class="question-statement">{html.escape(question.statement)}</div>', unsafe_allow_html=True)


def render_answer_buttons(key: str, selected: bool | None, on_select: Callable[[bool], None]) -> None:
    """大きな○✕ボタンを横並びで表示する。

    Args:
        key: ボタンの識別名（問題ごとに一意にすること）。
        selected: 選択済みの回答（選択中のボタンを強調表示する）。None なら未選択。
        on_select: ボタンが押されたときに呼ぶ関数（引数は True=○ / False=✕）。
    """
    with row(f"answer_{key}"):
        col_maru, col_batsu = st.columns(2)
        for column, value, label in ((col_maru, True, MARU), (col_batsu, False, BATSU)):
            column.button(
                label,
                key=f"{key}_{value}",
                type="primary" if selected is value else "secondary",
                width="stretch",
                on_click=on_select,
                args=(value,),
            )


def render_feedback(question: Question, user_answer: bool) -> None:
    """回答の正誤を表示する（色だけに頼らず「正解／不正解」の文字も出す）。"""
    correct_text = f"正解は「{answer_symbol(question.answer)}」"
    if user_answer == question.answer:
        st.success(f"**✔ 正解**　{correct_text}")
    else:
        st.error(f"**✘ 不正解**　あなたの回答は「{answer_symbol(user_answer)}」／{correct_text}")


def render_explanation(question: Question) -> None:
    """解説・根拠・一言tipsを表示する。"""
    st.markdown(f"**解説**  \n{question.explanation}")
    st.markdown(f"**根拠**  \n{question.reference}")
    st.info(f"💡 {question.tip}")
    if question.is_draft:
        st.caption("⚠ この問題は根拠の確認が済んでいない（draft）ため、内容に誤りがある可能性があります。")


def render_review_toggle(ctx: AppContext, question_id: str, key: str) -> None:
    """「要復習」フラグのチェックボックスを表示する。変更すると即座に履歴へ保存する。

    Args:
        ctx: アプリの共通データ。
        question_id: 対象の問題id。
        key: チェックボックスの識別名（画面内で一意にすること）。
    """

    def on_change() -> None:
        ctx.history.set_review_flag(question_id, st.session_state[key])

    st.checkbox(
        "🔖 要復習にする",
        value=ctx.history.is_review_flagged(question_id),
        key=key,
        on_change=on_change,
    )


def render_empty_pool_warning() -> None:
    """出題できる問題が1問もないときの案内を表示する。"""
    st.warning("出題できる問題がありません。設定画面で「draft（要確認）の問題を出題に含める」をオンにするか、問題を追加してください。")
