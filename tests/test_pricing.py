import json
from decimal import Decimal
from pathlib import Path

import pytest
import responses

from meli_sdk.exceptions import MeliAPIError
from meli_sdk.models import ListingPrice

API_URL = "https://api.mercadolibre.com"
FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> list | dict:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_get_listing_prices_returns_list(client, mocked):
    """Without a listing type the endpoint returns a list of prices."""
    mocked.add(
        responses.GET,
        f"{API_URL}/sites/MCO/listing_prices",
        json=load("listing_prices.json"),
        match=[
            responses.matchers.query_param_matcher(
                {"price": "100000", "category_id": "MCO1430"}
            )
        ],
    )

    prices = client.items.get_listing_prices(100000, category_id="MCO1430")

    assert isinstance(prices, list)
    assert len(prices) == 7
    assert all(isinstance(price, ListingPrice) for price in prices)


def test_get_listing_prices_wraps_single_object(client, mocked):
    """A single-object response is wrapped in a list."""
    mocked.add(
        responses.GET,
        f"{API_URL}/sites/MCO/listing_prices",
        json=load("listing_price.json"),
        match=[responses.matchers.query_param_matcher({"price": "100000"})],
    )

    prices = client.items.get_listing_prices(100000)

    assert len(prices) == 1
    assert prices[0].listing_type_id == "gold_special"


def test_get_listing_price_sends_type_and_returns_one(client, mocked):
    """The single lookup sends listing_type_id and returns one model."""
    mocked.add(
        responses.GET,
        f"{API_URL}/sites/MCO/listing_prices",
        json=load("listing_price.json"),
        match=[
            responses.matchers.query_param_matcher(
                {"price": "100000", "listing_type_id": "gold_special"}
            )
        ],
    )

    price = client.items.get_listing_price(100000, "gold_special")

    assert isinstance(price, ListingPrice)
    assert price.listing_type_id == "gold_special"
    assert price.percentage_fee == Decimal("11.0")


def test_get_listing_price_picks_matching_entry_from_list(client, mocked):
    """When the API answers a list, the matching entry is picked."""
    mocked.add(
        responses.GET,
        f"{API_URL}/sites/MCO/listing_prices",
        json=load("listing_prices.json"),
        match=[
            responses.matchers.query_param_matcher(
                {"price": "100000", "listing_type_id": "gold_pro"}
            )
        ],
    )

    price = client.items.get_listing_price(100000, "gold_pro")

    assert price.listing_type_id == "gold_pro"
    assert price.listing_type_name == "Oro Pro"


def test_get_listing_price_missing_type_raises(client, mocked):
    """A list without the requested listing type raises MeliAPIError."""
    mocked.add(
        responses.GET,
        f"{API_URL}/sites/MCO/listing_prices",
        json=load("listing_prices.json"),
        match=[
            responses.matchers.query_param_matcher(
                {"price": "100000", "listing_type_id": "unknown"}
            )
        ],
    )

    with pytest.raises(MeliAPIError) as exc_info:
        client.items.get_listing_price(100000, "unknown")

    assert exc_info.value.status_code == 200


@pytest.mark.parametrize("price", [0, -1, True, "10", float("nan")])
def test_listing_price_rejects_invalid_price(client, mocked, price):
    """Prices must be positive finite numbers."""
    with pytest.raises(ValueError):
        client.items.get_listing_prices(price)


def test_decimal_price_is_sent_without_exponent(client, mocked):
    """Decimal prices are formatted without exponent notation."""
    mocked.add(
        responses.GET,
        f"{API_URL}/sites/MCO/listing_prices",
        json=load("listing_price.json"),
        match=[responses.matchers.query_param_matcher({"price": "100000"})],
    )

    client.items.get_listing_prices(Decimal("1E+5"))


def test_free_shipping_quote_by_item_id(client, mocked):
    """The seller comes from the token when item_id is used."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/12345/shipping_options/free",
        json=load("free_shipping_quote.json"),
        match=[responses.matchers.query_param_matcher({"item_id": "MCO1"})],
    )

    quote = client.shipments.get_free_shipping_quote(item_id="MCO1")

    assert quote.list_cost == Decimal("8900")
    assert quote.currency_id == "COP"


@pytest.mark.parametrize("dimensions", [(10, 20, 30, 500), "10x20x30,500"])
def test_free_shipping_quote_by_dimensions_tuple_and_string(client, mocked, dimensions):
    """A dimensions quote sends the canonical dimensions, price and listing type."""
    params = {
        "dimensions": "10x20x30,500",
        "item_price": "100000",
        "listing_type_id": "gold_special",
        "mode": "me2",
        "logistic_type": "xd_drop_off",
    }
    mocked.add(
        responses.GET,
        f"{API_URL}/users/12345/shipping_options/free",
        json=load("free_shipping_quote.json"),
        match=[responses.matchers.query_param_matcher(params)],
    )

    quote = client.shipments.get_free_shipping_quote(
        dimensions=dimensions,
        item_price=100000,
        listing_type_id="gold_special",
        logistic_type="xd_drop_off",
    )

    assert quote.billable_weight == 500


def test_free_shipping_quote_requires_exactly_one_source(client, mocked):
    """Neither or both of item_id and dimensions is an error."""
    with pytest.raises(ValueError):
        client.shipments.get_free_shipping_quote()

    with pytest.raises(ValueError):
        client.shipments.get_free_shipping_quote(
            item_id="MCO1", dimensions=(10, 20, 30, 500)
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"listing_type_id": "gold_special"},
        {"item_price": 100000},
    ],
)
def test_free_shipping_quote_dimensions_require_price_and_type(client, mocked, kwargs):
    """A dimensions quote needs item_price and listing_type_id."""
    with pytest.raises(ValueError):
        client.shipments.get_free_shipping_quote(
            dimensions=(10, 20, 30, 500), **kwargs
        )


@pytest.mark.parametrize(
    "dimensions",
    [(10, 20, 30, 0.5), (10, 20, 30), "10x20x30", (0, 20, 30, 500), "10x20x30,0.5"],
)
def test_free_shipping_quote_rejects_bad_dimensions(client, mocked, dimensions):
    """Dimensions must be positive integers, with the weight in grams."""
    with pytest.raises(ValueError):
        client.shipments.get_free_shipping_quote(
            dimensions=dimensions,
            item_price=100000,
            listing_type_id="gold_special",
        )


def test_get_costs(client, mocked):
    """Shipment costs are parsed with the buyer and seller amounts."""
    mocked.add(
        responses.GET,
        f"{API_URL}/shipments/1/costs",
        json=load("shipment_costs.json"),
    )

    costs = client.shipments.get_costs(1)

    assert costs.buyer_cost == Decimal("5900")
    assert costs.seller_cost == Decimal("3000")
    assert costs.buyer_paid_shipping is True
    assert costs.seller_was_charged is True
