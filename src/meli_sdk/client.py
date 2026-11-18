import time

import requests

from .exceptions import MeliAPIError, MeliConnectionError, MeliTokenExpiredError
from .storage import TokenStorage


class MeliClient:
    """Cliente central de la API de Mercado Libre."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_storage: TokenStorage,
        api_url: str = "https://api.mercadolibre.com",
        token_buffer_seconds: int = 300,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_storage = token_storage
        self.api_url = api_url.rstrip("/")
        self.token_buffer_seconds = token_buffer_seconds

        # Recursos (Lazy imports or direct instantiations to avoid circular dependencies)
        from .bills import Bills
        from .items import Items
        from .metrics import Metrics
        from .orders import Orders
        from .shipments import Shipments

        self.orders = Orders(self)
        self.bills = Bills(self)
        self.shipments = Shipments(self)
        self.items = Items(self)
        self.metrics = Metrics(self)

    def request(self, method: str, path: str, **kwargs) -> dict:
        """
        Realiza una petición HTTP a la API de Mercado Libre,
        asegurando primero que el token de acceso sea válido.
        """
        # Asegurar token de acceso válido
        access_token = self.ensure_token_valid()

        # Configurar URL completa
        url = path if path.startswith("http") else f"{self.api_url}{path}"

        # Configurar cabeceras
        headers = kwargs.pop("headers", {})
        headers.update({
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "format-new": "true",
        })

        try:
            response = requests.request(method, url, headers=headers, **kwargs)
        except requests.RequestException as e:
            raise MeliConnectionError(f"Error de conexión con la API de Mercado Libre: {e}") from e

        # Manejar respuestas con errores
        if response.status_code >= 400:
            error_data = {}
            try:
                error_data = response.json()
            except ValueError:
                pass

            message = error_data.get("message") or error_data.get("error") or response.text
            error_code = error_data.get("error") or error_data.get("code")

            raise MeliAPIError(
                message=f"API Error: {message}",
                status_code=response.status_code,
                error_code=error_code,
                response_text=response.text,
            )

        # Retornar parsed JSON o response vacío si no hay contenido
        if response.status_code == 204 or not response.text:
            return {}

        try:
            return response.json()
        except ValueError as e:
            raise MeliAPIError(
                message=f"No se pudo decodificar JSON de la respuesta: {e}",
                status_code=response.status_code,
                response_text=response.text,
            ) from e

    def ensure_token_valid(self) -> str:
        """
        Verifica el token actual. Si está expirado o próximo a expirar,
        inicia la renovación automática y actualiza el almacenamiento.
        Retorna el access_token válido.
        """
        token_data = self.token_storage.load_token()

        if not token_data:
            raise MeliTokenExpiredError("No hay un token almacenado. Debe autenticarse primero.")

        access_token = token_data.get("access_token")
        refresh_token_str = token_data.get("refresh_token")
        expires_at = token_data.get("expires_at")

        # Si el token no tiene fecha de expiración calculada, intentamos calcularla o refrescar
        now = time.time()

        # Si expires_at no está o faltan menos de buffer_seconds para expirar
        is_expired = (
            not expires_at
            or not access_token
            or now >= (expires_at - self.token_buffer_seconds)
        )

        if is_expired:
            if not refresh_token_str:
                raise MeliTokenExpiredError(
                    "El access token ha expirado y no hay un refresh token disponible."
                )

            # Renovar token
            new_token_data = self.refresh_token(refresh_token_str)
            return new_token_data["access_token"]

        return access_token

    def refresh_token(self, refresh_token_str: str) -> dict:
        """Solicita un nuevo token de acceso usando el token de refresco."""
        url = f"{self.api_url}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token_str,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = requests.post(url, data=payload, headers=headers)
        except requests.RequestException as e:
            raise MeliConnectionError(f"Error al conectar para renovar el token: {e}") from e

        if response.status_code >= 400:
            error_data = {}
            try:
                error_data = response.json()
            except ValueError:
                pass

            message = error_data.get("message") or error_data.get("error") or response.text
            raise MeliTokenExpiredError(f"Fallo al renovar el token: {message}")

        token_response = response.json()

        # Enriquecer respuesta con marcas de tiempo calculadas locales en segundos UTC
        now = time.time()
        token_response["created_at"] = now
        token_response["expires_at"] = now + token_response.get("expires_in", 21600)

        # Guardar en almacenamiento
        self.token_storage.save_token(token_response)

        return token_response
