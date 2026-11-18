from typing import Union

from .actions import Actions
from .exceptions import MeliAPIError


class Bills:
    """Clase moderna para interactuar con los recursos de Facturación y Documentos Fiscales
    (Composición)."""

    def __init__(self, client) -> None:
        self.client = client

    def get_billing_info(self, order_id: Union[int, str]) -> dict:
        """Obtiene la información de facturación vinculada a una orden."""
        return self.client.request("GET", f"/orders/{order_id}/billing_info")

    def has_fiscal_document(self, pack_id: Union[int, str]) -> bool:
        """Comprueba si un paquete de órdenes tiene un documento fiscal adjunto."""
        try:
            response = self.client.request("GET", f"/packs/{pack_id}/fiscal_documents")
            return bool(response)
        except MeliAPIError as e:
            if e.status_code == 404:
                return False
            raise e

    def upload_fiscal_document(self, pack_id: Union[int, str], file_path: str) -> dict:
        """Sube un documento fiscal (factura) en formato PDF para un paquete."""
        with open(file_path, "rb") as f:
            files = {"fiscal_document": f}
            return self.client.request("POST", f"/packs/{pack_id}/fiscal_documents", files=files)


# --- Capa de Compatibilidad Clásica (Legacy) ---
class Bill(Actions):
    """Clase legacy Bill compatible con la estructura original."""

    def __init__(self, session) -> None:
        self.session = session

    def info(self, id: Union[int, str]) -> dict:
        return Bills(self.session.client).get_billing_info(id)

    def documents(self, pack_id: Union[int, str]) -> bool:
        return Bills(self.session.client).has_fiscal_document(pack_id)

    def upload(self, id: Union[int, str], url_file: str) -> dict:
        return Bills(self.session.client).upload_fiscal_document(id, url_file)
