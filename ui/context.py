"""各画面で共通して使うデータ（設定・問題・履歴）をまとめるモジュール。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from quiz.config import AppConfig, ConfigError, load_config
from quiz.history import HistoryLoadError, HistoryStore
from quiz.loader import load_questions
from quiz.models import Question

#: 設定ファイルの場所（リポジトリのルート）
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@dataclass
class AppContext:
    """画面の描画に必要なデータ一式。"""

    config: AppConfig
    all_questions: list[Question]  # 読み込んだすべての問題
    history: HistoryStore
    _by_id: dict[str, Question] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # id から問題をすぐ引けるよう、辞書を作っておく
        self._by_id = {q.id: q for q in self.all_questions}

    @property
    def questions(self) -> list[Question]:
        """出題対象の問題（設定で draft を除外している場合は reviewed のみ）。"""
        if self.history.include_draft:
            return list(self.all_questions)
        return [q for q in self.all_questions if not q.is_draft]

    def question_by_id(self, question_id: str) -> Question | None:
        """id から問題を探す（見つからなければ None）。"""
        return self._by_id.get(question_id)


def build_context() -> AppContext:
    """設定・問題・履歴を読み込んで AppContext を作る。

    どれかの読み込みに失敗した場合は、原因を画面に表示してアプリを止める（st.stop）。
    """
    try:
        config = load_config(CONFIG_PATH)
    except ConfigError as exc:
        st.error(f"config.yaml の設定に誤りがあります: {exc}")
        st.stop()

    result = load_questions(config.questions_dir)
    if not result.ok:
        st.error(f"問題データに {len(result.errors)} 件のエラーがあるため起動できません。以下を修正してください。")
        st.markdown("\n".join(f"- `{error}`" for error in result.errors))
        st.caption("修正後、ブラウザを再読み込みしてください。`python scripts/validate_questions.py` でも確認できます。")
        st.stop()

    try:
        history = HistoryStore.load(config.history_file)
    except HistoryLoadError as exc:
        st.error(f"学習履歴を読み込めません: {exc}")
        st.caption(f"{config.history_file.name} を別名で退避するか削除すると、空の履歴で起動します。")
        st.stop()

    return AppContext(config=config, all_questions=result.questions, history=history)
