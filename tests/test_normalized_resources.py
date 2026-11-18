import json
from decimal import Decimal
from pathlib import Path

import pytest
import responses

from meli_sdk.exceptions import MeliAPIError
from meli_sdk.models import BillingInfo, ShipmentInfo

API_URL = "https://api.mercadolibre.com"
FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def order_without_billing_id() -> dict:
    """Return the order fixture with the billing reference removed."""
    order = load("order_with_billing_id.json")
    order["buyer"].pop("billing_info", None)
    return order


def test_get_normalized_uses_new_endpoint(client, mocked):
    """The billing id from the order is used against the new endpoint."""
    mocked.add(responses.GET, f"{API_URL}/orders/1", json=load("order_with_billing_id.json"))
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/billing-info/MCO/BI-0001",
        json=load("billing_info_new_person.json"),
    )

    info = client.bills.get_normalized(1)

    assert isinstance(info, BillingInfo)
    assert info.source == "billing-info"
    assert info.doc_number == "1020304050"
    assert len(mocked.calls) == 2


def test_get_normalized_with_given_order_skips_order_call(client, mocked):
    """Passing the order avoids the GET /orders/{id} call."""
    order = load("order_with_billing_id.json")
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/billing-info/MCO/BI-0001",
        json=load("billing_info_new_person.json"),
    )

    info = client.bills.get_normalized(1, order=order)

    assert info.source == "billing-info"
    assert len(mocked.calls) == 1


def test_get_normalized_falls_back_to_legacy_v2_on_404(client, mocked):
    """A 404 on the new endpoint falls back to the v2 legacy endpoint."""
    mocked.add(responses.GET, f"{API_URL}/orders/1", json=load("order_with_billing_id.json"))
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/billing-info/MCO/BI-0001",
        status=404,
        json={"message": "not found"},
    )
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/1/billing_info",
        json=load("billing_info_new_person.json"),
        match=[responses.matchers.header_matcher({"x-version": "2"})],
    )

    info = client.bills.get_normalized(1)

    assert info.source == "legacy-v2"
    assert len(mocked.calls) == 3


def test_get_normalized_without_billing_id_uses_legacy(client, mocked):
    """Without a billing id the legacy endpoint is used directly."""
    mocked.add(responses.GET, f"{API_URL}/orders/1", json=order_without_billing_id())
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/1/billing_info",
        json=load("billing_info_new_person.json"),
        match=[responses.matchers.header_matcher({"x-version": "2"})],
    )

    info = client.bills.get_normalized(1)

    assert info.source == "legacy-v2"
    assert len(mocked.calls) == 2


def test_get_normalized_legacy_v1_payload(client, mocked):
    """A legacy v1 payload is detected and parsed."""
    mocked.add(responses.GET, f"{API_URL}/orders/1", json=load("order_with_billing_id.json"))
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/billing-info/MCO/BI-0001",
        status=404,
        json={"message": "not found"},
    )
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/1/billing_info",
        json=load("billing_info_legacy_v1.json"),
        match=[responses.matchers.header_matcher({"x-version": "2"})],
    )

    info = client.bills.get_normalized(1)

    assert info.source == "legacy-v1"
    assert info.name == "Carlos"


def test_get_normalized_returns_none_when_all_404(client, mocked):
    """When both endpoints return 404 there is no billing info."""
    mocked.add(responses.GET, f"{API_URL}/orders/1", json=load("order_with_billing_id.json"))
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/billing-info/MCO/BI-0001",
        status=404,
        json={"message": "not found"},
    )
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/1/billing_info",
        status=404,
        json={"message": "not found"},
    )

    assert client.bills.get_normalized(1) is None
    assert len(mocked.calls) == 3


def test_get_normalized_propagates_other_errors(client, mocked):
    """A 5xx on the new endpoint is not swallowed."""
    client._sleep = lambda seconds: None
    mocked.add(responses.GET, f"{API_URL}/orders/1", json=load("order_with_billing_id.json"))
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/billing-info/MCO/BI-0001",
        status=500,
        json={"message": "boom"},
    )

    with pytest.raises(MeliAPIError) as exc_info:
        client.bills.get_normalized(1)

    assert exc_info.value.status_code == 500


def test_shipments_get_normalized(client, mocked):
    """Shipments.get_normalized returns a ShipmentInfo."""
    mocked.add(
        responses.GET,
        f"{API_URL}/shipments/4028374928",
        json=load("shipment.json"),
    )

    info = client.shipments.get_normalized(4028374928)

    assert isinstance(info, ShipmentInfo)
    assert info.id == 4028374928
    assert info.shipping_cost == Decimal("8900")
    assert info.address.city == "Bogota"
