from calendar import monthrange
from datetime import datetime
from typing import Union

from .actions import Actions


class Orders:
    """Clase moderna para interactuar con el recurso de Órdenes de Mercado Libre (Composición)."""

    def __init__(self, client) -> None:
        self.client = client

    def date(
        self, year: int = None, month: int = None, start: int = None, end: int = None
    ) -> dict:
        """Calcula el rango de fecha para las búsquedas de órdenes."""
        dt = datetime.now()

        if year is not None and month is not None:
            dt = datetime(year, month, 1 if start is None else start)

        if start is not None:
            start_str = str(start).zfill(2)
        else:
            start_str = "01"

        if end is not None:
            end_str = str(end).zfill(2)
        else:
            end_val = monthrange(int(dt.strftime("%Y")), int(dt.strftime("%m")))[1]
            end_str = str(end_val).zfill(2)

        start_date = dt.strftime(f"%Y-%m-{start_str}T00:00:00.000-00:00")
        end_date = dt.strftime(f"%Y-%m-{end_str}T23:59:59.000-00:00")

        return {
            "start": start_date,
            "end": end_date,
            "year": int(dt.strftime("%Y")),
            "month": str(dt.strftime("%b")),
        }

    def search(
        self,
        seller_id: int = None,
        offset: int = 0,
        limit: int = 50,
        year: int = None,
        month: int = None,
    ) -> dict:
        """
        Busca órdenes del vendedor en un periodo de tiempo.
        Si no se proporciona seller_id, se obtiene del token activo de Mercado Libre.
        """
        if seller_id is None:
            token_data = self.client.token_storage.load_token()
            seller_id = token_data.get("user_id")
            if not seller_id:
                raise ValueError("seller_id es requerido o no se pudo obtener del token activo.")

        # Obtener rango de fecha
        date_range = self.date(year, month)

        params = {
            "seller": seller_id,
            "order.date_created.from": date_range["start"],
            "order.date_created.to": date_range["end"],
            "limit": limit,
            "sort": "date_asc",
            "offset": offset,
        }

        return self.client.request("GET", "/orders/search", params=params)

    def get(self, order_id: Union[int, str]) -> dict:
        """Obtiene información de una orden específica."""
        return self.client.request("GET", f"/orders/{order_id}")

    def get_pack(self, pack_id: Union[int, str]) -> dict:
        """Obtiene información de un paquete (pack) específico."""
        return self.client.request("GET", f"/packs/{pack_id}")


# --- Capa de Compatibilidad Clásica (Legacy) ---
class Order(Actions):
    """Clase legacy Order compatible con la estructura original."""

    def __init__(self, session) -> None:
        self.session = session

    def date(
        self, year: int = None, month: int = None, start: int = None, end: int = None
    ) -> dict:
        # Reutilizar el cálculo de la clase Orders moderna
        return Orders(self.session.client).date(year, month, start, end)

    def list(self, offset: int = 0, year: int = None, month: int = None) -> dict:
        # Reutilizar la búsqueda moderna pasándole el ID de seller clásico
        seller_id = self.session.ml_user.get("id")
        return Orders(self.session.client).search(
            seller_id=seller_id, offset=offset, year=year, month=month
        )

    def info(self, id: Union[int, str]) -> dict:
        return Orders(self.session.client).get(id)

    def pack(self, order: Union[int, str]) -> dict:
        return Orders(self.session.client).get_pack(order)
