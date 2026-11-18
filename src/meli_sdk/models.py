import math
from dataclasses import dataclass, field
from decimal import Decimal

from .exceptions import MeliAPIError


@dataclass(frozen=True)
class Address:
    street_name: str | None = None
    street_number: str | None = None
    address_line: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    state_code: str | None = None
    zip_code: str | None = None
    country_id: str | None = None
    comment: str | None = None


@dataclass(frozen=True)
class BillingInfo:
    doc_type: str | None
    doc_number: str | None
    name: str | None
    last_name: str | None
    cust_type: str | None
    taxpayer_type: str | None
    address: Address
    source: str
    raw: dict = field(repr=False, compare=False)

    @property
    def full_name(self) -> str | None:
        parts = [part for part in (self.name, self.last_name) if part]
        return " ".join(parts) if parts else None

    @property
    def is_business(self) -> bool:
        return self.cust_type == "BU" or self.doc_type == "NIT"


@dataclass(frozen=True)
class ListingPrice:
    listing_type_id: str | None
    listing_type_name: str | None
    currency_id: str | None
    sale_fee_amount: Decimal
    percentage_fee: Decimal | None
    fixed_fee: Decimal | None
    listing_fee_amount: Decimal
    listing_exposure: str | None
    requires_picture: bool | None
    raw: dict = field(repr=False, compare=False)


@dataclass(frozen=True)
class ShippingQuote:
    list_cost: Decimal
    currency_id: str | None
    billable_weight: int | None
    raw: dict = field(repr=False, compare=False)


@dataclass(frozen=True)
class ShipmentCosts:
    gross_amount: Decimal
    buyer_cost: Decimal
    seller_cost: Decimal
    raw: dict = field(repr=False, compare=False)

    @property
    def buyer_paid_shipping(self) -> bool:
        return self.buyer_cost > 0

    @property
    def seller_was_charged(self) -> bool:
        return self.seller_cost > 0


@dataclass(frozen=True)
class ValidationCause:
    type: str | None
    code: str | None
    message: str | None
    department: str | None
    cause_id: int | None
    references: tuple[str, ...]


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[ValidationCause, ...]
    warnings: tuple[ValidationCause, ...]
    raw: dict = field(repr=False, compare=False)


@dataclass(frozen=True)
class UploadedPicture:
    id: str
    max_size: str | None
    secure_url: str | None
    raw: dict = field(repr=False, compare=False)


@dataclass(frozen=True)
class ShipmentInfo:
    id: int | None
    status: str | None
    substatus: str | None
    mode: str | None
    logistic_type: str | None
    tracking_number: str | None
    shipping_cost: Decimal
    list_cost: Decimal | None
    currency_id: str | None
    receiver_name: str | None
    receiver_phone: str | None
    address: Address
    raw: dict = field(repr=False, compare=False)


_V1_DOC_NUMBER_KEYS = (
    "DOC_NUMBER",
    "TAXPAYER_ID",
    "IDENTIFICATION_NUMBER",
    "CITIZEN_ID",
    "FEDERAL_TAX_ID",
    "NATIONAL_REGISTRATION_NUMBER",
    "ID",
)
_V1_DOC_TYPE_KEYS = ("DOC_TYPE", "TAXPAYER_TYPE_ID", "ID_TYPE")
_V1_COMPANY_KEYS = (
    "BUSINESS_NAME",
    "LEGAL_NAME",
    "COMPANY_NAME",
    "CORPORATION_NAME",
    "TAXPAYER_NAME",
    "TRADE_NAME",
)


