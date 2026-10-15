"""学習履歴の保存先（バックエンド）を定義するモジュール。

保存先を差し替えられるようにすることで、
  - 自分のPCで使うとき   … ローカルの history.json（FileHistoryBackend）
  - どこからでも使うとき … GitHub Gist 上の history.json（GistHistoryBackend）
のどちらでも、同じ HistoryStore（quiz/history.py）で履歴を扱えるようにしている。

どのバックエンドも、次の2つのメソッドを持つ。
  load() … 保存されている履歴の辞書を返す（まだ何も保存されていなければ None）
  save(data) … 履歴の辞書を保存する
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Protocol

#: GitHub API のURL
GITHUB_API_URL = "https://api.github.com"

#: Gist 上で履歴を保存するファイル名の既定値
DEFAULT_GIST_FILENAME = "history.json"

#: GitHub API の通信を待つ最大秒数
DEFAULT_TIMEOUT_SECONDS = 15


class HistoryBackendError(Exception):
    """履歴の読み込み・保存に失敗したときに送出する例外。"""


class HistoryBackend(Protocol):
    """履歴の保存先が備えるべきメソッド（型ヒント用）。"""

    def load(self) -> dict[str, Any] | None:
        """保存されている履歴を返す（未保存なら None）。"""

    def save(self, data: dict[str, Any]) -> None:
        """履歴を保存する。"""

    def describe(self) -> str:
        """画面に表示する保存先の説明を返す。"""


def _parse_history_json(text: str, source: str) -> dict[str, Any] | None:
    """履歴の JSON 文字列を辞書に変換する。

    空文字や空のオブジェクト（{}）は「まだ何も保存されていない」とみなして None を返す。

    Raises:
        HistoryBackendError: JSON が壊れている、またはオブジェクトでない場合。
    """
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HistoryBackendError(f"{source} を読み込めません: {exc}") from exc
    if not isinstance(data, dict):
        raise HistoryBackendError(f"{source} の形式が正しくありません（オブジェクトではありません）")
    return data or None


def _dump_history_json(data: dict[str, Any]) -> str:
    """履歴の辞書を、人が読みやすい JSON 文字列に変換する。"""
    return json.dumps(data, ensure_ascii=False, indent=2)


class FileHistoryBackend:
    """ローカルのファイル（history.json）に履歴を保存する。"""

    def __init__(self, path: Path):
        """
        Args:
            path: 保存先のファイルパス。
        """
        self.path = path

    def load(self) -> dict[str, Any] | None:
        """ファイルから履歴を読み込む。ファイルが無ければ None。"""
        if not self.path.exists():
            return None
        try:
            text = self.path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise HistoryBackendError(f"{self.path.name} の文字コードが UTF-8 ではありません") from exc
        return _parse_history_json(text, self.path.name)

    def save(self, data: dict[str, Any]) -> None:
        """履歴をファイルに保存する。

        書き込み途中でアプリが止まってもファイルが壊れないよう、
        一時ファイルに書いてから本来のファイル名に置き換える。
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(_dump_history_json(data), encoding="utf-8")
        os.replace(tmp_path, self.path)

    def describe(self) -> str:
        """保存先の説明。"""
        return f"このPCのファイル（{self.path.name}）"


class GistHistoryBackend:
    """GitHub Gist 上のファイルに履歴を保存する。

    どのPCからアプリを開いても、同じ Gist を読み書きするので履歴を共有できる。
    Gist はあらかじめ作成しておき、その id とアクセストークンを Streamlit の Secrets に設定する。
    """

    def __init__(
        self,
        token: str,
        gist_id: str,
        filename: str = DEFAULT_GIST_FILENAME,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ):
        """
        Args:
            token: Gist の読み書き権限を持つ GitHub のアクセストークン。
            gist_id: 保存先 Gist の id（Gist の URL の末尾の英数字）。
            filename: Gist 内で履歴を保存するファイル名。
            timeout: 通信の待ち時間の上限（秒）。
            opener: HTTP 通信を行う関数（テストで通信を差し替えるための引数）。
        """
        self.token = token
        self.gist_id = gist_id
        self.filename = filename
        self.timeout = timeout
        self._opener = opener

    def _request(self, method: str, url: str, body: dict[str, Any] | None = None) -> bytes:
        """GitHub API にリクエストを送り、レスポンス本文を返す。

        Raises:
            HistoryBackendError: 通信エラーや、認証失敗などのエラー応答の場合。
        """
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=payload, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self._opener(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            hint = "トークンの権限（Gists の読み書き）と Gist の id を確認してください" if exc.code in (401, 403, 404) else ""
            raise HistoryBackendError(f"GitHub Gist との通信でエラーが発生しました（HTTP {exc.code}）。{hint}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HistoryBackendError(f"GitHub Gist に接続できません: {exc}") from exc

    def load(self) -> dict[str, Any] | None:
        """Gist から履歴を読み込む。対象のファイルが無ければ None。"""
        raw = self._request("GET", f"{GITHUB_API_URL}/gists/{self.gist_id}")
        gist = json.loads(raw.decode("utf-8"))
        file_info = gist.get("files", {}).get(self.filename)
        if file_info is None:
            return None
        if file_info.get("truncated"):
            # 大きなファイルは API の応答で内容が省略されるため、raw_url から全文を取得する
            text = self._request("GET", file_info["raw_url"]).decode("utf-8")
        else:
            text = file_info.get("content", "")
        return _parse_history_json(text, f"Gist の {self.filename}")

    def save(self, data: dict[str, Any]) -> None:
        """Gist のファイルを履歴の内容で上書きする。"""
        body = {"files": {self.filename: {"content": _dump_history_json(data)}}}
        self._request("PATCH", f"{GITHUB_API_URL}/gists/{self.gist_id}", body)

    def describe(self) -> str:
        """保存先の説明（トークンは表示しない）。"""
        return f"GitHub Gist（{self.filename}）"
