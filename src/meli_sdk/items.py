from typing import List, Union

from .exceptions import MeliAPIError


class Items:
    """Clase para interactuar con los recursos de Publicaciones de Productos (Items) de
    Mercado Libre."""

    def __init__(self, client) -> None:
        self.client = client

    def create(self, data: dict) -> dict:
        """Crea/publica un nuevo producto en Mercado Libre."""
        return self.client.request("POST", "/items", json=data)

    def get(self, item_id: str) -> dict:
        """Obtiene la información de un producto por su ID."""
        return self.client.request("GET", f"/items/{item_id}")

    def update(self, item_id: str, data: dict) -> dict:
        """Actualiza atributos específicos de un producto."""
        return self.client.request("PUT", f"/items/{item_id}", json=data)

    def update_price(self, item_id: str, price: float) -> dict:
        """Método de conveniencia para actualizar el precio de un producto."""
        return self.update(item_id, {"price": price})

    def update_stock(self, item_id: str, available_quantity: int) -> dict:
        """Método de conveniencia para actualizar el stock/cantidad disponible de un producto."""
        return self.update(item_id, {"available_quantity": available_quantity})

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

    def get_many(self, item_ids, *, attributes=None, include_errors: bool = False) -> list:
        """Fetch several items through the multiget endpoint, in batches of 20."""
        unique_ids = list(dict.fromkeys(item_ids))
        if not unique_ids:
            return []

        results = []
        for start in range(0, len(unique_ids), 20):
            batch = unique_ids[start : start + 20]
            params = {"ids": ",".join(str(item_id) for item_id in batch)}
            if attributes is not None:
                if isinstance(attributes, str):
                    params["attributes"] = attributes
                else:
                    params["attributes"] = ",".join(attributes)

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
