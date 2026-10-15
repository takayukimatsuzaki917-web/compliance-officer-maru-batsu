"""履歴の保存先（ファイル / GitHub Gist）のテスト。

Gist はインターネット上のサービスのため、テストでは通信部分（opener）を偽物に差し替える。
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from quiz.history_backends import (
    FileHistoryBackend,
    GistHistoryBackend,
    HistoryBackendError,
    mask_gist_id,
    normalize_gist_id,
)

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
    backend = GistHistoryBackend("token123", "abc123", opener=fake)
    assert backend.load() is None  # まだファイルが無い
    backend.save({"version": 1, "mock_results": []})
    assert backend.load() == {"version": 1, "mock_results": []}


def test_gist_backend_sends_token_and_targets_gist():
    fake = _FakeGitHub()
    GistHistoryBackend("token123", "abc123", opener=fake).load()
    request = fake.requests[0]
    assert request.full_url == "https://api.github.com/gists/abc123"
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


# ---------------------------------------------------------------
# gist_id の表記ゆれの吸収とエラー表示
# ---------------------------------------------------------------

GIST_ID = "0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize(
    "value",
    [
        GIST_ID,
        f"  {GIST_ID}  ",
        f'"{GIST_ID}"',
        f"https://gist.github.com/someone/{GIST_ID}",
        f"https://gist.github.com/someone/{GIST_ID}/",
        f"https://gist.github.com/someone/{GIST_ID}#file-history-json",
        f"https://gist.github.com/{GIST_ID}.git",
        f"someone/{GIST_ID}",
    ],
)
def test_normalize_gist_id_accepts_common_formats(value):
    assert normalize_gist_id(value) == GIST_ID


@pytest.mark.parametrize("value", ["", "   ", "https://gist.github.com/", "abc-123", "日本語"])
def test_normalize_gist_id_rejects_invalid(value):
    with pytest.raises(HistoryBackendError, match="gist_id"):
        normalize_gist_id(value)


def test_gist_backend_uses_normalized_id_in_url():
    fake = _FakeGitHub()
    GistHistoryBackend("t", f"https://gist.github.com/someone/{GIST_ID}", opener=fake).load()
    assert fake.requests[0].full_url == f"https://api.github.com/gists/{GIST_ID}"


def test_gist_backend_404_message_points_to_gist_id():
    fake = _FakeGitHub(error_code=404)
    with pytest.raises(HistoryBackendError) as excinfo:
        GistHistoryBackend("t", GIST_ID, opener=fake).load()
    message = str(excinfo.value)
    assert "Gist が見つかりません" in message
    assert "0123…cdef（32文字）" in message  # id は一部だけ表示する
    assert GIST_ID not in message


def test_mask_gist_id_short_value():
    assert mask_gist_id("abc") == "abc（3文字）"
