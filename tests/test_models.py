import json
from decimal import Decimal
from pathlib import Path

import pytest

from meli_sdk.models import (
    Address,
    BillingInfo,
    ListingPrice,
    ShipmentCosts,
    ShipmentInfo,
    ShippingQuote,
    ValidationResult,
    parse_billing_info,
    parse_listing_price,
    parse_shipment,
    parse_shipment_costs,
    parse_shipping_quote,
    parse_validation_result,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_new_person():
    """The new billing endpoint shape parses every field."""
    info = parse_billing_info(load("billing_info_new_person.json"), source="billing-info")

    assert isinstance(info, BillingInfo)
    assert info.doc_type == "CC"
    assert info.doc_number == "1020304050"
    assert info.name == "Ana"
    assert info.last_name == "Gomez"
    assert info.cust_type == "CO"
    assert info.taxpayer_type is None
    assert info.source == "billing-info"
    assert info.full_name == "Ana Gomez"
    assert info.is_business is False
    assert info.address == Address(
        street_name="Calle Falsa",
        street_number="123",
        address_line="Calle Falsa 123",
        neighborhood="Centro",
        city="Bogota",
        state="Bogota D.C.",
        state_code="DC",
        zip_code=None,
        country_id="CO",
        comment="Apto 101",
    )


def test_parse_new_business():
    """A legal entity keeps the company name and reports is_business."""
    info = parse_billing_info(load("billing_info_new_business.json"), source="billing-info")

    assert info.name == "Facturas Felices SAS"
    assert info.last_name is None
    assert info.full_name == "Facturas Felices SAS"
    assert info.is_business is True
    assert info.taxpayer_type == "Responsable de IVA"
    assert info.address.zip_code == "050001"
    assert info.address.state == "Antioquia"
    assert info.address.state_code == "ANT"


def test_parse_missing_optional_fields_are_none():
    """Missing zip_code and taxes parse as None."""
    info = parse_billing_info(load("billing_info_new_person.json"), source="billing-info")

    assert info.address.zip_code is None
    assert info.taxpayer_type is None


def test_parse_null_fields_while_processing():
    """Null identification fields are tolerated while a document is processing."""
    payload = load("billing_info_new_person.json")
    payload["buyer"]["billing_info"]["identification"] = {"type": None, "number": None}

    info = parse_billing_info(payload, source="billing-info")

    assert info.doc_type is None
    assert info.doc_number is None


def test_parse_legacy_v1_person():
    """The legacy v1 additional_info list is mapped field by field."""
    info = parse_billing_info(load("billing_info_legacy_v1.json"), source="legacy-v1")

    assert info.source == "legacy-v1"
    assert info.name == "Carlos"
    assert info.last_name == "Perez"
    assert info.full_name == "Carlos Perez"
    assert info.doc_type == "CC"
    assert info.doc_number == "1020304050"
    assert info.cust_type is None
    assert info.taxpayer_type == "Persona natural"
    assert info.address.street_name == "Carrera 7"
    assert info.address.street_number == "45-10"
    assert info.address.address_line == "Carrera 7 45-10"
    assert info.address.city == "Bogota"
    assert info.address.state == "Cundinamarca"
    assert info.address.zip_code == "110111"
    assert info.address.comment == "Oficina 201"
    assert info.is_business is False


def test_parse_legacy_v1_company_name_wins():
    """A company name replaces the person name and clears last_name."""
    payload = load("billing_info_legacy_v1.json")
    for entry in payload["billing_info"]["additional_info"]:
        if entry["type"] == "BUSINESS_NAME":
            entry["value"] = "Compania Falsa SAS"

    info = parse_billing_info(payload, source="legacy-v1")

    assert info.name == "Compania Falsa SAS"
    assert info.last_name is None


@pytest.mark.parametrize(
    "key",
    [
        "DOC_NUMBER",
        "TAXPAYER_ID",
        "IDENTIFICATION_NUMBER",
        "CITIZEN_ID",
        "FEDERAL_TAX_ID",
        "NATIONAL_REGISTRATION_NUMBER",
        "ID",
    ],
)
def test_parse_legacy_v1_doc_number_key_priority(key):
    """Every key in the doc number chain is accepted."""
    payload = {
        "billing_info": {"additional_info": [{"type": key, "value": "DOC-1"}]}
    }

    assert parse_billing_info(payload, source="legacy-v1").doc_number == "DOC-1"


def test_parse_returns_none_for_unknown_payload():
    """A payload without a known shape returns None."""
    assert parse_billing_info({"foo": "bar"}, source="billing-info") is None
    assert parse_billing_info({}, source="legacy-v1") is None


def test_doc_type_is_uppercased_and_stripped():
    """The document type code is normalized."""
    info = parse_billing_info(load("billing_info_new_business.json"), source="billing-info")

    assert info.doc_type == "NIT"


def test_repr_hides_raw():
    """repr does not dump the raw payload."""
    info = parse_billing_info(load("billing_info_new_person.json"), source="billing-info")

    text = repr(info)

    assert "raw" not in text
    assert "BUYER-1" not in text
    assert "1020304050" in text


def test_parse_shipment():
    """The shipment payload is normalized, including money and the address."""
    info = parse_shipment(load("shipment.json"))

    assert isinstance(info, ShipmentInfo)
    assert info.id == 4028374928
    assert info.status == "shipped"
    assert info.substatus == "in_transit"
    assert info.mode == "me2"
    assert info.logistic_type == "drop_off"
    assert info.tracking_number == "TRACK-123"
    assert info.shipping_cost == Decimal("8900")
    assert info.list_cost == Decimal("9900")
    assert info.currency_id == "COP"
    assert info.receiver_name == "Ana Gomez"
    assert info.receiver_phone == "3001234567"
    assert info.address.address_line == "Calle Falsa 123, Apto 101"
    assert info.address.street_name == "Calle Falsa"
    assert info.address.street_number == "123"
    assert info.address.neighborhood == "Centro"
    assert info.address.city == "Bogota"
    assert info.address.state == "Bogota D.C."
    assert info.address.state_code == "DC"
    assert info.address.zip_code == "110111"
    assert info.address.country_id == "CO"
    assert info.address.comment == "Apto 101"


def test_parse_shipment_cost_falls_back_and_defaults():
    """The shipping cost falls back to the top-level cost and then to zero."""
    with_top_level = {"id": 1, "cost": "7000", "receiver_address": {}}
    assert parse_shipment(with_top_level).shipping_cost == Decimal("7000")

    without_cost = {"id": 2, "receiver_address": {}}
    info = parse_shipment(without_cost)
    assert info.shipping_cost == Decimal("0")
    assert info.list_cost is None
    assert info.currency_id is None


def test_shipment_address_line_built_from_street():
    """Without address_line, it is built from street name and number."""
    payload = {
        "id": 3,
        "receiver_address": {"street_name": "Calle Falsa", "street_number": "123"},
    }

    assert parse_shipment(payload).address.address_line == "Calle Falsa 123"


def test_parse_legacy_v1_falls_back_to_billing_name():
    """Without a company or person name, billing_info.name is used."""
    payload = {
        "billing_info": {
            "name": "Empresa Sin Documento",
            "additional_info": [
                {"type": "DOC_NUMBER", "value": "DOC-1"},
                {"type": "FIRST_NAME", "value": ""},
                {"type": "LAST_NAME", "value": ""},
            ],
        }
    }

    info = parse_billing_info(payload, source="legacy-v1")

    assert info.name == "Empresa Sin Documento"
    assert info.last_name is None


def test_parse_legacy_v1_person_name_wins_over_billing_name():
    """FIRST_NAME/LAST_NAME win over the billing_info.name fallback."""
    payload = {
        "billing_info": {
            "name": "Billing Name",
            "additional_info": [
                {"type": "FIRST_NAME", "value": "Carlos"},
                {"type": "LAST_NAME", "value": "Perez"},
            ],
        }
    }

    info = parse_billing_info(payload, source="legacy-v1")

    assert info.name == "Carlos"
    assert info.last_name == "Perez"


def test_parse_listing_price():
    """A listing price entry is normalized with Decimal money."""
    info = parse_listing_price(load("listing_price.json"))

    assert isinstance(info, ListingPrice)
    assert info.listing_type_id == "gold_special"
    assert info.listing_type_name == "Oro Especial"
    assert info.currency_id == "COP"
    assert info.sale_fee_amount == Decimal("11000")
    assert info.percentage_fee == Decimal("11.0")
    assert info.fixed_fee == Decimal("0")
    assert info.listing_fee_amount == Decimal("0")
    assert info.listing_exposure == "high"
    assert info.requires_picture is True


def test_parse_listing_price_tolerates_missing_details():
    """Missing amounts default to zero and missing details to None."""
    info = parse_listing_price({"listing_type_id": "free"})

    assert info.sale_fee_amount == Decimal("0")
    assert info.listing_fee_amount == Decimal("0")
    assert info.percentage_fee is None
    assert info.fixed_fee is None
    assert info.requires_picture is None


def test_parse_shipping_quote():
    """A free-shipping quote is normalized."""
    quote = parse_shipping_quote(load("free_shipping_quote.json"))

    assert isinstance(quote, ShippingQuote)
    assert quote.list_cost == Decimal("8900")
    assert quote.currency_id == "COP"
    assert quote.billable_weight == 500


def test_parse_shipping_quote_missing_coverage_defaults_zero():
    """A quote without coverage defaults the cost to zero."""
    quote = parse_shipping_quote({})

    assert quote.list_cost == Decimal("0")
    assert quote.currency_id is None
    assert quote.billable_weight is None


def test_parse_shipment_costs():
    """Shipment costs sum the senders and expose the convenience properties."""
    costs = parse_shipment_costs(load("shipment_costs.json"))

    assert isinstance(costs, ShipmentCosts)
    assert costs.gross_amount == Decimal("8900")
    assert costs.buyer_cost == Decimal("5900")
    assert costs.seller_cost == Decimal("3000")
    assert costs.buyer_paid_shipping is True
    assert costs.seller_was_charged is True


def test_parse_shipment_costs_without_senders():
    """Without senders the seller was not charged."""
    costs = parse_shipment_costs({"gross_amount": 100, "receiver": {"cost": 100}})

    assert costs.seller_cost == Decimal("0")
    assert costs.seller_was_charged is False
    assert costs.buyer_paid_shipping is True


def test_parse_validation_result_204_is_valid():
    """A 204 with no body is valid and has no causes."""
    result = parse_validation_result(204, None)

    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.errors == ()
    assert result.warnings == ()


def test_parse_validation_result_warnings_only_is_valid():
    """A 400 with only warnings means the listing is valid."""
    result = parse_validation_result(400, load("validation_warnings_only.json"))

    assert result.valid is True
    assert result.errors == ()
    assert len(result.warnings) == 2
    assert result.warnings[0].code == "shipping.lost_me1_by_user"
    assert result.warnings[1].code == "item.shipping.mandatory_free_shipping"


def test_parse_validation_result_with_error_is_invalid():
    """Errors and warnings are split, and any error makes it invalid."""
    result = parse_validation_result(400, load("validation_with_error.json"))

    assert result.valid is False
    assert len(result.errors) == 1
    assert len(result.warnings) == 1
    assert result.errors[0].code == "item.attribute.invalid"
    assert result.errors[0].references == ("attributes",)


def test_parse_validation_result_invalid_fields_shape():
    """The cause-less body.invalid_fields shape yields one synthesized error."""
    result = parse_validation_result(400, load("validation_invalid_fields.json"))

    assert result.valid is False
    assert len(result.errors) == 1
    error = result.errors[0]
    assert error.type == "error"
    assert error.code == "body.invalid_fields"
    assert error.message == "The fields [title] are invalid for requested call."


def test_parse_validation_result_unknown_type_counts_as_error():
    """A cause with an unknown type fails closed."""
    payload = {
        "cause": [
            {
                "department": "items",
                "cause_id": 3001,
                "type": "info",
                "code": "something.new",
                "references": [],
                "message": "Unknown severity",
            }
        ]
    }

    result = parse_validation_result(400, payload)

    assert result.valid is False
    assert len(result.errors) == 1


@pytest.mark.parametrize("payload", [None, {}, {"cause": []}])
def test_parse_validation_result_empty_400_is_invalid(payload):
    """A 400 without causes fails closed with a synthesized error."""
    result = parse_validation_result(400, payload)

    assert result.valid is False
    assert len(result.errors) == 1
    assert result.errors[0].code == "validation.unknown"
