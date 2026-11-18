import pytest
import requests
import responses

from MeliAPIClient.exceptions import MeliAPIError, MeliConnectionError

API_URL = "https://api.mercadolibre.com"


def test_request_sends_auth_and_default_headers(client, mocked):
    """A request carries the bearer token and the client default headers."""
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    headers = mocked.calls[0].request.headers
    assert headers["Authorization"] == "Bearer APP_USR-valid"
    assert headers["Accept"] == "application/json"
    assert headers["format-new"] == "true"


def test_relative_path_is_joined_to_api_url(client, mocked):
    """A relative path is appended to the configured API base URL."""
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    assert mocked.calls[0].request.url == f"{API_URL}/users/me"


def test_absolute_url_is_used_as_is(client, mocked):
    """An absolute URL bypasses the configured API base URL."""
    absolute_url = "https://other.example.com/resource"
    mocked.add(responses.GET, absolute_url, json={"ok": True})

    client.request("GET", absolute_url)

    assert mocked.calls[0].request.url == absolute_url


def test_caller_headers_are_merged(client, mocked):
    """Caller headers are sent together with the client default headers."""
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me", headers={"X-Test": "1"})

    headers = mocked.calls[0].request.headers
    assert headers["X-Test"] == "1"
    assert headers["Authorization"] == "Bearer APP_USR-valid"


def test_4xx_raises_api_error_with_json_fields(client, mocked):
    """A 4xx JSON response raises MeliAPIError with its status and error code."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/me",
        status=400,
        json={"message": "bad", "error": "validation_error"},
    )

    try:
        client.request("GET", "/users/me")
    except MeliAPIError as exc:
        assert exc.status_code == 400
        assert exc.error_code == "validation_error"
        assert "bad" in str(exc)
    else:
        raise AssertionError("MeliAPIError was not raised")


def test_4xx_non_json_body_uses_text(client, mocked):
    """A 4xx plain-text response falls back to the raw body as the message."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/me",
        status=500,
        body="boom",
        content_type="text/plain",
    )

    try:
        client.request("GET", "/users/me")
    except MeliAPIError as exc:
        assert "boom" in str(exc)
    else:
        raise AssertionError("MeliAPIError was not raised")


def test_204_returns_empty_dict(client, mocked):
    """A 204 No Content response is parsed as an empty dict."""
    mocked.add(responses.GET, f"{API_URL}/users/me", status=204)

    assert client.request("GET", "/users/me") == {}


def test_empty_body_returns_empty_dict(client, mocked):
    """An empty 200 response body is parsed as an empty dict."""
    mocked.add(responses.GET, f"{API_URL}/users/me", status=200, body="")

    assert client.request("GET", "/users/me") == {}


def test_invalid_json_on_200_raises_api_error(client, mocked):
    """An undecodable 200 response raises MeliAPIError."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/me",
        status=200,
        body="{not json",
        content_type="application/json",
    )

    try:
        client.request("GET", "/users/me")
    except MeliAPIError as exc:
        assert exc.status_code == 200
    else:
        raise AssertionError("MeliAPIError was not raised")


def test_connection_error_raises_meli_connection_error(client, mocked):
    """A transport failure is wrapped in MeliConnectionError."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/me",
        body=requests.ConnectionError("x"),
    )

    try:
        client.request("GET", "/users/me")
    except MeliConnectionError:
        pass
    else:
        raise AssertionError("MeliConnectionError was not raised")


@pytest.mark.xfail(
    strict=True, reason="Known bug: no timeout; fixed in F1-01"
)
def test_request_sets_a_timeout(client, mocked):
    """Every HTTP request must carry a timeout."""
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    assert mocked.calls[0].request.req_kwargs.get("timeout") is not None
