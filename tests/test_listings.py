import json
from pathlib import Path
from unittest.mock import patch

import pytest
import responses

from meli_sdk.exceptions import MeliAPIError
from meli_sdk.items import seller_package_attributes

API_URL = "https://api.mercadolibre.com"
FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_validate_returns_valid_on_204(client, mocked):
    """A 204 means the listing is valid."""
    mocked.add(responses.POST, f"{API_URL}/items/validate", status=204)

    result = client.items.validate({"title": "Producto"})

    assert result.valid is True
    assert result.errors == ()
    assert result.warnings == ()


def test_validate_warnings_only_400_is_valid(client, mocked):
    """A 400 with only warnings means the listing is valid."""
    mocked.add(
        responses.POST,
        f"{API_URL}/items/validate",
        status=400,
        json=load("validation_warnings_only.json"),
    )

    result = client.items.validate({"title": "Producto"})

    assert result.valid is True
    assert result.errors == ()
    assert len(result.warnings) == 2


def test_validate_error_400_is_invalid(client, mocked):
    """A 400 with an error means the listing is invalid."""
    mocked.add(
        responses.POST,
        f"{API_URL}/items/validate",
        status=400,
        json=load("validation_with_error.json"),
    )

    result = client.items.validate({"title": "Producto"})

    assert result.valid is False
    assert len(result.errors) == 1
    assert len(result.warnings) == 1


@pytest.mark.parametrize("status", [401, 500])
def test_validate_propagates_non_400(client, mocked, status):
    """Non-400 errors are not converted into a ValidationResult."""
    client._sleep = lambda seconds: None
    mocked.add(
        responses.POST,
        f"{API_URL}/items/validate",
        status=status,
        json={"message": "no"},
    )
    if status == 401:
        # The client refreshes once and retries on 401 before validate sees the error.
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
        mocked.add(
            responses.POST,
            f"{API_URL}/items/validate",
            status=401,
            json={"message": "no"},
        )

    with pytest.raises(MeliAPIError) as exc_info:
        client.items.validate({"title": "Producto"})

    assert exc_info.value.status_code == status
    if status == 500:
        assert len(mocked.calls) == 1


def test_create_rejects_title_and_family_name_together(client, mocked):
    """The API rejects both fields together, so the SDK does too, before any call."""
    with pytest.raises(ValueError):
        client.items.create({"title": "Producto", "family_name": "Camisetas"})

    assert len(mocked.calls) == 0


def test_create_with_family_name_only_posts(client, mocked):
    """A user-products payload without title is posted as usual."""
    body = {"family_name": "Camisetas"}
    mocked.add(
        responses.POST,
        f"{API_URL}/items",
        json={"id": "MCO1"},
        match=[responses.matchers.json_params_matcher(body)],
    )

    assert client.items.create(body) == {"id": "MCO1"}


def test_is_user_product_seller_true_and_false(client, mocked):
    """The tag decides whether family_name is required."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/me",
        json={"id": 1, "tags": ["user_product_seller"]},
    )
    assert client.items.is_user_product_seller() is True

    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 1, "tags": []})
    assert client.items.is_user_product_seller() is False


def test_is_user_product_seller_with_user_id(client, mocked):
    """An explicit user id uses the users endpoint."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/999",
        json={"id": 999, "tags": ["user_product_seller"]},
    )

    assert client.items.is_user_product_seller(999) is True


def test_set_description_puts_with_api_version(client, mocked):
    """Descriptions are updated with PUT api_version=2."""
    text = "Descripcion de prueba"
    mocked.add(
        responses.PUT,
        f"{API_URL}/items/MCO1/description",
        json={"plain_text": text},
        match=[
            responses.matchers.query_param_matcher({"api_version": "2"}),
            responses.matchers.json_params_matcher({"plain_text": text}),
        ],
    )

    assert client.items.set_description("MCO1", text) == {"plain_text": text}


def test_set_description_falls_back_to_post_on_404(client, mocked):
    """A 404 on PUT means no description yet, so it creates it with POST."""
    text = "Descripcion de prueba"
    mocked.add(
        responses.PUT,
        f"{API_URL}/items/MCO1/description",
        status=404,
        json={"message": "not found"},
    )
    mocked.add(
        responses.POST,
        f"{API_URL}/items/MCO1/description",
        json={"plain_text": text},
        match=[responses.matchers.json_params_matcher({"plain_text": text})],
    )

    assert client.items.set_description("MCO1", text) == {"plain_text": text}
    assert [call.request.method for call in mocked.calls] == ["PUT", "POST"]


def test_set_description_propagates_other_errors(client, mocked):
    """A 400 on PUT is not followed by a POST."""
    mocked.add(
        responses.PUT,
        f"{API_URL}/items/MCO1/description",
        status=400,
        json={"message": "bad"},
    )

    with pytest.raises(MeliAPIError) as exc_info:
        client.items.set_description("MCO1", "texto")

    assert exc_info.value.status_code == 400
    assert len(mocked.calls) == 1


@pytest.mark.parametrize("plain_text", ["", "   ", None, 123])
def test_set_description_rejects_empty(client, mocked, plain_text):
    """The description must be a non-empty string."""
    with pytest.raises(ValueError):
        client.items.set_description("MCO1", plain_text)


def test_update_description_is_alias(client):
    """update_description delegates to set_description."""
    with patch.object(
        type(client.items), "set_description", return_value={"ok": True}
    ) as set_description:
        assert client.items.update_description("MCO1", "hola") == {"ok": True}

    set_description.assert_called_once_with("MCO1", "hola")


def test_get_description(client, mocked):
    """The description is fetched and returned raw."""
    mocked.add(
        responses.GET,
        f"{API_URL}/items/MCO1/description",
        json={"plain_text": "Descripcion"},
    )

    assert client.items.get_description("MCO1") == {"plain_text": "Descripcion"}


def test_seller_package_attributes():
    """The four seller package attributes carry integer units."""
    attributes = seller_package_attributes(10, 20, 30, 500)

    assert attributes == [
        {"id": "SELLER_PACKAGE_HEIGHT", "value_name": "10 cm"},
        {"id": "SELLER_PACKAGE_WIDTH", "value_name": "20 cm"},
        {"id": "SELLER_PACKAGE_LENGTH", "value_name": "30 cm"},
        {"id": "SELLER_PACKAGE_WEIGHT", "value_name": "500 g"},
    ]


@pytest.mark.parametrize("value", [0, -1, 10.0, True, "10"])
def test_seller_package_attributes_rejects(value):
    """Only positive integers are accepted, never floats or bools."""
    with pytest.raises(ValueError):
        seller_package_attributes(value, 20, 30, 500)
