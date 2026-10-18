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
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

#: GitHub API のURL
GITHUB_API_URL = "https://api.github.com"

#: Gist 上で履歴を保存するファイル名の既定値
DEFAULT_GIST_FILENAME = "history.json"

#: GitHub API の通信を待つ最大秒数
DEFAULT_TIMEOUT_SECONDS = 15

#: 利用回数の上限で通信を控えている間のエラーに付けるステータス（Too Many Requests）
HTTP_TOO_MANY_REQUESTS = 429

#: 利用回数の上限に達したが解除時刻が分からないときに、通信を控える秒数
DEFAULT_RATE_LIMIT_WAIT_SECONDS = 60

#: 日本時間（UTC+9）。Windows でも追加パッケージなしで使えるよう、固定のオフセットで定義する
JST = timezone(timedelta(hours=9), "JST")

#: 画面に表示する日時の形式
JST_DISPLAY_FORMAT = "%m/%d %H:%M"


#: Gist の id として使える文字（英数字のみ）
GIST_ID_PATTERN = re.compile(r"^[0-9A-Za-z]+$")

#: エラー表示で gist_id の前後に見せる文字数（全体を表示しないため）
GIST_ID_VISIBLE_CHARS = 4

#: GitHub API の主なエラーコードと、確認してほしい点
HTTP_ERROR_HINTS: dict[int, str] = {
    401: "トークンが正しくないか、有効期限が切れています。新しいトークンを発行して Secrets の token を更新してください。",
    403: (
        "書き込みが拒否されました。トークンの Gists の権限が「Read and write」になっているか（Read-only ではないか）、"
        "Gist を作ったアカウントとトークンを発行したアカウントが同じか確認してください。"
        "設定画面の「Gist への接続を診断する」で原因を確認できます。"
    ),
    404: (
        "指定した Gist が見つかりません。Secrets の gist_id に、Gist の URL の末尾の英数字だけを設定しているか、"
        "Gist を削除していないか確認してください。"
    ),
}


