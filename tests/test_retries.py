import datetime
import io
import logging
from email.utils import format_datetime

import pytest
import requests
import responses
from freezegun import freeze_time

from meli_sdk.client import MeliClient
from meli_sdk.exceptions import MeliAPIError, MeliConnectionError, MeliTokenExpiredError

API_URL = "https://api.mercadolibre.com"


def make_client(storage, sleeps, **kwargs) -> MeliClient:
    """Return a MeliClient with a recording sleep function."""
    client = MeliClient(
        client_id="cid",
        client_secret="csecret",
        token_storage=storage,
        **kwargs,
    )
    client._sleep = sleeps.append
    return client


@pytest.fixture
def sleeps(client):
    """Replace the client sleep function with a recorder."""
    recorded = []
    client._sleep = recorded.append
    return recorded


def test_get_retries_on_429_then_succeeds(client, mocked, sleeps):
    """A GET is retried on 429 with exponential backoff."""
    mocked.add(responses.GET, f"{API_URL}/users/me", status=429)
    mocked.add(responses.GET, f"{API_URL}/users/me", status=429)
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    assert client.request("GET", "/users/me") == {"id": 12345}

    assert len(mocked.calls) == 3
    assert sleeps == [0.5, 1.0]


def test_post_retries_on_429(client, mocked, sleeps):
    """A POST is retried on 429 because the request was rejected, not processed."""
    mocked.add(responses.POST, f"{API_URL}/items", status=429)
    mocked.add(responses.POST, f"{API_URL}/items", status=201, json={"id": "MLA1"})

    assert client.request("POST", "/items", json={"title": "x"}) == {"id": "MLA1"}

    assert len(mocked.calls) == 2


def test_post_is_not_retried_on_503(client, mocked, sleeps):
    """A POST is never retried on 5xx."""
    mocked.add(responses.POST, f"{API_URL}/items", status=503, json={"message": "down"})

    with pytest.raises(MeliAPIError) as exc_info:
        client.request("POST", "/items", json={"title": "x"})

    assert exc_info.value.status_code == 503
    assert len(mocked.calls) == 1
    assert sleeps == []


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_put_retries_on_502_503_504_and_500(client, mocked, sleeps, status):
    """A PUT is retried on the retryable 5xx statuses."""
    mocked.add(responses.PUT, f"{API_URL}/items/MLA1", status=status)
    mocked.add(responses.PUT, f"{API_URL}/items/MLA1", status=200, json={"ok": True})

    assert client.request("PUT", "/items/MLA1", json={"price": 1}) == {"ok": True}

    assert len(mocked.calls) == 2


def test_get_retries_connection_error_then_succeeds(client, mocked, sleeps):
    """A GET is retried after a connection error."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/me",
        body=requests.ConnectionError("boom"),
    )
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    assert client.request("GET", "/users/me") == {"id": 12345}

    assert len(mocked.calls) == 2
    assert sleeps == [0.5]


def test_post_connection_error_is_not_retried(client, mocked, sleeps):
    """A POST is not retried after a connection error."""
    mocked.add(
        responses.POST,
        f"{API_URL}/items",
        body=requests.ConnectionError("boom"),
    )

    with pytest.raises(MeliConnectionError):
        client.request("POST", "/items", json={"title": "x"})

    assert len(mocked.calls) == 1
    assert sleeps == []


def test_retry_after_seconds_is_honoured(client, mocked, sleeps):
    """A numeric Retry-After header sets the delay."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/me",
        status=429,
        headers={"Retry-After": "7"},
    )
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    assert sleeps == [7]


def test_retry_after_http_date_is_honoured(client, mocked, sleeps):
    """An HTTP-date Retry-After is converted to a delay."""
    with freeze_time("2026-02-01T12:00:00Z"):
        retry_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=10)
        mocked.add(
            responses.GET,
            f"{API_URL}/users/me",
            status=429,
            headers={"Retry-After": format_datetime(retry_at, usegmt=True)},
        )
        mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

        client.request("GET", "/users/me")

    assert sleeps == [10]


def test_retry_after_is_capped_by_max_backoff(client, mocked, sleeps):
    """A Retry-After above max_backoff is capped."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/me",
        status=429,
        headers={"Retry-After": "3600"},
    )
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    assert sleeps == [60.0]


def test_malformed_retry_after_falls_back_to_backoff(client, mocked, sleeps):
    """A malformed Retry-After falls back to the exponential backoff."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/me",
        status=429,
        headers={"Retry-After": "soon"},
    )
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    assert sleeps == [0.5]


