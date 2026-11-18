import time

import pytest
import responses
from freezegun import freeze_time

from meli_sdk.client import MeliClient
from meli_sdk.exceptions import MeliTokenExpiredError
from meli_sdk.storage import MemoryTokenStorage

API_URL = "https://api.mercadolibre.com"
FROZEN_NOW = "2026-02-01T12:00:00Z"


def _expire_token(storage, offset=-10):
    """Move the stored token's expiry into the past."""
    token = storage.load_token()
    token["expires_at"] = time.time() + offset
    storage.save_token(token)


def _register_refresh(mocked, access_token="APP_USR-new"):
    return mocked.add(
        responses.POST,
        f"{API_URL}/oauth/token",
        json={
            "access_token": access_token,
            "refresh_token": "TG-refresh-2",
            "expires_in": 21600,
            "user_id": 12345,
        },
        match=[
            responses.matchers.urlencoded_params_matcher(
                {
                    "grant_type": "refresh_token",
                    "client_id": "cid",
                    "client_secret": "csecret",
                    "refresh_token": "TG-refresh-1",
                }
            )
        ],
    )


def test_valid_token_does_not_refresh(client, mocked):
    """A token outside the refresh buffer is used without a token request."""
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    assert client.request("GET", "/users/me") == {"id": 12345}
    assert len(mocked.calls) == 1


def test_expired_token_refreshes_and_persists(client, storage, mocked):
    """An expired token is refreshed, persisted and used for the next request."""
    with freeze_time(FROZEN_NOW):
        now = time.time()
        _expire_token(storage)
        _register_refresh(mocked)
        mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

        client.request("GET", "/users/me")

        stored = storage.load_token()
        assert stored["access_token"] == "APP_USR-new"
        assert stored["created_at"] == now
        assert stored["expires_at"] == now + 21600

        get_call = next(
            call for call in mocked.calls if call.request.method == "GET"
        )
        assert get_call.request.headers["Authorization"] == "Bearer APP_USR-new"


def test_token_inside_buffer_is_refreshed(client, storage, mocked):
    """A token expiring inside the 300 second buffer is refreshed early."""
    with freeze_time(FROZEN_NOW):
        _expire_token(storage, offset=100)
        _register_refresh(mocked)
        mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

        client.request("GET", "/users/me")

        assert storage.load_token()["access_token"] == "APP_USR-new"


def test_missing_expires_at_forces_refresh(client, storage, mocked):
    """A token without expires_at is refreshed."""
    with freeze_time(FROZEN_NOW):
        token = storage.load_token()
        token.pop("expires_at")
        storage.save_token(token)
        _register_refresh(mocked)
        mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

        client.request("GET", "/users/me")

        assert storage.load_token()["access_token"] == "APP_USR-new"


def test_no_stored_token_raises(mocked):
    """An empty storage prevents any request and raises MeliTokenExpiredError."""
    empty_client = MeliClient(
        client_id="cid",
        client_secret="csecret",
        token_storage=MemoryTokenStorage(),
    )

    with pytest.raises(MeliTokenExpiredError):
        empty_client.request("GET", "/users/me")


def test_expired_without_refresh_token_raises(client, storage, mocked):
    """An expired token without a refresh token raises MeliTokenExpiredError."""
    with freeze_time(FROZEN_NOW):
        _expire_token(storage)
        token = storage.load_token()
        token.pop("refresh_token")
        storage.save_token(token)

        with pytest.raises(MeliTokenExpiredError):
            client.request("GET", "/users/me")


def test_refresh_http_error_raises_token_expired(client, storage, mocked):
    """A rejected refresh request raises MeliTokenExpiredError."""
    with freeze_time(FROZEN_NOW):
        _expire_token(storage)
        mocked.add(
            responses.POST,
            f"{API_URL}/oauth/token",
            status=400,
            json={"error": "invalid_grant"},
        )

        with pytest.raises(MeliTokenExpiredError):
            client.request("GET", "/users/me")


@pytest.mark.xfail(
    strict=True, reason="Known bug: refresh has no timeout; fixed in F1-01"
)
def test_refresh_sets_a_timeout(client, storage, mocked):
    """The refresh request must carry a timeout."""
    with freeze_time(FROZEN_NOW):
        _expire_token(storage)
        _register_refresh(mocked)

        client.refresh_token("TG-refresh-1")

        assert mocked.calls[0].request.req_kwargs.get("timeout") is not None