class HistoryBackendError(Exception):
    """履歴の読み込み・保存に失敗したときに送出する例外。

    Attributes:
        status: GitHub API の HTTP ステータスコード（通信エラー以外の場合は None）。
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def describe_github_error(exc: urllib.error.HTTPError, now: float | None = None) -> str:
    """GitHub API のエラー応答から、原因の手がかりになる情報を取り出して文章にする。

    取り出す情報:
      - 応答本文の message（例: "Resource not accessible by personal access token"）
      - X-Accepted-GitHub-Permissions ヘッダー（Fine-grained token に足りない権限。例: "gists=write"）
      - X-RateLimit-Remaining ヘッダーが 0 のとき（利用回数の上限に達した）

    Args:
        exc: urllib が送出した HTTP エラー。
        now: 現在のUNIX時刻（省略時は実際の時刻。Retry-After から解除時刻を計算するのに使う）。

    Returns:
        「（GitHub からのメッセージ: …）」の形の文字列。手がかりが無ければ空文字。
    """
    parts: list[str] = []
    try:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        message = json.loads(body).get("message", "") if body else ""
    except (ValueError, AttributeError, OSError):
        message = ""
    if message:
        parts.append(f"GitHub からのメッセージ: {message}")

    headers = exc.headers or {}
    accepted = headers.get("X-Accepted-GitHub-Permissions")
    if accepted:
        parts.append(f"必要な権限: {accepted}")
    reset_at = rate_limit_reset_epoch(exc, now=now)
    if reset_at is not None:
        parts.append(f"GitHub API の利用回数の上限に達しています。{format_jst(reset_at)}（日本時間）ごろに自動で回復します")
    return f"（{' ／ '.join(parts)}）" if parts else ""


def format_jst(epoch_seconds: float) -> str:
    """UNIX時刻を「10/18 13:05」の形の日本時間の文字列にする。"""
    return datetime.fromtimestamp(epoch_seconds, JST).strftime(JST_DISPLAY_FORMAT)


def rate_limit_reset_epoch(exc: urllib.error.HTTPError, now: float | None = None) -> float | None:
    """利用回数の上限によるエラーなら、制限が解除される時刻（UNIX時刻）を返す。それ以外は None。

    GitHub は上限に達すると、次のどちらかのヘッダーで解除時刻を知らせる。
      - X-RateLimit-Remaining: 0 と X-RateLimit-Reset（解除時刻のUNIX時刻）
      - Retry-After（あと何秒待てばよいか）
    """
    headers = exc.headers or {}
    current = time.time() if now is None else now
    if headers.get("X-RateLimit-Remaining") == "0":
        reset = headers.get("X-RateLimit-Reset")
        return float(reset) if reset and reset.isdigit() else current + DEFAULT_RATE_LIMIT_WAIT_SECONDS
    retry_after = headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return current + int(retry_after)
    return None


def normalize_gist_id(value: str) -> str:
    """Secrets に設定された gist_id から、Gist の id 部分だけを取り出す。

    次のような書き方でも id を取り出せるようにしている（よくある設定ミスの吸収）。
      - Gist の URL 全体:   https://gist.github.com/ユーザー名/abc123
      - ユーザー名付き:     ユーザー名/abc123
      - 前後の空白や引用符、末尾の「/」「.git」「#…」「?…」

    Args:
        value: Secrets に設定された文字列。

    Returns:
        id 部分（英数字）。

    Raises:
        HistoryBackendError: 取り出した結果が英数字の id にならない場合。
    """
    text = value.strip().strip("\"'").strip()
    text = re.split(r"[?#]", text, maxsplit=1)[0]  # クエリ・アンカーを除く
    segments = [segment for segment in text.split("/") if segment]
    candidate = segments[-1] if segments else ""
    candidate = candidate.removesuffix(".git")
    if not GIST_ID_PATTERN.match(candidate):
        raise HistoryBackendError(
            "Secrets の gist_id の形式が正しくありません。Gist の URL の末尾の英数字（例: 0123456789abcdef…）を設定してください。"
        )
    return candidate


def mask_gist_id(gist_id: str) -> str:
    """エラー表示用に、gist_id の前後の数文字と文字数だけを見せる文字列を返す。"""
    if len(gist_id) <= GIST_ID_VISIBLE_CHARS * 2:
        return f"{gist_id}（{len(gist_id)}文字）"
    return f"{gist_id[:GIST_ID_VISIBLE_CHARS]}…{gist_id[-GIST_ID_VISIBLE_CHARS:]}（{len(gist_id)}文字）"


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
        clock: Callable[[], float] = time.time,
    ):
        """
        Args:
            token: Gist の読み書き権限を持つ GitHub のアクセストークン。
            gist_id: 保存先 Gist の id（Gist の URL の末尾の英数字）。
            filename: Gist 内で履歴を保存するファイル名。
            timeout: 通信の待ち時間の上限（秒）。
            opener: HTTP 通信を行う関数（テストで通信を差し替えるための引数）。
            clock: 現在のUNIX時刻を返す関数（テストで時刻を差し替えるための引数）。
        """
        self.token = token.strip()
        self.gist_id = normalize_gist_id(gist_id)
        self.filename = filename
        self.timeout = timeout
        self._opener = opener
        self._clock = clock
        # 利用回数の上限に達したとき、解除されるまで通信を控えるための時刻（UNIX時刻）
        self._blocked_until = 0.0

    def _request(self, method: str, url: str, body: dict[str, Any] | None = None, *, ignore_block: bool = False) -> bytes:
        """GitHub API にリクエストを送り、レスポンス本文を返す。

        利用回数の上限に達した後は、解除時刻まで通信せずにエラーを返す
        （上限中に通信を繰り返しても成功しないうえ、GitHub に負担をかけるため）。

        Args:
            method: HTTP メソッド。
            url: リクエスト先。
            body: 送信する JSON（無ければ None）。
            ignore_block: True なら上限中でも通信する（利用状況の確認用。回数を消費しない窓口に限る）。

        Raises:
            HistoryBackendError: 通信エラーや、認証失敗などのエラー応答の場合。
        """
        if not ignore_block and self._clock() < self._blocked_until:
            raise HistoryBackendError(
                f"GitHub API の利用回数の上限に達しているため、{format_jst(self._blocked_until)}（日本時間）ごろまで"
                "保存・読み込みを見合わせています。それまでに解いた分は、このブラウザで開いている間は保持され、回復後の保存時にまとめて書き込まれます。",
                status=HTTP_TOO_MANY_REQUESTS,
            )

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
            reset_at = rate_limit_reset_epoch(exc, now=self._clock())
            if reset_at is not None:
                # 利用回数の上限：権限の問題ではないので権限の案内は出さず、解除時刻まで通信を控える
                self._blocked_until = reset_at
                hint = ""
            else:
                hint = HTTP_ERROR_HINTS.get(exc.code, "")
            detail = describe_github_error(exc, now=self._clock())
            raise HistoryBackendError(
                f"GitHub Gist との通信でエラーが発生しました（HTTP {exc.code}、gist_id: {mask_gist_id(self.gist_id)}）。"
                f"{hint}{detail}",
                status=exc.code,
            ) from exc
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

    # -----------------------------------------------------------
    # 接続の診断
    # -----------------------------------------------------------

    def _get_json(self, url: str, ignore_block: bool = False) -> dict[str, Any]:
        """GET して JSON を辞書で返す。"""
        return json.loads(self._request("GET", url, ignore_block=ignore_block).decode("utf-8"))

    def _rate_limit_result(self) -> "DiagnosticResult":
        """GitHub API の利用状況を確認する（/rate_limit は利用回数を消費しない）。"""
        name = "GitHub API の利用回数"
        try:
            core = self._get_json(f"{GITHUB_API_URL}/rate_limit", ignore_block=True)["resources"]["core"]
        except (HistoryBackendError, KeyError, ValueError) as exc:
            return DiagnosticResult(name, False, f"利用状況を取得できませんでした: {exc}")

        limit, used, remaining, reset = core["limit"], core["used"], core["remaining"], core["reset"]
        summary = (
            f"1時間あたりの上限 {limit}回 ／ 使用済み {used}回 ／ 残り {remaining}回 ／ "
            f"回数のリセット: {format_jst(reset)}（日本時間）"
        )
        if remaining > 0:
            self._blocked_until = 0.0  # 回復していれば、通信の見合わせを解除する
            return DiagnosticResult(name, True, summary)

        self._blocked_until = float(reset)
        advice = (
            "上限に達しています。リセット時刻を過ぎると自動的に使えるようになります。"
            "このアプリの通信は1回の回答につき2回程度です。使用済み回数がとても多い場合は、"
            "同じGitHubアカウントで連携している他のツール（GitHubと連携した拡張機能やアプリなど）が回数を使っている可能性があります"
            "（上限はアカウント単位で共有されます）。"
        )
        return DiagnosticResult(name, False, f"{summary}  \n{advice}")

    def _current_content(self, gist: dict[str, Any]) -> str:
        """Gist の履歴ファイルの現在の内容（ファイルが無ければ空の履歴 "{}"）を返す。"""
        file_info = gist.get("files", {}).get(self.filename)
        if file_info is None:
            return "{}"
        if file_info.get("truncated"):
            return self._request("GET", file_info["raw_url"]).decode("utf-8")
        return file_info.get("content", "{}")

    def diagnose(self) -> list["DiagnosticResult"]:
        """Gist への接続を順に確認し、どこで失敗しているかを調べる。

        確認する項目:
          0. GitHub API の利用状況（上限・使用済み回数・解除時刻）
          1. トークンが有効か（トークンの持ち主のアカウント名を取得できるか）
          2. Gist を読めるか（Gist の持ち主のアカウント名と、履歴ファイルの有無）
          3. トークンの持ち主と Gist の持ち主が同じアカウントか
          4. Gist に書き込めるか（現在の内容をそのまま書き戻すので、履歴は変わらない）

        利用回数の上限に達している場合は、以降の確認をしても失敗するだけなので、0 の結果だけを返す。

        Returns:
            確認項目ごとの結果のリスト。
        """
        results: list[DiagnosticResult] = []

        # 0. 利用状況（この窓口は利用回数を消費しない）
        usage = self._rate_limit_result()
        results.append(usage)
        if not usage.ok:
            return results

        # 1. トークンの持ち主
        token_owner = ""
        try:
            token_owner = self._get_json(f"{GITHUB_API_URL}/user").get("login", "")
            results.append(DiagnosticResult("トークンが有効か", True, f"トークンを発行したアカウント: {token_owner}"))
        except HistoryBackendError as exc:
            results.append(DiagnosticResult("トークンが有効か", False, str(exc)))

        # 2. Gist の持ち主と履歴ファイル
        gist: dict[str, Any] | None = None
        try:
            gist = self._get_json(f"{GITHUB_API_URL}/gists/{self.gist_id}")
        except HistoryBackendError as exc:
            results.append(DiagnosticResult("Gist を読めるか", False, str(exc)))
        if gist is not None:
            gist_owner = (gist.get("owner") or {}).get("login", "")
            has_file = self.filename in gist.get("files", {})
            file_note = "あり" if has_file else "なし（最初の保存時に作成されます）"
            results.append(
                DiagnosticResult("Gist を読めるか", True, f"Gist を作ったアカウント: {gist_owner} ／ {self.filename}: {file_note}")
            )

            # 3. アカウントの一致
            if token_owner and gist_owner:
                same = token_owner.lower() == gist_owner.lower()
                detail = (
                    "同じアカウントです"
                    if same
                    else (
                        f"Gist は「{gist_owner}」、トークンは「{token_owner}」のものです。他人の Gist には書き込めません。"
                        "同じアカウントで Gist を作り直すか、Gist の持ち主のアカウントでトークンを発行し直してください"
                    )
                )
                results.append(DiagnosticResult("Gist とトークンが同じアカウントか", same, detail))

            # 4. 書き込み（現在の内容をそのまま書き戻す）
            try:
                content = self._current_content(gist)
                self._request(
                    "PATCH",
                    f"{GITHUB_API_URL}/gists/{self.gist_id}",
                    {"files": {self.filename: {"content": content}}},
                )
                results.append(DiagnosticResult("Gist に書き込めるか", True, "書き込めました（履歴の内容は変わっていません）"))
            except HistoryBackendError as exc:
                results.append(DiagnosticResult("Gist に書き込めるか", False, str(exc)))
        return results


@dataclass(frozen=True)
class DiagnosticResult:
    """接続診断の確認項目1つ分の結果。"""

    name: str  # 確認項目の名前
    ok: bool  # 問題がなければ True
    detail: str  # 確認結果の詳細（失敗時は原因と対処）