def test_exhausted_retries_raise_final_error(storage, mocked, sleeps):
    """After max_retries the final response is handled normally."""
    client = make_client(storage, sleeps, max_retries=2)
    mocked.add(responses.GET, f"{API_URL}/users/me", status=429)
    mocked.add(responses.GET, f"{API_URL}/users/me", status=429)
    mocked.add(responses.GET, f"{API_URL}/users/me", status=429)

    with pytest.raises(MeliAPIError) as exc_info:
        client.request("GET", "/users/me")

    assert exc_info.value.status_code == 429
    assert len(mocked.calls) == 3
    assert len(sleeps) == 2


def test_max_retries_zero_disables_retries(storage, mocked, sleeps):
    """max_retries=0 disables the retry loop."""
    client = make_client(storage, sleeps, max_retries=0)
    mocked.add(responses.GET, f"{API_URL}/users/me", status=429)

    with pytest.raises(MeliAPIError) as exc_info:
        client.request("GET", "/users/me")

    assert exc_info.value.status_code == 429
    assert len(mocked.calls) == 1
    assert sleeps == []


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_4xx_other_than_429_is_not_retried(client, mocked, sleeps, status):
    """Other 4xx statuses are never retried."""
    mocked.add(responses.GET, f"{API_URL}/users/me", status=status, json={"message": "no"})

    with pytest.raises(MeliAPIError) as exc_info:
        client.request("GET", "/users/me")

    assert exc_info.value.status_code == status
    assert len(mocked.calls) == 1
    assert sleeps == []


def test_upload_retry_rewinds_file(client, mocked, sleeps, tmp_path):
    """A retried upload sends the whole file again."""
    pdf_bytes = b"%PDF-1.4 invoice payload"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(pdf_bytes)
    mocked.add(responses.POST, f"{API_URL}/packs/123/fiscal_documents", status=429)
    mocked.add(
        responses.POST,
        f"{API_URL}/packs/123/fiscal_documents",
        status=200,
        json={"ok": True},
    )

    assert client.bills.upload_fiscal_document(123, str(pdf_path)) == {"ok": True}

    assert len(mocked.calls) == 2
    assert pdf_bytes in mocked.calls[0].request.body
    assert pdf_bytes in mocked.calls[1].request.body


class NonSeekableFile:
    """File-like object that supports read() but not seek()."""

    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


def test_non_seekable_file_is_not_retried(client, mocked, sleeps):
    """A 429 for a non-seekable upload is not retried."""
    upload = NonSeekableFile(b"%PDF-1.4 invoice payload")
    mocked.add(responses.POST, f"{API_URL}/packs/123/fiscal_documents", status=429)

    with pytest.raises(MeliAPIError) as exc_info:
        client.request(
            "POST",
            "/packs/123/fiscal_documents",
            files={"fiscal_document": upload},
        )

    assert exc_info.value.status_code == 429
    assert len(mocked.calls) == 1
    assert sleeps == []


def test_refresh_is_retried_on_429_only(client, sleeps):
    """The refresh POST is retried on 429 and succeeds."""
    with responses.RequestsMock(assert_all_requests_are_fired=True) as mocked:
        mocked.add(responses.POST, f"{API_URL}/oauth/token", status=429)
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

        token = client.refresh_token("TG-refresh-1")

        assert token["access_token"] == "APP_USR-new"
        assert len(mocked.calls) == 2
    assert sleeps == [0.5]


def test_refresh_is_not_retried_on_503(client, sleeps):
    """The refresh POST is not retried on 5xx."""
    with responses.RequestsMock(assert_all_requests_are_fired=True) as mocked:
        mocked.add(
            responses.POST,
            f"{API_URL}/oauth/token",
            status=503,
            json={"message": "down"},
        )

        with pytest.raises(MeliTokenExpiredError):
            client.refresh_token("TG-refresh-1")

        assert len(mocked.calls) == 1
    assert sleeps == []


def test_retry_is_logged_without_secrets(client, mocked, sleeps, caplog):
    """The retry log keeps the path and drops the query string and headers."""
    caplog.set_level(logging.WARNING, logger="meli_sdk")
    mocked.add(responses.GET, f"{API_URL}/users/me", status=429)
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me?access_token=leak")

    records = [record for record in caplog.records if record.name == "meli_sdk"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "1/3" in message
    assert "429" in message
    assert "leak" not in message
    assert "Bearer" not in message
    assert all("leak" not in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_retries": -1},
        {"max_retries": True},
        {"max_retries": 1.5},
        {"backoff_factor": -1},
        {"backoff_factor": float("nan")},
        {"max_backoff": 0},
        {"max_backoff": float("inf")},
    ],
)
def test_invalid_retry_settings_raise_value_error(storage, sleeps, kwargs):
    """Invalid retry settings are rejected when the client is built."""
    with pytest.raises(ValueError):
        make_client(storage, sleeps, **kwargs)
