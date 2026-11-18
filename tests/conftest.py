import time

import pytest
import responses

from MeliAPIClient.client import MeliClient
from MeliAPIClient.storage import MemoryTokenStorage


@pytest.fixture
def valid_token() -> dict:
    """Return a token that is valid for the next six hours."""
    now = time.time()
    return {
        "access_token": "APP_USR-valid",
        "refresh_token": "TG-refresh-1",
        "expires_in": 21600,
        "created_at": now,
        "expires_at": now + 21600,
        "user_id": 12345,
    }


@pytest.fixture
def storage(valid_token):
    """Return an in-memory token storage seeded with a valid token."""
    return MemoryTokenStorage(dict(valid_token))


@pytest.fixture
def client(storage):
    """Return a MeliClient wired to the in-memory token storage."""
    return MeliClient(client_id="cid", client_secret="csecret", token_storage=storage)


@pytest.fixture
def mocked():
    """Activate responses for the duration of a test."""
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        yield rsps
