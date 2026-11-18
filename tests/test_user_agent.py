import re
import time

import pytest
import requests
import responses

import meli_sdk
from meli_sdk.client import MeliClient

API_URL = "https://api.mercadolibre.com"
USER_AGENT_PATTERN = r"meli-sdk/(\S+) python-requests/(\S+)"


def make_client(storage, **kwargs) -> MeliClient:
    """Return a MeliClient with the shared test credentials."""
    return MeliClient(
        client_id="cid", client_secret="csecret", token_storage=storage, **kwargs
    )


def test_default_user_agent_is_sent(client, mocked):
    """A request carries the identifying default User-Agent."""
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    header = mocked.calls[0].request.headers["User-Agent"]
    match = re.fullmatch(USER_AGENT_PATTERN, header)
    assert match is not None, header
    assert match.group(1) == meli_sdk.__version__
    assert match.group(2) == requests.__version__


def test_custom_user_agent_is_prepended(storage, mocked):
    """A custom user_agent is prepended to the identifying default."""
    client = make_client(storage, user_agent="Zincro/2.0")
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    assert mocked.calls[0].request.headers["User-Agent"] == (
        f"Zincro/2.0 meli-sdk/{meli_sdk.__version__} "
        f"python-requests/{requests.__version__}"
    )


def test_user_agent_is_sent_on_refresh(storage, mocked):
    """The token refresh also carries the identifying User-Agent."""
    token = storage.load_token()
    token["expires_at"] = time.time() - 10
    storage.save_token(token)
    client = make_client(storage)
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
    assert re.fullmatch(
        USER_AGENT_PATTERN, refresh_call.request.headers["User-Agent"]
    ) is not None


def test_per_call_user_agent_wins(client, mocked):
    """A User-Agent passed per call replaces the client one."""
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me", headers={"User-Agent": "Custom/1"})

    assert mocked.calls[0].request.headers["User-Agent"] == "Custom/1"


def test_injected_session_headers_are_not_mutated(storage, mocked):
    """The client does not write the User-Agent into an injected session."""
    session = requests.Session()
    before = dict(session.headers)
    client = make_client(storage, session=session)
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    assert dict(session.headers) == before
    assert mocked.calls[0].request.headers["User-Agent"].startswith("meli-sdk/")


@pytest.mark.parametrize("user_agent", ["", "   ", "a\r\nX: y", "a\nb"])
def test_invalid_user_agent_raises(storage, user_agent):
    """Empty, whitespace-only or multi-line User-Agents are rejected."""
    with pytest.raises(ValueError):
        make_client(storage, user_agent=user_agent)
