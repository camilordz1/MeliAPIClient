import re
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Union

from .actions import Actions

DEFAULT_UTC_OFFSET = "-05:00"
_OFFSET_PATTERN = re.compile(r"^([+-])(\d{2}):(\d{2})$")


def _parse_utc_offset(utc_offset: str) -> timezone:
    """Parse a +HH:MM or -HH:MM offset into a fixed timezone."""
    match = _OFFSET_PATTERN.fullmatch(utc_offset) if isinstance(utc_offset, str) else None
    if match is None:
        raise ValueError(
            f"utc_offset must match +HH:MM or -HH:MM, got {utc_offset!r}"
        )

    hours = int(match.group(2))
    minutes = int(match.group(3))
    if hours > 14 or minutes >= 60:
        raise ValueError(
            f"utc_offset must match +HH:MM or -HH:MM, got {utc_offset!r}"
        )

    sign = -1 if match.group(1) == "-" else 1
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


class Orders:
    """Clase moderna para interactuar con el recurso de Órdenes de Mercado Libre (Composición)."""

    def __init__(self, client) -> None:
        self.client = client

    def date(
        self,
        year: int = None,
        month: int = None,
        start: int = None,
        end: int = None,
        *,
        utc_offset: str = DEFAULT_UTC_OFFSET,
    ) -> dict:
        """Calcula el rango de fecha para las búsquedas de órdenes."""
        tz = _parse_utc_offset(utc_offset)

        if (year is None) != (month is None):
            raise ValueError("year and month must be given together")

        if year is None:
            dt = datetime.now(tz)
        else:
            dt = datetime(year, month, 1, tzinfo=tz)

        last_day = monthrange(dt.year, dt.month)[1]
        start_day = 1 if start is None else start
        end_day = last_day if end is None else end

        if not 1 <= start_day <= last_day or not 1 <= end_day <= last_day:
            raise ValueError(f"start and end must be days inside the month (1..{last_day})")
        if start_day > end_day:
            raise ValueError("start must be less than or equal to end")

        start_date = f"{dt:%Y-%m}-{start_day:02d}T00:00:00.000{utc_offset}"
        end_date = f"{dt:%Y-%m}-{end_day:02d}T23:59:59.000{utc_offset}"

        return {
            "start": start_date,
            "end": end_date,
            "year": dt.year,
            "month": dt.strftime("%b"),
        }

    def search(
        self,
        seller_id: int = None,
        offset: int = 0,
        limit: int = 50,
        year: int = None,
        month: int = None,
        *,
        utc_offset: str = DEFAULT_UTC_OFFSET,
        status: str = None,
        sort: str = "date_asc",
        extra_params: dict = None,
    ) -> dict:
        """
        Busca órdenes del vendedor en un periodo de tiempo.
        Si no se proporciona seller_id, se obtiene del token activo de Mercado Libre.
        """
        if sort not in ("date_asc", "date_desc"):
            raise ValueError("sort must be 'date_asc' or 'date_desc'")

        if seller_id is None:
            token_data = self.client.token_storage.load_token()
            seller_id = token_data.get("user_id")
            if not seller_id:
                raise ValueError("seller_id es requerido o no se pudo obtener del token activo.")

        # Obtener rango de fecha
        date_range = self.date(year, month, utc_offset=utc_offset)

        params = {
            "seller": seller_id,
            "order.date_created.from": date_range["start"],
            "order.date_created.to": date_range["end"],
            "limit": limit,
            "sort": sort,
            "offset": offset,
        }
        if status is not None:
            params["order.status"] = status
        if extra_params:
            params.update(extra_params)

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