def _clean(value) -> str | None:
    """Strip a value, turning None and empty strings into None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_dict(value) -> dict:
    """Return a dict payload or an empty dict."""
    return value if isinstance(value, dict) else {}


def _first_value(mapping: dict, keys) -> str | None:
    """Return the first truthy value among the given keys."""
    for key in keys:
        value = mapping.get(key)
        if value:
            return value
    return None


def _to_decimal(value) -> Decimal:
    """Convert a money value to Decimal without going through float."""
    return Decimal(str(value))


def _build_address(
    *,
    street_name=None,
    street_number=None,
    address_line=None,
    neighborhood=None,
    city=None,
    state=None,
    state_code=None,
    zip_code=None,
    country_id=None,
    comment=None,
) -> Address:
    """Normalize an address, building address_line when it is absent."""
    clean_street = _clean(street_name)
    clean_number = _clean(street_number)
    clean_line = _clean(address_line)
    if clean_line is None:
        parts = [part for part in (clean_street, clean_number) if part]
        clean_line = " ".join(parts) or None

    return Address(
        street_name=clean_street,
        street_number=clean_number,
        address_line=clean_line,
        neighborhood=_clean(neighborhood),
        city=_clean(city),
        state=_clean(state),
        state_code=_clean(state_code),
        zip_code=_clean(zip_code),
        country_id=_clean(country_id),
        comment=_clean(comment),
    )


def _parse_billing_v2(billing: dict, source: str, raw: dict) -> BillingInfo:
    """Parse the billing_info object shared by the new endpoint and legacy v2."""
    identification = _as_dict(billing.get("identification"))
    attributes = _as_dict(billing.get("attributes"))
    address = _as_dict(billing.get("address"))
    state = _as_dict(address.get("state"))
    taxes = _as_dict(billing.get("taxes"))
    taxpayer_type = _as_dict(taxes.get("taxpayer_type"))

    doc_type = _clean(identification.get("type"))

    return BillingInfo(
        doc_type=doc_type.upper() if doc_type else None,
        doc_number=_clean(identification.get("number")),
        name=_clean(billing.get("name")),
        last_name=_clean(billing.get("last_name")),
        cust_type=_clean(attributes.get("cust_type")),
        taxpayer_type=_clean(taxpayer_type.get("description")),
        address=_build_address(
            street_name=address.get("street_name"),
            street_number=address.get("street_number"),
            neighborhood=address.get("neighborhood"),
            city=address.get("city_name"),
            state=state.get("name"),
            state_code=state.get("code"),
            zip_code=address.get("zip_code"),
            country_id=address.get("country_id"),
            comment=address.get("comment"),
        ),
        source=source,
        raw=raw,
    )


def _parse_billing_v1(billing: dict, raw: dict) -> BillingInfo:
    """Parse the legacy v1 additional_info type/value list."""
    info = {}
    for entry in billing.get("additional_info") or []:
        if not isinstance(entry, dict):
            continue
        key = _clean(entry.get("type"))
        if key:
            info[key.upper()] = _clean(entry.get("value"))

    doc_number = _first_value(info, _V1_DOC_NUMBER_KEYS) or _clean(
        billing.get("doc_number")
    )
    doc_type = _first_value(info, _V1_DOC_TYPE_KEYS) or _clean(billing.get("doc_type"))

    company_name = _first_value(info, _V1_COMPANY_KEYS)
    if company_name:
        name, last_name = company_name, None
    else:
        name, last_name = info.get("FIRST_NAME"), info.get("LAST_NAME")
        if not name and not last_name:
            name = _clean(billing.get("name"))

    street_name = info.get("STREET_NAME")
    street_number = info.get("STREET_NUMBER")
    address_line = None
    if not street_name and not street_number:
        address_line = _first_value(info, ("COMMENT", "STREET", "ADDRESS"))

    return BillingInfo(
        doc_type=doc_type.upper() if doc_type else None,
        doc_number=doc_number,
        name=name,
        last_name=last_name,
        cust_type=None,
        taxpayer_type=info.get("TAXPAYER_TYPE"),
        address=_build_address(
            street_name=street_name,
            street_number=street_number,
            address_line=address_line,
            city=info.get("CITY_NAME") or info.get("CITY"),
            state=info.get("STATE_NAME") or info.get("STATE"),
            zip_code=info.get("ZIP_CODE") or info.get("POSTAL_CODE"),
            comment=info.get("COMMENT"),
        ),
        source="legacy-v1",
        raw=raw,
    )


def parse_billing_info(payload: dict, *, source: str) -> BillingInfo | None:
    """Parse a billing payload into a normalized BillingInfo.

    Accepts the new/v2 shape (``payload["buyer"]["billing_info"]``) and the legacy v1 shape
    (``payload["billing_info"]["additional_info"]``). Returns None when neither is present.
    """
    if not isinstance(payload, dict):
        return None

    billing = _as_dict(_as_dict(payload.get("buyer")).get("billing_info"))
    if billing:
        return _parse_billing_v2(billing, source, payload)

    legacy = _as_dict(payload.get("billing_info"))
    if legacy.get("additional_info"):
        return _parse_billing_v1(legacy, payload)

    return None


def parse_shipment(payload: dict) -> ShipmentInfo:
    """Parse a shipment payload into a normalized ShipmentInfo."""
    data = _as_dict(payload)
    shipping_option = _as_dict(data.get("shipping_option"))
    receiver = _as_dict(data.get("receiver_address"))
    city = _as_dict(receiver.get("city"))
    state = _as_dict(receiver.get("state"))
    country = _as_dict(receiver.get("country"))
    neighborhood = _as_dict(receiver.get("neighborhood"))

    cost = shipping_option.get("cost")
    if cost is None:
        cost = data.get("cost")
    list_cost = shipping_option.get("list_cost")

    return ShipmentInfo(
        id=data.get("id"),
        status=_clean(data.get("status")),
        substatus=_clean(data.get("substatus")),
        mode=_clean(data.get("mode")),
        logistic_type=_clean(data.get("logistic_type")),
        tracking_number=_clean(data.get("tracking_number")),
        shipping_cost=_to_decimal(cost) if cost is not None else Decimal("0"),
        list_cost=_to_decimal(list_cost) if list_cost is not None else None,
        currency_id=_clean(shipping_option.get("currency_id")),
        receiver_name=_clean(receiver.get("receiver_name")),
        receiver_phone=_clean(receiver.get("receiver_phone")),
        address=_build_address(
            street_name=receiver.get("street_name"),
            street_number=receiver.get("street_number"),
            address_line=receiver.get("address_line"),
            neighborhood=neighborhood.get("name"),
            city=city.get("name"),
            state=state.get("name"),
            state_code=state.get("id"),
            zip_code=receiver.get("zip_code"),
            country_id=country.get("id"),
            comment=receiver.get("comment"),
        ),
        raw=data,
    )


def parse_listing_price(entry: dict) -> ListingPrice:
    """Parse one listing price entry into a ListingPrice."""
    data = _as_dict(entry)
    sale_details = _as_dict(data.get("sale_fee_details"))

    sale_fee = data.get("sale_fee_amount")
    listing_fee = data.get("listing_fee_amount")
    percentage_fee = sale_details.get("percentage_fee")
    fixed_fee = sale_details.get("fixed_fee")

    return ListingPrice(
        listing_type_id=_clean(data.get("listing_type_id")),
        listing_type_name=_clean(data.get("listing_type_name")),
        currency_id=_clean(data.get("currency_id")),
        sale_fee_amount=_to_decimal(sale_fee) if sale_fee is not None else Decimal("0"),
        percentage_fee=(
            _to_decimal(percentage_fee) if percentage_fee is not None else None
        ),
        fixed_fee=_to_decimal(fixed_fee) if fixed_fee is not None else None,
        listing_fee_amount=(
            _to_decimal(listing_fee) if listing_fee is not None else Decimal("0")
        ),
        listing_exposure=_clean(data.get("listing_exposure")),
        requires_picture=data.get("requires_picture"),
        raw=data,
    )


def parse_shipping_quote(payload: dict) -> ShippingQuote:
    """Parse a free-shipping quote into a ShippingQuote."""
    data = _as_dict(payload)
    coverage = _as_dict(_as_dict(data.get("coverage")).get("all_country"))
    list_cost = coverage.get("list_cost")

    return ShippingQuote(
        list_cost=_to_decimal(list_cost) if list_cost is not None else Decimal("0"),
        currency_id=_clean(coverage.get("currency_id")),
        billable_weight=coverage.get("billable_weight"),
        raw=data,
    )


def parse_shipment_costs(payload: dict) -> ShipmentCosts:
    """Parse shipment costs, summing what every sender was charged."""
    data = _as_dict(payload)
    receiver = _as_dict(data.get("receiver"))

    seller_cost = Decimal("0")
    for sender in data.get("senders") or []:
        if isinstance(sender, dict) and sender.get("cost") is not None:
            seller_cost += _to_decimal(sender["cost"])

    gross_amount = data.get("gross_amount")
    buyer_cost = receiver.get("cost")

    return ShipmentCosts(
        gross_amount=_to_decimal(gross_amount) if gross_amount is not None else Decimal("0"),
        buyer_cost=_to_decimal(buyer_cost) if buyer_cost is not None else Decimal("0"),
        seller_cost=seller_cost,
        raw=data,
    )


def _format_price(value) -> str:
    """Validate a positive price and format it without exponent notation."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"price must be a positive number, got {value!r}")

    if isinstance(value, Decimal):
        if not value.is_finite() or value <= 0:
            raise ValueError(f"price must be a positive number, got {value!r}")
        return format(value, "f")

    if isinstance(value, float) and (not math.isfinite(value) or value <= 0):
        raise ValueError(f"price must be a positive number, got {value!r}")

    if value <= 0:
        raise ValueError(f"price must be a positive number, got {value!r}")
    return str(value)


