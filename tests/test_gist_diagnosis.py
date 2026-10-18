"""Gist への接続診断と、GitHub のエラー詳細の表示のテスト。

GitHub API の代わりに、URL と HTTP メソッドごとに応答を決められる偽物を使う。
"""

from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message

import pytest

from quiz.history_backends import GistHistoryBackend, HistoryBackendError

GIST_ID = "0123456789abcdef0123456789abcdef"
USER_URL = "https://api.github.com/user"
GIST_URL = f"https://api.github.com/gists/{GIST_ID}"


class _Response(io.BytesIO):
    """urlopen の戻り値の代わり（with 文で使える）。"""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _http_error(url, code, message="", headers=None):
    """GitHub が返すような HTTP エラー（本文とヘッダー付き）を作る。"""
    header_obj = Message()
    for key, value in (headers or {}).items():
        header_obj[key] = value
    body = json.dumps({"message": message}).encode("utf-8")
    return urllib.error.HTTPError(url, code, "error", header_obj, io.BytesIO(body))


class _FakeGitHub:
    """(メソッド, URL) ごとに応答またはエラーを返す GitHub API の偽物。"""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        result = self.routes[(request.get_method(), request.full_url)]
        if isinstance(result, Exception):
            raise result
        return _Response(json.dumps(result).encode("utf-8"))


def _gist(owner="alice", content='{"version": 1}'):
    return {"owner": {"login": owner}, "files": {"history.json": {"content": content, "truncated": False}}}


def _results_by_name(results):
    return {r.name: r for r in results}


def test_all_checks_pass():
    fake = _FakeGitHub({
        ("GET", USER_URL): {"login": "alice"},
        ("GET", GIST_URL): _gist("alice"),
        ("PATCH", GIST_URL): {},
    })
    results = GistHistoryBackend("t", GIST_ID, opener=fake).diagnose()
    assert all(r.ok for r in results)
    assert len(results) == 4
    # 書き込み確認では現在の内容をそのまま書き戻す（履歴は変わらない）
    patch = [r for r in fake.requests if r.get_method() == "PATCH"][0]
    assert json.loads(patch.data)["files"]["history.json"]["content"] == '{"version": 1}'


def test_read_only_permission_is_reported_with_required_permission():
    error = _http_error(
        GIST_URL, 403, "Resource not accessible by personal access token", {"X-Accepted-GitHub-Permissions": "gists=write"}
    )
    fake = _FakeGitHub({
        ("GET", USER_URL): {"login": "alice"},
        ("GET", GIST_URL): _gist("alice"),
        ("PATCH", GIST_URL): error,
    })
    results = _results_by_name(GistHistoryBackend("t", GIST_ID, opener=fake).diagnose())
    write = results["Gist に書き込めるか"]
    assert not write.ok
    assert "HTTP 403" in write.detail
    assert "Resource not accessible by personal access token" in write.detail
    assert "必要な権限: gists=write" in write.detail
    assert results["Gist とトークンが同じアカウントか"].ok


def test_owner_mismatch_is_reported():
    fake = _FakeGitHub({
        ("GET", USER_URL): {"login": "alice"},
        ("GET", GIST_URL): _gist("bob"),
        ("PATCH", GIST_URL): _http_error(GIST_URL, 403, "Forbidden"),
    })
    results = _results_by_name(GistHistoryBackend("t", GIST_ID, opener=fake).diagnose())
    mismatch = results["Gist とトークンが同じアカウントか"]
    assert not mismatch.ok
    assert "bob" in mismatch.detail and "alice" in mismatch.detail


def test_invalid_token_is_reported():
    fake = _FakeGitHub({
        ("GET", USER_URL): _http_error(USER_URL, 401, "Bad credentials"),
        ("GET", GIST_URL): _gist("alice"),
        ("PATCH", GIST_URL): _http_error(GIST_URL, 401, "Bad credentials"),
    })
    results = _results_by_name(GistHistoryBackend("t", GIST_ID, opener=fake).diagnose())
    assert not results["トークンが有効か"].ok
    assert "Bad credentials" in results["トークンが有効か"].detail


def test_missing_gist_stops_before_write_check():
    fake = _FakeGitHub({
        ("GET", USER_URL): {"login": "alice"},
        ("GET", GIST_URL): _http_error(GIST_URL, 404, "Not Found"),
    })
    results = _results_by_name(GistHistoryBackend("t", GIST_ID, opener=fake).diagnose())
    assert not results["Gist を読めるか"].ok
    assert "Gist に書き込めるか" not in results


def test_save_error_includes_github_message_and_status():
    error = _http_error(GIST_URL, 403, "Resource not accessible by personal access token", {"X-Accepted-GitHub-Permissions": "gists=write"})
    fake = _FakeGitHub({("PATCH", GIST_URL): error})
    with pytest.raises(HistoryBackendError) as excinfo:
        GistHistoryBackend("t", GIST_ID, opener=fake).save({"version": 1})
    assert excinfo.value.status == 403
    assert "gists=write" in str(excinfo.value)


def test_rate_limit_is_reported():
    error = _http_error(GIST_URL, 403, "API rate limit exceeded", {"X-RateLimit-Remaining": "0"})
    fake = _FakeGitHub({("GET", GIST_URL): error})
    with pytest.raises(HistoryBackendError, match="利用回数の上限"):
        GistHistoryBackend("t", GIST_ID, opener=fake).load()
