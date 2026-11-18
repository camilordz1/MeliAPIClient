import io
import json
import os
from typing import List, Union

from .exceptions import MeliAPIError
from .models import (
    ListingPrice,
    UploadedPicture,
    ValidationResult,
    _format_price,
    parse_listing_price,
    parse_uploaded_picture,
    parse_validation_result,
)
from .pictures import (
    JPEG_MAGIC,
    MAX_UPLOAD_BYTES,
    PNG_MAGIC,
    read_picture_source,
    to_jpeg_bytes,
)


def seller_package_attributes(
    height_cm: int, width_cm: int, length_cm: int, weight_g: int
) -> list:
    """Return the SELLER_PACKAGE_* attributes for user-products sellers."""
    values = (height_cm, width_cm, length_cm, weight_g)
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                "package dimensions and weight must be positive integers"
            )

    height, width, length, weight = values
    return [
        {"id": "SELLER_PACKAGE_HEIGHT", "value_name": f"{height} cm"},
        {"id": "SELLER_PACKAGE_WIDTH", "value_name": f"{width} cm"},
        {"id": "SELLER_PACKAGE_LENGTH", "value_name": f"{length} cm"},
        {"id": "SELLER_PACKAGE_WEIGHT", "value_name": f"{weight} g"},
    ]


