"""各画面で共通して使うデータ（設定・問題・履歴）をまとめるモジュール。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from quiz.config import AppConfig, ConfigError, load_config
from quiz.history import HistoryLoadError, HistoryStore
from quiz.history_backends import (
    DEFAULT_GIST_FILENAME,
    FileHistoryBackend,
    GistHistoryBackend,
    HistoryBackend,
    HistoryBackendError,
)
from quiz.loader import load_questions
from quiz.models import Question
from ui.app_secrets import GITHUB_SECTION, read_section

#: 設定ファイルの場所（リポジトリのルート）
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"

#: 読み込んだ履歴をブラウザのセッション中に保持しておく session_state のキー
#: （画面操作のたびに保存先へ読み込みに行かないようにするため）
HISTORY_STATE_KEY = "history_store"


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


def create_history_backend(config: AppConfig) -> HistoryBackend:
    """履歴の保存先を決める。

    Secrets に GitHub のトークンと Gist の id が設定されていれば Gist に保存し
    （どのPCからでも同じ履歴を使える）、設定が無ければローカルの history.json に保存する。

    Raises:
        HistoryBackendError: gist_id の形式が不正な場合。
    """
    github = read_section(GITHUB_SECTION)
    token = str(github.get("token", "")).strip()
    gist_id = str(github.get("gist_id", "")).strip()
    if token and gist_id:
        filename = str(github.get("filename", DEFAULT_GIST_FILENAME)).strip() or DEFAULT_GIST_FILENAME
        return GistHistoryBackend(token=token, gist_id=gist_id, filename=filename)
    return FileHistoryBackend(config.history_file)


def get_history_store(config: AppConfig) -> HistoryStore:
    """履歴を返す。セッションの初回だけ保存先から読み込み、以降は手元の内容を使う。

    読み込みに失敗した場合は、原因を画面に表示してアプリを止める（st.stop）。
    """
    store = st.session_state.get(HISTORY_STATE_KEY)
    if store is not None:
        return store

    try:
        backend = create_history_backend(config)
    except HistoryBackendError as exc:
        # gist_id の形式が不正な場合など、保存先の設定そのものに誤りがある
        st.error(f"学習履歴の保存先の設定に誤りがあります: {exc}")
        st.stop()

    try:
        store = HistoryStore.load(backend)
    except HistoryLoadError as exc:
        st.error(f"学習履歴を読み込めません（保存先: {backend.describe()}）: {exc}")
        if isinstance(backend, FileHistoryBackend):
            st.caption(f"{config.history_file.name} を別名で退避するか削除すると、空の履歴で起動します。")
        else:
            st.caption("通信状況や Secrets の設定（トークン・Gist の id）を確認し、ブラウザを再読み込みしてください。")
        st.stop()

    st.session_state[HISTORY_STATE_KEY] = store
    return store


def reload_history() -> None:
    """保存先から履歴を読み込み直す（他のPCで解いた内容を反映するため）。

    Raises:
        HistoryLoadError: 保存先から読み込めない場合。
    """
    store: HistoryStore | None = st.session_state.get(HISTORY_STATE_KEY)
    if store is not None:
        store.reload()


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

    history = get_history_store(config)
    return AppContext(config=config, all_questions=result.questions, history=history)
