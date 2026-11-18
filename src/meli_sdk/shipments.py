from typing import Union

from .actions import Actions


class Shipments:
    """Clase moderna para interactuar con el recurso de Envíos (Shipments) de Mercado Libre
    (Composición)."""

    def __init__(self, client) -> None:
        self.client = client

    def get(self, shipment_id: Union[int, str]) -> dict:
        """Obtiene información de un envío específico."""
        return self.client.request("GET", f"/shipments/{shipment_id}")


# --- Capa de Compatibilidad Clásica (Legacy) ---
class Ship(Actions):
    """Clase legacy Ship compatible con la estructura original."""

    def __init__(self, session) -> None:
        self.session = session

    def info(self, id: Union[int, str]) -> dict:
        return Shipments(self.session.client).get(id)