class Items:
    """Clase para interactuar con los recursos de Publicaciones de Productos (Items) de
    Mercado Libre."""

    def __init__(self, client) -> None:
        self.client = client

    def create(self, data: dict) -> dict:
        """Crea/publica un nuevo producto en Mercado Libre."""
        if isinstance(data, dict) and "title" in data and "family_name" in data:
            raise ValueError("title and family_name cannot be sent together")
        return self.client.request("POST", "/items", json=data)

    def validate(self, data: dict) -> ValidationResult:
        """Validate a listing payload without creating it."""
        try:
            self.client.request("POST", "/items/validate", json=data)
        except MeliAPIError as exc:
            if exc.status_code != 400:
                raise
            try:
                payload = json.loads(exc.response_text)
            except (TypeError, ValueError):
                raise
            return parse_validation_result(400, payload)
        return parse_validation_result(204, None)

    def is_user_product_seller(self, user_id: int = None) -> bool:
        """Return True when the seller has the user_product_seller tag."""
        path = f"/users/{user_id}" if user_id is not None else "/users/me"
        user = self.client.request("GET", path)
        tags = user.get("tags") if isinstance(user, dict) else None
        return isinstance(tags, list) and "user_product_seller" in tags

    def get(self, item_id: str) -> dict:
        """Obtiene la información de un producto por su ID."""
        return self.client.request("GET", f"/items/{item_id}")

    def upload_picture(
        self, source, *, filename: str = None, convert="auto"
    ) -> UploadedPicture:
        """Upload a picture and return it.

        ``convert="auto"`` uploads a JPEG or PNG up to 10 MB as-is and converts anything else to
        JPEG; it does not upscale a small picture. Use ``convert=True`` for pictures under 500 px.
        """
        if convert == "auto":
            mode = "auto"
        elif convert is True:
            mode = True
        elif convert is False:
            mode = False
        else:
            raise ValueError('convert must be "auto", True or False')

        data, hint = read_picture_source(source)
        name = filename or hint or "picture"
        is_jpeg = data.startswith(JPEG_MAGIC)
        is_png = data.startswith(PNG_MAGIC)
        allowed = (is_jpeg or is_png) and len(data) <= MAX_UPLOAD_BYTES

        if mode is False and not allowed:
            raise ValueError(
                "only JPEG or PNG pictures up to 10 MB can be uploaded without conversion"
            )

        if mode is True or (mode == "auto" and not allowed):
            data = to_jpeg_bytes(data)
            is_jpeg, is_png = True, False

        extension = "jpg" if is_jpeg else "png"
        mime = "image/jpeg" if is_jpeg else "image/png"
        stem = os.path.splitext(name)[0] or "picture"
        upload_name = f"{stem}.{extension}"

        files = {"file": (upload_name, io.BytesIO(data), mime)}
        payload = self.client.request(
            "POST", "/pictures/items/upload", files=files
        )
        return parse_uploaded_picture(payload)

    def add_picture(self, item_id: str, picture_id: str) -> dict:
        """Link an uploaded picture to an item."""
        if not isinstance(picture_id, str) or not picture_id.strip():
            raise ValueError("picture_id must be a non-empty string")

        return self.client.request(
            "POST", f"/items/{item_id}/pictures", json={"id": picture_id}
        )

    def get_description(self, item_id: str) -> dict:
        """Return the raw description payload of an item."""
        return self.client.request("GET", f"/items/{item_id}/description")

    def set_description(self, item_id: str, plain_text: str) -> dict:
        """Set or update the plain-text description of an item."""
        if not isinstance(plain_text, str) or not plain_text.strip():
            raise ValueError("plain_text must be a non-empty string")

        body = {"plain_text": plain_text}
        try:
            return self.client.request(
                "PUT",
                f"/items/{item_id}/description",
                params={"api_version": 2},
                json=body,
            )
        except MeliAPIError as exc:
            if exc.status_code != 404:
                raise

        return self.client.request("POST", f"/items/{item_id}/description", json=body)

    def update_description(self, item_id: str, plain_text: str) -> dict:
        """Alias of set_description."""
        return self.set_description(item_id, plain_text)

    def update(self, item_id: str, data: dict) -> dict:
        """Actualiza atributos específicos de un producto."""
        return self.client.request("PUT", f"/items/{item_id}", json=data)

    def update_price(self, item_id: str, price: float) -> dict:
        """Método de conveniencia para actualizar el precio de un producto."""
        return self.update(item_id, {"price": price})

    def update_stock(self, item_id: str, available_quantity: int) -> dict:
        """Método de conveniencia para actualizar el stock/cantidad disponible de un producto."""
        return self.update(item_id, {"available_quantity": available_quantity})

    def get_listing_prices(
        self,
        price,
        *,
        category_id: str = None,
        site_id: str = "MCO",
        currency_id: str = None,
        logistic_type: str = None,
        shipping_mode: str = None,
        billable_weight: int = None,
    ) -> list:
        """Return the listing price options for a price, always as a list."""
        params = {"price": _format_price(price)}
        self._add_listing_filters(
            params,
            category_id=category_id,
            currency_id=currency_id,
            logistic_type=logistic_type,
            shipping_mode=shipping_mode,
            billable_weight=billable_weight,
        )

        response = self.client.request(
            "GET", f"/sites/{site_id}/listing_prices", params=params
        )
        if isinstance(response, dict):
            return [parse_listing_price(response)]
        return [parse_listing_price(entry) for entry in response]

    def get_listing_price(
        self,
        price,
        listing_type_id: str,
        *,
        category_id: str = None,
        site_id: str = "MCO",
        currency_id: str = None,
        logistic_type: str = None,
        shipping_mode: str = None,
        billable_weight: int = None,
    ) -> ListingPrice:
        """Return the listing price for one listing type."""
        params = {
            "price": _format_price(price),
            "listing_type_id": listing_type_id,
        }
        self._add_listing_filters(
            params,
            category_id=category_id,
            currency_id=currency_id,
            logistic_type=logistic_type,
            shipping_mode=shipping_mode,
            billable_weight=billable_weight,
        )

        response = self.client.request(
            "GET", f"/sites/{site_id}/listing_prices", params=params
        )
        if isinstance(response, dict):
            return parse_listing_price(response)

        for entry in response:
            if isinstance(entry, dict) and entry.get("listing_type_id") == listing_type_id:
                return parse_listing_price(entry)

        raise MeliAPIError(
            message=f"No listing price found for listing type {listing_type_id!r}",
            status_code=200,
            response_text=str(response),
        )

    @staticmethod
    def _add_listing_filters(
        params: dict,
        *,
        category_id,
        currency_id,
        logistic_type,
        shipping_mode,
        billable_weight,
    ) -> None:
        """Add the optional listing price filters to the query params."""
        if category_id is not None:
            params["category_id"] = category_id
        if currency_id is not None:
            params["currency_id"] = currency_id
        if logistic_type is not None:
            params["logistic_type"] = logistic_type
        if shipping_mode is not None:
            params["shipping_mode"] = shipping_mode
        if billable_weight is not None:
            params["billable_weight"] = billable_weight

    def search(
        self,
        seller_id: int = None,
        offset: int = 0,
        limit: int = 50,
        extra_params: dict = None,
    ) -> dict:
        """Busca y lista los IDs de publicaciones de un vendedor."""
        if seller_id is None:
            token_data = self.client.token_storage.load_token()
            seller_id = token_data.get("user_id")
            if not seller_id:
                raise ValueError("seller_id es requerido o no se pudo obtener del token activo.")

        params = {"offset": offset, "limit": limit}
        if extra_params:
            params.update(extra_params)

        return self.client.request("GET", f"/users/{seller_id}/items/search", params=params)

    def iter_all(
        self,
        seller_id: int = None,
        *,
        page_size: int = 100,
        extra_params: dict = None,
    ):
        """Yield the seller's item IDs using scan mode, in API order.

        This yields IDs; use ``get_many`` to fetch the item details. The scan ``scroll_id``
        expires after 5 minutes, so consume the generator without long pauses.

        ``page_size`` must be an int between 1 and 100 and ``extra_params`` must not contain
        ``offset``, ``limit``, ``search_type`` or ``scroll_id``; both are validated on the first
        ``next()``.
        """
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 100
        ):
            raise ValueError("page_size must be an int between 1 and 100")

        pagination_keys = {"offset", "limit", "search_type", "scroll_id"}
        if extra_params and pagination_keys.intersection(extra_params):
            raise ValueError(
                "extra_params must not contain 'offset', 'limit', 'search_type' or 'scroll_id'"
            )

        if seller_id is None:
            token_data = self.client.token_storage.load_token()
            seller_id = token_data.get("user_id")
            if not seller_id:
                raise ValueError(
                    "seller_id es requerido o no se pudo obtener del token activo."
                )

        url = f"/users/{seller_id}/items/search"
        params = {"search_type": "scan", "limit": page_size}
        if extra_params:
            params.update(extra_params)

        scroll_id = None
        while True:
            current = dict(params)
            if scroll_id is not None:
                current["scroll_id"] = scroll_id

            page = self.client.request("GET", url, params=current)
            results = page.get("results") or []

            for item_id in results:
                yield item_id

            scroll_id = page.get("scroll_id")
            if not results or not scroll_id:
                return

    @staticmethod
    def _normalize_item_ids(item_ids) -> list:
        """Normalize ids to trimmed strings and deduplicate in first-seen order."""
        if isinstance(item_ids, str):
            item_ids = [item_ids]
        elif isinstance(item_ids, (bytes, bytearray)) or not hasattr(item_ids, "__iter__"):
            raise TypeError("item_ids must be a string or an iterable of ids")

        normalized = []
        seen = set()
        for item_id in item_ids:
            value = str(item_id).strip()
            if not value:
                raise ValueError("item ids must not be empty")
            if value not in seen:
                seen.add(value)
                normalized.append(value)
        return normalized

    @staticmethod
    def _normalize_attributes(attributes):
        """Return a comma-separated attribute list that always includes id."""
        if attributes is None:
            return None

        if isinstance(attributes, str):
            names = attributes.split(",")
        elif isinstance(attributes, (bytes, bytearray)) or not hasattr(attributes, "__iter__"):
            raise TypeError("attributes must be a string or an iterable of names")
        else:
            names = attributes

        cleaned = []
        for name in names:
            value = str(name).strip()
            if value and value not in cleaned:
                cleaned.append(value)

        if not cleaned:
            raise ValueError("attributes must contain at least one name")
        if "id" not in cleaned:
            cleaned.insert(0, "id")
        return ",".join(cleaned)

    def get_many(self, item_ids, *, attributes=None, include_errors: bool = False) -> list:
        """Fetch several items through the multiget endpoint, in batches of 20."""
        unique_ids = self._normalize_item_ids(item_ids)
        if not unique_ids:
            return []

        attributes_param = self._normalize_attributes(attributes)

        results = []
        for start in range(0, len(unique_ids), 20):
            batch = unique_ids[start : start + 20]
            params = {"ids": ",".join(batch)}
            if attributes_param is not None:
                params["attributes"] = attributes_param

            response = self.client.request("GET", "/items", params=params)
            if not isinstance(response, list):
                raise MeliAPIError(
                    message="Unexpected non-list response from the items multiget",
                    status_code=200,
                    response_text=str(response),
                )

            if include_errors:
                results.extend(response)
                continue

            # The API may return entries in another order; match them by body id.
            entries_by_id = {}
            for entry in response:
                if entry.get("code") != 200:
                    continue
                body = entry.get("body")
                if isinstance(body, dict):
                    entries_by_id[body.get("id")] = body
            for item_id in batch:
                body = entries_by_id.get(item_id)
                if body is not None:
                    results.append(body)

        return results

    def _format_ids(self, item_ids: Union[str, List[str]]) -> str:
        """Formatea una lista o cadena de IDs de items en un formato separado por comas."""
        if isinstance(item_ids, list):
            return ",".join(map(str, item_ids))
        return str(item_ids)

    def get_visits(
        self,
        item_ids: Union[str, List[str]],
        date_from: str = None,
        date_to: str = None,
    ) -> dict:
        """
        Obtiene las visitas acumuladas de uno o varios productos en un periodo de fechas.
        Rango de fechas en formato ISO 8601 (ej. '2026-06-01T00:00:00.000-00:00').
        """
        ids_str = self._format_ids(item_ids)
        params = {"ids": ids_str}

        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        return self.client.request("GET", "/items/visits", params=params)

    def get_visits_window(
        self,
        item_ids: Union[str, List[str]],
        last: int = 5,
        unit: str = "day",
    ) -> dict:
        """
        Obtiene visitas usando una ventana de tiempo móvil (ej. últimas 5 horas o días).
        - unit: 'day' o 'hour'
        """
        ids_str = self._format_ids(item_ids)
        params = {"ids": ids_str, "last": last, "unit": unit}

        return self.client.request("GET", "/items/visits/time_window", params=params)

    def get_user_items_visits(
        self,
        seller_id: int = None,
        date_from: str = None,
        date_to: str = None,
    ) -> dict:
        """Obtiene estadísticas agregadas de visitas a nivel usuario/vendedor."""
        if seller_id is None:
            token_data = self.client.token_storage.load_token()
            seller_id = token_data.get("user_id")
            if not seller_id:
                raise ValueError("seller_id es requerido o no se pudo obtener del token activo.")

        params = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        return self.client.request("GET", f"/users/{seller_id}/items_visits", params=params)
