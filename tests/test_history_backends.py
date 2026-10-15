"""履歴の保存先（ファイル / GitHub Gist）のテスト。

Gist はインターネット上のサービスのため、テストでは通信部分（opener）を偽物に差し替える。
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from quiz.history_backends import FileHistoryBackend, GistHistoryBackend, HistoryBackendError

# ---------------------------------------------------------------
# ファイル
# ---------------------------------------------------------------


def test_file_backend_round_trip(tmp_path):
    backend = FileHistoryBackend(tmp_path / "sub" / "history.json")
    assert backend.load() is None
    backend.save({"version": 1, "question_stats": {}})
    assert backend.load() == {"version": 1, "question_stats": {}}


def test_file_backend_empty_object_is_treated_as_empty(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{}", encoding="utf-8")
    assert FileHistoryBackend(path).load() is None


def test_file_backend_broken_json_raises(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(HistoryBackendError):
        FileHistoryBackend(path).load()


# ---------------------------------------------------------------
# GitHub Gist（通信を偽物に差し替え）
# ---------------------------------------------------------------


class _FakeResponse(io.BytesIO):
    """urlopen の戻り値の代わり（with 文で使える）。"""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class _FakeGitHub:
    """GitHub Gist API の偽物。受け取ったリクエストを記録し、決まった応答を返す。"""

    def __init__(self, files=None, error_code=None):
        self.files = files if files is not None else {}
        self.error_code = error_code
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error_code:
            raise urllib.error.HTTPError(request.full_url, self.error_code, "error", {}, None)
        if request.get_method() == "PATCH":
            body = json.loads(request.data.decode("utf-8"))
            for name, info in body["files"].items():
                self.files[name] = {"content": info["content"], "truncated": False}
            return _FakeResponse(b"{}")
        return _FakeResponse(json.dumps({"files": self.files}).encode("utf-8"))


def test_gist_backend_round_trip():
    fake = _FakeGitHub()
    backend = GistHistoryBackend("token123", "gist-id", opener=fake)
    assert backend.load() is None  # まだファイルが無い
    backend.save({"version": 1, "mock_results": []})
    assert backend.load() == {"version": 1, "mock_results": []}


def test_gist_backend_sends_token_and_targets_gist():
    fake = _FakeGitHub()
    GistHistoryBackend("token123", "gist-id", opener=fake).load()
    request = fake.requests[0]
    assert request.full_url == "https://api.github.com/gists/gist-id"
    assert request.get_header("Authorization") == "Bearer token123"


def test_gist_backend_initial_empty_object_is_treated_as_empty():
    fake = _FakeGitHub(files={"history.json": {"content": "{}", "truncated": False}})
    assert GistHistoryBackend("t", "g", opener=fake).load() is None


def test_gist_backend_http_error_is_wrapped():
    fake = _FakeGitHub(error_code=401)
    with pytest.raises(HistoryBackendError, match="401"):
        GistHistoryBackend("bad-token", "g", opener=fake).load()


def test_gist_backend_describe_does_not_reveal_token():
    assert "token123" not in GistHistoryBackend("token123", "g").describe()
