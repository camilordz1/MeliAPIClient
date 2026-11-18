import contextlib
import time
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
import responses
from freezegun import freeze_time

from meli_sdk import CallbackTokenStorage, MemoryTokenStorage
from meli_sdk.client import MeliClient
from meli_sdk.exceptions import MeliAPIError, MeliConnectionError

API_URL = "https://api.mercadolibre.com"
REDIRECT_URI = "https://app.example.com/callback"
TOKEN_BODY = {
    "access_token": "APP_USR-new",
    "refresh_token": "TG-refresh-2",
    "expires_in": 21600,
    "user_id": 12345,
}


def make_client(token_storage) -> MeliClient:
    """Return a MeliClient with the shared test credentials."""
    return MeliClient(
        client_id="cid", client_secret="csecret", token_storage=token_storage
    )


def test_authorization_url_for_mco(client):
    """The MCO authorization URL carries the documented parameters."""
    url = client.get_authorization_url(REDIRECT_URI, state="state-123")

    parts = urlsplit(url)
    assert parts.scheme == "https"
    assert parts.netloc == "auth.mercadolibre.com.co"
    assert parts.path == "/authorization"
    assert parse_qs(parts.query) == {
        "response_type": ["code"],
        "client_id": ["cid"],
        "redirect_uri": [REDIRECT_URI],
        "state": ["state-123"],
    }


def test_authorization_url_with_pkce(client):
    """A code_challenge adds the PKCE parameters."""
    url = client.get_authorization_url(
        REDIRECT_URI, state="state-123", code_challenge="challenge-abc"
    )

    params = parse_qs(urlsplit(url).query)
    assert params["code_challenge"] == ["challenge-abc"]
    assert params["code_challenge_method"] == ["S256"]


HOSTS = {
    "MCO": "auth.mercadolibre.com.co",
    "MLA": "auth.mercadolibre.com.ar",
    "MLM": "auth.mercadolibre.com.mx",
    "MLB": "auth.mercadolivre.com.br",
    "MLC": "auth.mercadolibre.cl",
    "MPE": "auth.mercadolibre.com.pe",
    "MLU": "auth.mercadolibre.com.uy",
}


@pytest.mark.parametrize("site_id,host", HOSTS.items())
def test_authorization_url_hosts(client, site_id, host):
    """Every supported site uses its own authorization host."""
    url = client.get_authorization_url(
        REDIRECT_URI, state="state-123", site_id=site_id
    )

    assert urlsplit(url).netloc == host


def test_authorization_url_unknown_site_raises(client):
    """An unknown site is rejected."""
    with pytest.raises(ValueError):
        client.get_authorization_url(REDIRECT_URI, state="state-123", site_id="XXX")


@pytest.mark.parametrize("state", ["", "   "])
def test_authorization_url_requires_state(client, state):
    """The state parameter is required."""
    with pytest.raises(ValueError):
        client.get_authorization_url(REDIRECT_URI, state=state)


def test_exchange_code_posts_form_and_stores_token(mocked):
    """The exchange posts the form and persists the enriched token."""
    storage = MemoryTokenStorage()
    client = make_client(storage)
    mocked.add(
        responses.POST,
        f"{API_URL}/oauth/token",
        json=TOKEN_BODY,
        match=[
            responses.matchers.urlencoded_params_matcher(
                {
                    "grant_type": "authorization_code",
                    "client_id": "cid",
                    "client_secret": "csecret",
                    "code": "AUTHCODE",
                    "redirect_uri": REDIRECT_URI,
                }
            )
        ],
    )

    with freeze_time("2026-02-01T12:00:00Z"):
        now = time.time()
        token = client.exchange_code("AUTHCODE", REDIRECT_URI)
        stored = storage.load_token()

    assert token["access_token"] == "APP_USR-new"
    assert stored["created_at"] == now
    assert stored["expires_at"] == now + 21600
    assert stored["user_id"] == 12345


def test_exchange_code_sends_code_verifier(mocked):
    """The PKCE verifier is sent when provided."""
    storage = MemoryTokenStorage()
    client = make_client(storage)
    mocked.add(
        responses.POST,
        f"{API_URL}/oauth/token",
        json=TOKEN_BODY,
        match=[
            responses.matchers.urlencoded_params_matcher(
                {
                    "grant_type": "authorization_code",
                    "client_id": "cid",
                    "client_secret": "csecret",
                    "code": "AUTHCODE",
                    "redirect_uri": REDIRECT_URI,
                    "code_verifier": "verifier-abc",
                }
            )
        ],
    )

    token = client.exchange_code("AUTHCODE", REDIRECT_URI, code_verifier="verifier-abc")

    assert token["access_token"] == "APP_USR-new"


def test_exchange_code_error_raises_api_error_without_secrets(mocked):
    """An error response raises MeliAPIError without leaking the code or secret."""
    storage = MemoryTokenStorage()
    client = make_client(storage)
    mocked.add(
        responses.POST,
        f"{API_URL}/oauth/token",
        status=400,
        json={"error": "invalid_grant", "message": "invalid code"},
    )

    with pytest.raises(MeliAPIError) as exc_info:
        client.exchange_code("AUTHCODE", REDIRECT_URI)

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "invalid_grant"
    assert "csecret" not in str(exc_info.value)
    assert "AUTHCODE" not in str(exc_info.value)


def test_exchange_code_retries_on_429(mocked):
    """The exchange goes through the safe retry loop."""
    storage = MemoryTokenStorage()
    client = make_client(storage)
    mocked.add(responses.POST, f"{API_URL}/oauth/token", status=429)
    mocked.add(responses.POST, f"{API_URL}/oauth/token", json=TOKEN_BODY)

    token = client.exchange_code("AUTHCODE", REDIRECT_URI)

    assert token["access_token"] == "APP_USR-new"
    assert len([call for call in mocked.calls if call.request.method == "POST"]) == 2


def test_exchange_code_uses_storage_lock(mocked):
    """The storage lock wraps the exchange and the save."""
    events = []
    state = {}

    def save_token(token_data):
        events.append("save")
        state.update(token_data)

    @contextlib.contextmanager
    def database_lock():
        events.append("lock_enter")
        try:
            yield
        finally:
            events.append("lock_exit")

    storage = CallbackTokenStorage(lambda: {}, save_token, lock_callback=database_lock)
    client = make_client(storage)
    mocked.add(responses.POST, f"{API_URL}/oauth/token", json=TOKEN_BODY)

    client.exchange_code("AUTHCODE", REDIRECT_URI)

    assert events == ["lock_enter", "save", "lock_exit"]
    assert state["access_token"] == "APP_USR-new"


def test_exchange_code_connection_error_raises_meli_connection_error(mocked):
    """A connection failure during the exchange raises MeliConnectionError."""
    storage = MemoryTokenStorage()
    client = make_client(storage)
    mocked.add(
        responses.POST,
        f"{API_URL}/oauth/token",
        body=requests.ConnectionError("boom"),
    )

    with pytest.raises(MeliConnectionError):
        client.exchange_code("AUTHCODE", REDIRECT_URI)
