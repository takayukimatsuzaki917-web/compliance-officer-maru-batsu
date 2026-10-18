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
RATE_URL = "https://api.github.com/rate_limit"

#: テストで使う「現在時刻」と「制限の解除時刻」（UNIX時刻。2026-10-18 12:00 と 13:05 日本時間）
NOW_EPOCH = 1792292400
RESET_EPOCH = NOW_EPOCH + 65 * 60


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


def _rate_limit(remaining=4990, used=10, limit=5000, reset=RESET_EPOCH):
    """/rate_limit の応答を作る。"""
    return {"resources": {"core": {"limit": limit, "used": used, "remaining": remaining, "reset": reset}}}


class _FakeGitHub:
    """(メソッド, URL) ごとに応答またはエラーを返す GitHub API の偽物。

    /rate_limit を指定しなかった場合は、残り回数が十分ある応答を返す。
    """

    def __init__(self, routes):
        self.routes = {("GET", RATE_URL): _rate_limit(), **routes}
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
    assert len(results) == 5  # 利用回数・トークン・Gist・アカウント・書き込み
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


# ---------------------------------------------------------------
# 利用回数の上限
# ---------------------------------------------------------------


def test_diagnosis_shows_usage_first():
    fake = _FakeGitHub({
        ("GET", USER_URL): {"login": "alice"},
        ("GET", GIST_URL): _gist("alice"),
        ("PATCH", GIST_URL): {},
    })
    results = GistHistoryBackend("t", GIST_ID, opener=fake).diagnose()
    assert results[0].name == "GitHub API の利用回数"
    assert results[0].ok
    assert "使用済み 10回" in results[0].detail and "残り 4990回" in results[0].detail


def test_diagnosis_stops_when_rate_limited():
    fake = _FakeGitHub({("GET", RATE_URL): _rate_limit(remaining=0, used=5000)})
    results = GistHistoryBackend("t", GIST_ID, opener=fake, clock=lambda: NOW_EPOCH).diagnose()
    assert len(results) == 1
    assert not results[0].ok
    assert "10/18 13:05" in results[0].detail  # リセット時刻を日本時間で表示
    assert "他のツール" in results[0].detail
    # 上限中は /rate_limit 以外に通信していない
    assert [r.full_url for r in fake.requests] == [RATE_URL]


def _rate_limited_error(url):
    return _http_error(url, 403, "API rate limit exceeded for user ID 1.", {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(RESET_EPOCH)})


def test_rate_limit_error_shows_reset_time_and_no_permission_hint():
    fake = _FakeGitHub({("PATCH", GIST_URL): _rate_limited_error(GIST_URL)})
    backend = GistHistoryBackend("t", GIST_ID, opener=fake, clock=lambda: NOW_EPOCH)
    with pytest.raises(HistoryBackendError) as excinfo:
        backend.save({"version": 1})
    message = str(excinfo.value)
    assert "10/18 13:05" in message
    assert "Read and write" not in message  # 権限の問題ではないので権限の案内は出さない


def test_requests_are_held_until_reset_after_rate_limit():
    now = [NOW_EPOCH]
    fake = _FakeGitHub({
        ("PATCH", GIST_URL): _rate_limited_error(GIST_URL),
        ("GET", GIST_URL): _gist("alice"),
    })
    backend = GistHistoryBackend("t", GIST_ID, opener=fake, clock=lambda: now[0])
    with pytest.raises(HistoryBackendError):
        backend.save({"version": 1})
    sent = len(fake.requests)

    # 解除時刻までは通信せずにエラーにする
    with pytest.raises(HistoryBackendError, match="見合わせています") as excinfo:
        backend.load()
    assert excinfo.value.status == 429
    assert len(fake.requests) == sent

    # 解除時刻を過ぎれば再び通信する
    now[0] = RESET_EPOCH + 1
    assert backend.load() == {"version": 1}
    assert len(fake.requests) == sent + 1


def test_retry_after_header_is_respected():
    error = _http_error(GIST_URL, 403, "You have exceeded a secondary rate limit", {"Retry-After": "120"})
    fake = _FakeGitHub({("GET", GIST_URL): error})
    backend = GistHistoryBackend("t", GIST_ID, opener=fake, clock=lambda: NOW_EPOCH)
    with pytest.raises(HistoryBackendError, match="10/18 12:02"):
        backend.load()