def _parse_validation_cause(entry) -> ValidationCause | None:
    """Parse one validation cause entry."""
    data = _as_dict(entry)
    references = data.get("references") or []
    if not isinstance(references, (list, tuple)):
        references = [references]

    cause = ValidationCause(
        type=_clean(data.get("type")),
        code=_clean(data.get("code")),
        message=_clean(data.get("message")),
        department=_clean(data.get("department")),
        cause_id=data.get("cause_id"),
        references=tuple(str(reference) for reference in references),
    )
    return cause


def parse_validation_result(status_code: int, payload: dict | None) -> ValidationResult:
    """Parse the response of POST /items/validate.

    Warnings do not block the listing; unknown cause types count as errors.
    """
    data = _as_dict(payload)

    if status_code < 400:
        return ValidationResult(valid=True, errors=(), warnings=(), raw=data)

    causes = [
        cause
        for cause in (_parse_validation_cause(entry) for entry in data.get("cause") or [])
        if cause is not None
    ]
    errors = tuple(cause for cause in causes if cause.type != "warning")
    warnings = tuple(cause for cause in causes if cause.type == "warning")

    if not causes:
        message = _clean(data.get("message"))
        error = _clean(data.get("error"))
        if message or error:
            synthesized = ValidationCause(
                type="error",
                code=message,
                message=error,
                department=None,
                cause_id=None,
                references=(),
            )
        else:
            synthesized = ValidationCause(
                type="error",
                code="validation.unknown",
                message="validation failed without causes",
                department=None,
                cause_id=None,
                references=(),
            )
        return ValidationResult(
            valid=False, errors=(synthesized,), warnings=(), raw=data
        )

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings, raw=data)


def parse_uploaded_picture(payload: dict) -> UploadedPicture:
    """Parse a picture upload response into an UploadedPicture."""
    data = _as_dict(payload)
    picture_id = _clean(data.get("id"))
    if not picture_id:
        raise MeliAPIError(
            message="The picture upload response has no id",
            status_code=200,
            response_text=str(data),
        )

    variations = data.get("variations") or []
    secure_url = None
    if variations and isinstance(variations[0], dict):
        secure_url = _clean(variations[0].get("secure_url"))

    return UploadedPicture(
        id=picture_id,
        max_size=_clean(data.get("max_size")),
        secure_url=secure_url,
        raw=data,
    )
