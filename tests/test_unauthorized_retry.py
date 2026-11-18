import io
import json
import time

import pytest
import responses

from meli_sdk.exceptions import MeliAPIError, MeliTokenExpiredError

API_URL = "https://api.mercadolibre.com"
REFRESH_BODY = {
    "access_token": "APP_USR-new",
    "refresh_token": "TG-refresh-2",
    "expires_in": 21600,
    "user_id": 12345,
}


class NonSeekableFile:
    """File-like object that supports read() but not seek()."""

    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


def test_401_refreshes_and_retries_once(client, mocked):
    """A 401 triggers one refresh and one retry with the new bearer."""
    mocked.add(responses.GET, f"{API_URL}/users/me", status=401, json={"message": "invalid"})
    mocked.add(responses.POST, f"{API_URL}/oauth/token", json=REFRESH_BODY)
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    assert client.request("GET", "/users/me") == {"id": 12345}

    get_calls = [call for call in mocked.calls if call.request.method == "GET"]
    refresh_calls = [call for call in mocked.calls if call.request.method == "POST"]
    assert len(get_calls) == 2
    assert len(refresh_calls) == 1
    assert get_calls[0].request.headers["Authorization"] == "Bearer APP_USR-valid"
    assert get_calls[1].request.headers["Authorization"] == "Bearer APP_USR-new"


def test_second_401_raises(client, mocked):
    """A second 401 is raised and never retried again."""
    mocked.add(responses.GET, f"{API_URL}/users/me", status=401, json={"message": "invalid"})
    mocked.add(responses.POST, f"{API_URL}/oauth/token", json=REFRESH_BODY)
    mocked.add(responses.GET, f"{API_URL}/users/me", status=401, json={"message": "invalid"})

    with pytest.raises(MeliAPIError) as exc_info:
        client.request("GET", "/users/me")

    assert exc_info.value.status_code == 401
    get_calls = [call for call in mocked.calls if call.request.method == "GET"]
    refresh_calls = [call for call in mocked.calls if call.request.method == "POST"]
    assert len(get_calls) == 2
    assert len(refresh_calls) == 1


def test_401_uses_token_refreshed_by_another_thread(client, storage, mocked):
    """A token refreshed while the request was in flight is used without a new refresh."""
    calls = {"count": 0}

    def users_callback(request):
        calls["count"] += 1
        if calls["count"] == 1:
            now = time.time()
            storage.save_token({
                "access_token": "APP_USR-other",
                "refresh_token": "TG-refresh-3",
                "expires_in": 21600,
                "created_at": now,
                "expires_at": now + 21600,
                "user_id": 12345,
            })
            return (401, {}, json.dumps({"message": "invalid"}))
        return (200, {}, json.dumps({"id": 12345}))

    mocked.add_callback(responses.GET, f"{API_URL}/users/me", callback=users_callback)

    assert client.request("GET", "/users/me") == {"id": 12345}

    assert [call.request.method for call in mocked.calls] == ["GET", "GET"]
    assert mocked.calls[1].request.headers["Authorization"] == "Bearer APP_USR-other"


def test_401_on_post_json_is_retried_once(client, mocked):
    """A 401 on a POST with a JSON body is retried once."""
    mocked.add(responses.POST, f"{API_URL}/items", status=401, json={"message": "invalid"})
    mocked.add(responses.POST, f"{API_URL}/oauth/token", json=REFRESH_BODY)
    mocked.add(responses.POST, f"{API_URL}/items", status=201, json={"id": "MLA1"})

    assert client.request("POST", "/items", json={"title": "x"}) == {"id": "MLA1"}

    item_calls = [
        call for call in mocked.calls if call.request.url == f"{API_URL}/items"
    ]
    assert len(item_calls) == 2
    assert item_calls[1].request.headers["Authorization"] == "Bearer APP_USR-new"


def test_401_with_non_seekable_file_is_not_retried(client, mocked):
    """A 401 for a non-seekable upload is raised without retrying."""
    upload = NonSeekableFile(b"%PDF-1.4 invoice payload")
    mocked.add(
        responses.POST,
        f"{API_URL}/packs/123/fiscal_documents",
        status=401,
        json={"message": "invalid"},
    )

    with pytest.raises(MeliAPIError) as exc_info:
        client.request(
            "POST", "/packs/123/fiscal_documents", files={"fiscal_document": upload}
        )

    assert exc_info.value.status_code == 401
    assert len(mocked.calls) == 1


def test_401_when_refresh_fails_raises_token_expired(client, mocked):
    """A rejected refresh propagates MeliTokenExpiredError."""
    mocked.add(responses.GET, f"{API_URL}/users/me", status=401, json={"message": "invalid"})
    mocked.add(
        responses.POST,
        f"{API_URL}/oauth/token",
        status=400,
        json={"error": "invalid_grant"},
    )

    with pytest.raises(MeliTokenExpiredError):
        client.request("GET", "/users/me")


def test_401_without_refresh_token_raises_token_expired(client, storage, mocked):
    """A 401 without a refresh token raises MeliTokenExpiredError."""
    token = storage.load_token()
    token.pop("refresh_token")
    storage.save_token(token)
    mocked.add(responses.GET, f"{API_URL}/users/me", status=401, json={"message": "invalid"})

    with pytest.raises(MeliTokenExpiredError):
        client.request("GET", "/users/me")
