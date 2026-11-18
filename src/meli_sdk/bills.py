import io
import os
from typing import Union

from .actions import Actions
from .exceptions import MeliAPIError

DEFAULT_FILENAME = "factura.pdf"
PDF_MAGIC = b"%PDF-"


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
        except MeliAPIError as e:
            if e.status_code == 404:
                return False
            raise

        documents = response.get("fiscal_documents") if isinstance(response, dict) else None
        return isinstance(documents, list) and bool(documents)

    def upload_fiscal_document(
        self,
        pack_id: Union[int, str],
        document,
        *,
        filename: str = None,
    ) -> dict:
        """Sube un documento fiscal (factura PDF) para un paquete.

        ``document`` puede ser una ruta, ``bytes``/``bytearray`` o un objeto de archivo binario.
        """
        filename, fileobj, owns_file = self._prepare_fiscal_document(document, filename)
        try:
            files = {"fiscal_document": (filename, fileobj, "application/pdf")}
            return self.client.request(
                "POST", f"/packs/{pack_id}/fiscal_documents", files=files
            )
        finally:
            if owns_file:
                fileobj.close()

    def _prepare_fiscal_document(self, document, filename):
        """Return (filename, file object, owns_file) after validating the PDF."""
        if isinstance(document, (str, os.PathLike)):
            fileobj = open(document, "rb")
            try:
                self._check_pdf(fileobj)
            except Exception:
                fileobj.close()
                raise
            default_name = os.path.basename(os.fspath(document))
            return filename or default_name, fileobj, True

        if isinstance(document, (bytes, bytearray)):
            if not document:
                raise ValueError("fiscal document is empty")
            if bytes(document[:5]) != PDF_MAGIC:
                raise ValueError("fiscal document must be a PDF")
            return filename or DEFAULT_FILENAME, io.BytesIO(bytes(document)), True

        if hasattr(document, "read"):
            self._check_pdf_file_object(document)
            name = getattr(document, "name", "")
            default_name = os.path.basename(name) if isinstance(name, str) and name else ""
            return filename or default_name or DEFAULT_FILENAME, document, False

        raise TypeError("document must be a path, bytes or a binary file object")

    @staticmethod
    def _check_pdf(fileobj) -> None:
        """Validate the PDF signature of a seekable file and rewind it."""
        header = fileobj.read(5)
        if not header:
            raise ValueError("fiscal document is empty")
        if header != PDF_MAGIC:
            raise ValueError("fiscal document must be a PDF")
        fileobj.seek(0)

    @staticmethod
    def _check_pdf_file_object(document) -> None:
        """Validate the PDF signature of a caller file object when it is seekable."""
        seek = getattr(document, "seek", None)
        seekable = getattr(document, "seekable", None)
        if seek is None or (callable(seekable) and not seekable()):
            return

        header = document.read(5)
        document.seek(0)
        if not header:
            raise ValueError("fiscal document is empty")
        if header != PDF_MAGIC:
            raise ValueError("fiscal document must be a PDF")


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
