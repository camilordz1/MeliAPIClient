import time
from unittest.mock import MagicMock, patch

import pytest
import requests
import responses

from meli_sdk.client import MeliClient

API_URL = "https://api.mercadolibre.com"


def make_client(storage, **kwargs) -> MeliClient:
    """Return a MeliClient with the shared test credentials and extra options."""
    return MeliClient(
        client_id="cid",
        client_secret="csecret",
        token_storage=storage,
        **kwargs,
    )


def test_default_timeout_is_30_seconds(client, mocked):
    """A request without options carries the 30 second default timeout."""
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    assert mocked.calls[0].request.req_kwargs["timeout"] == 30.0


@pytest.mark.parametrize("timeout", [5, (3.05, 27)])
def test_custom_timeout_float_and_tuple_are_sent(storage, mocked, timeout):
    """A custom timeout, as a number or a (connect, read) tuple, is forwarded."""
    client = make_client(storage, timeout=timeout)
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    assert mocked.calls[0].request.req_kwargs["timeout"] == timeout


def test_per_call_timeout_overrides_default(client, mocked):
    """A timeout passed to request() wins over the client default."""
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me", timeout=2)

    assert mocked.calls[0].request.req_kwargs["timeout"] == 2


def test_refresh_uses_client_timeout(storage, mocked):
    """The token refresh carries the client timeout."""
    token = storage.load_token()
    token["expires_at"] = time.time() - 10
    storage.save_token(token)
    client = make_client(storage, timeout=7)
    mocked.add(
        responses.POST,
        f"{API_URL}/oauth/token",
        json={
            "access_token": "APP_USR-new",
            "refresh_token": "TG-refresh-2",
            "expires_in": 21600,
            "user_id": 12345,
        },
    )
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    refresh_call = next(call for call in mocked.calls if call.request.method == "POST")
    assert refresh_call.request.req_kwargs["timeout"] == 7


@pytest.mark.parametrize(
    "timeout", [0, -1, True, "30", None, (1,), (1, 0), (1, 2, 3)]
)
def test_invalid_timeout_raises_value_error(storage, timeout):
    """Invalid timeout values are rejected when the client is built."""
    with pytest.raises(ValueError):
        make_client(storage, timeout=timeout)


def test_requests_reuse_one_session(storage, mocked):
    """Every call goes through the same session, never through requests.request."""
    session = requests.Session()
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 1})
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 2})

    with patch.object(session, "request", wraps=session.request) as spy:
        client = make_client(storage, session=session)
        with patch("requests.request", side_effect=AssertionError("must not be used")):
            client.request("GET", "/users/me")
            client.request("GET", "/users/me")

    assert spy.call_count == 2


def test_close_closes_owned_session(storage):
    """close() closes a session created by the client."""
    client = make_client(storage)

    with patch.object(client.session, "close") as close:
        client.close()

    close.assert_called_once()


def test_close_does_not_close_injected_session(storage):
    """close() leaves an injected session open."""
    session = MagicMock(spec=requests.Session)
    client = make_client(storage, session=session)

    client.close()

    session.close.assert_not_called()


def test_context_manager_closes_owned_session(storage):
    """The context manager returns the client and closes the owned session."""
    client = make_client(storage)

    with patch.object(client.session, "close") as close:
        with client as entered:
            assert entered is client

    close.assert_called_once()


def test_close_is_idempotent(storage):
    """Calling close() twice closes the owned session only once."""
    client = make_client(storage)

    with patch.object(client.session, "close") as close:
        client.close()
        client.close()

    assert close.call_count == 1
