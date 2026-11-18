import re
from typing import Union

from .actions import Actions
from .models import (
    ShipmentCosts,
    ShipmentInfo,
    ShippingQuote,
    _format_price,
    parse_shipment,
    parse_shipment_costs,
    parse_shipping_quote,
)

_DIMENSIONS_PATTERN = re.compile(r"^(\d+)x(\d+)x(\d+),(\d+)$")


def _format_dimensions(dimensions) -> str:
    """Validate dimensions and return ``HxWxL,G`` with the weight in integer grams."""
    if isinstance(dimensions, str):
        match = _DIMENSIONS_PATTERN.fullmatch(dimensions)
        if match is None:
            raise ValueError("dimensions must look like 'HxWxL,G' with integer values")
        values = tuple(int(part) for part in match.groups())
    elif isinstance(dimensions, tuple) and len(dimensions) == 4:
        values = dimensions
    else:
        raise ValueError("dimensions must be a 4-tuple or an 'HxWxL,G' string")

    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                "dimensions must be positive integers "
                "(height, width, length and weight in grams)"
            )

    return f"{values[0]}x{values[1]}x{values[2]},{values[3]}"


class Shipments:
    """Clase moderna para interactuar con el recurso de Envíos (Shipments) de Mercado Libre
    (Composición)."""

    def __init__(self, client) -> None:
        self.client = client

    def get(self, shipment_id: Union[int, str]) -> dict:
        """Obtiene información de un envío específico."""
        return self.client.request("GET", f"/shipments/{shipment_id}")

    def get_normalized(self, shipment_id: Union[int, str]) -> ShipmentInfo:
        """Return a normalized view of the shipment."""
        return parse_shipment(
            self.client.request("GET", f"/shipments/{shipment_id}")
        )

    def get_free_shipping_quote(
        self,
        *,
        item_id: str = None,
        dimensions=None,
        item_price=None,
        listing_type_id: str = None,
        mode: str = "me2",
        logistic_type: str = None,
        free_shipping: bool = None,
        seller_id: int = None,
    ) -> ShippingQuote:
        """Quote free shipping by item id or by dimensions."""
        if (item_id is None) == (dimensions is None):
            raise ValueError("Exactly one of item_id or dimensions is required")

        params = {}
        if item_id is not None:
            params["item_id"] = item_id
        else:
            formatted_dimensions = _format_dimensions(dimensions)
            if item_price is None or listing_type_id is None:
                raise ValueError(
                    "item_price and listing_type_id are required with dimensions"
                )
            params["dimensions"] = formatted_dimensions
            params["item_price"] = _format_price(item_price)
            params["listing_type_id"] = listing_type_id
            params["mode"] = mode
            if logistic_type is not None:
                params["logistic_type"] = logistic_type

        if free_shipping is not None:
            params["free_shipping"] = "true" if free_shipping else "false"

        if seller_id is None:
            token_data = self.client.token_storage.load_token()
            seller_id = token_data.get("user_id")
            if not seller_id:
                raise ValueError(
                    "seller_id es requerido o no se pudo obtener del token activo."
                )

        payload = self.client.request(
            "GET", f"/users/{seller_id}/shipping_options/free", params=params
        )
        return parse_shipping_quote(payload)

    def get_costs(self, shipment_id: Union[int, str]) -> ShipmentCosts:
        """Return the definitive shipment costs for reconciliation."""
        return parse_shipment_costs(
            self.client.request("GET", f"/shipments/{shipment_id}/costs")
        )


# --- Capa de Compatibilidad Clásica (Legacy) ---
class Ship(Actions):
    """Clase legacy Ship compatible con la estructura original."""

    def __init__(self, session) -> None:
        self.session = session

    def info(self, id: Union[int, str]) -> dict:
        return Shipments(self.session.client).get(id)
