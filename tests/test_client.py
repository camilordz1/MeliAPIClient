import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from meli_sdk.client import MeliClient
from meli_sdk.exceptions import MeliAPIError
from meli_sdk.storage import MemoryTokenStorage

API_URL = "https://api.mercadolibre.com"


@pytest.fixture
def client_storage() -> MemoryTokenStorage:
    """Return the legacy in-memory token used by these tests."""
    now = time.time()
    return MemoryTokenStorage({
        "access_token": "mock_access_token",
        "refresh_token": "mock_refresh_token",
        "expires_in": 21600,
        "created_at": now,
        "expires_at": now + 21600,
        "user_id": 12345,
    })


@pytest.fixture
def mock_client(client_storage):
    """Return a MeliClient wired to the legacy fixture storage."""
    return MeliClient(
        client_id="client_123",
        client_secret="secret_abc",
        token_storage=client_storage,
    )


def query_params(call) -> dict:
    """Return the query string of a mocked request as a flat dict."""
    parsed = urlparse(call.request.url)
    return {key: values[0] for key, values in parse_qs(parsed.query).items()}


def test_request_successful(mock_client, mocked) -> None:
    mocked.add(responses.GET, f"{API_URL}/test-endpoint", json={"status": "ok"})

    res = mock_client.request("GET", "/test-endpoint")

    assert res == {"status": "ok"}
    assert len(mocked.calls) == 1
    # Verificar que se mandaron las cabeceras requeridas
    headers = mocked.calls[0].request.headers
    assert headers["Authorization"] == "Bearer mock_access_token"
    assert headers["format-new"] == "true"


def test_request_api_error(mock_client, mocked) -> None:
    mocked.add(
        responses.GET,
        f"{API_URL}/test-endpoint",
        status=400,
        json={"message": "Bad Request", "error": "invalid_param"},
    )

    with pytest.raises(MeliAPIError) as exc_info:
        mock_client.request("GET", "/test-endpoint")

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "invalid_param"


def test_auto_token_refresh(mock_client, client_storage, mocked) -> None:
    # Hacer que el token expire restándole tiempo
    token_data = client_storage.load_token()
    token_data["expires_at"] = time.time() - 10  # expirado hace 10s
    client_storage.save_token(token_data)

    # Mockear respuesta del refresh token
    mocked.add(
        responses.POST,
        f"{API_URL}/oauth/token",
        json={
            "access_token": "new_access_token_789",
            "refresh_token": "new_refresh_token_xyz",
            "expires_in": 21600,
            "user_id": 12345,
        },
    )

    # Mockear petición final
    mocked.add(responses.GET, f"{API_URL}/orders/123", json={"data": "refreshed"})

    res = mock_client.request("GET", "/orders/123")

    assert res == {"data": "refreshed"}

    # Verificar que se llamó a refrescar y luego a la petición con el nuevo token
    refresh_calls = [call for call in mocked.calls if call.request.method == "POST"]
    assert len(refresh_calls) == 1
    get_call = next(call for call in mocked.calls if call.request.method == "GET")
    assert get_call.request.headers["Authorization"] == "Bearer new_access_token_789"

    # Verificar que el storage se actualizó
    updated_token = client_storage.load_token()
    assert updated_token["access_token"] == "new_access_token_789"
    assert updated_token["refresh_token"] == "new_refresh_token_xyz"


def test_items_resource(mock_client, mocked) -> None:
    mocked.add(
        responses.PUT,
        f"{API_URL}/items/MLA111",
        json={"id": "MLA111", "price": 150.0},
    )

    # 1. Test update price
    mock_client.items.update_price("MLA111", 150.0)

    call = mocked.calls[-1].request
    assert call.method == "PUT"
    assert call.url == f"{API_URL}/items/MLA111"
    assert json.loads(call.body) == {"price": 150.0}


def test_metrics_resource(mock_client, mocked) -> None:
    # Mock para get_item_reviews
    mocked.add(
        responses.GET,
        f"{API_URL}/reviews/item/MLA111",
        json={"reviews": [{"rating": 5, "comment": "Excellent"}]},
    )

    reviews = mock_client.metrics.get_item_reviews("MLA111", limit=10)
    assert reviews["reviews"][0]["comment"] == "Excellent"
    call = mocked.calls[-1].request
    assert call.method == "GET"
    assert call.url.split("?")[0] == f"{API_URL}/reviews/item/MLA111"
    assert query_params(mocked.calls[-1]) == {"limit": "10", "offset": "0"}

    # Mock para get_trends
    mocked.add(
        responses.GET,
        f"{API_URL}/sites/MCO/trends/search",
        json=[{"keyword": "iphone", "position": 1}],
    )

    trends = mock_client.metrics.get_trends("MCO", category_id="MCO1430")
    assert trends[0]["keyword"] == "iphone"
    call = mocked.calls[-1].request
    assert call.method == "GET"
    assert call.url.split("?")[0] == f"{API_URL}/sites/MCO/trends/search"
    assert query_params(mocked.calls[-1]) == {"category": "MCO1430"}

    # Mock para get_questions
    mocked.add(
        responses.GET,
        f"{API_URL}/questions/search",
        json={"questions": [{"id": 999, "text": "Stock?"}]},
    )

    questions = mock_client.metrics.get_questions(
        seller_id=12345, item_id="MLA111", status="unanswered"
    )
    assert questions["questions"][0]["text"] == "Stock?"
    call = mocked.calls[-1].request
    assert call.method == "GET"
    assert call.url.split("?")[0] == f"{API_URL}/questions/search"
    assert query_params(mocked.calls[-1]) == {
        "seller_id": "12345",
        "api_version": "4",
        "limit": "50",
        "offset": "0",
        "item": "MLA111",
        "status": "unanswered",
    }
