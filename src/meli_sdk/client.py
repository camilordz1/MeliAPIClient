import logging
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

from .exceptions import MeliAPIError, MeliConnectionError, MeliTokenExpiredError
from .storage import TokenStorage

logger = logging.getLogger("meli_sdk")

RETRYABLE_STATUSES = frozenset({500, 502, 503, 504})
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


def _validate_timeout(timeout):
    """Return a validated timeout, raising ValueError when it is not usable."""
    message = (
        "timeout must be a positive int/float or a (connect, read) tuple of "
        f"positive numbers, got {timeout!r}"
    )

    if isinstance(timeout, bool):
        raise ValueError(message)

    if isinstance(timeout, (int, float)):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(message)
        return timeout

    if isinstance(timeout, tuple) and len(timeout) == 2:
        for value in timeout:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(message)
        return timeout

    raise ValueError(message)


def _validate_max_retries(value):
    """Return a validated max_retries, raising ValueError when it is not usable."""
    message = f"max_retries must be an int >= 0, got {value!r}"
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(message)
    return value


def _validate_backoff_factor(value):
    """Return a validated backoff_factor, raising ValueError when it is not usable."""
    message = f"backoff_factor must be a finite number >= 0, got {value!r}"
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(message)
    return value


def _validate_max_backoff(value):
    """Return a validated max_backoff, raising ValueError when it is not usable."""
    message = f"max_backoff must be a finite number > 0, got {value!r}"
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(message)
    return value


class MeliClient:
    """Cliente central de la API de Mercado Libre."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_storage: TokenStorage,
        api_url: str = "https://api.mercadolibre.com",
        token_buffer_seconds: int = 300,
        *,
        timeout: float | tuple[float, float] = 30.0,
        session: requests.Session | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        max_backoff: float = 60.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_storage = token_storage
        self.api_url = api_url.rstrip("/")
        self.token_buffer_seconds = token_buffer_seconds
        self.timeout = _validate_timeout(timeout)
        self.session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._closed = False
        self.max_retries = _validate_max_retries(max_retries)
        self.backoff_factor = _validate_backoff_factor(backoff_factor)
        self.max_backoff = _validate_max_backoff(max_backoff)
        self._sleep = time.sleep

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

        timeout = kwargs.pop("timeout", self.timeout)

        try:
            response = self._send(method, url, headers=headers, timeout=timeout, **kwargs)
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

    def _send(self, method: str, url: str, **kwargs) -> requests.Response:
        """Send a request and retry the safe subset of transient failures."""
        method_name = method.upper()
        idempotent = method_name in IDEMPOTENT_METHODS
        attempt = 0

        while True:
            try:
                response = self.session.request(method, url, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if (
                    not idempotent
                    or attempt >= self.max_retries
                    or not self._rewind_files(kwargs.get("files"))
                ):
                    raise
                delay = self._backoff_delay(attempt)
                self._log_retry(method_name, url, delay, type(exc).__name__, attempt)
                self._sleep(delay)
                attempt += 1
                continue

            retryable = response.status_code == 429 or (
                response.status_code in RETRYABLE_STATUSES and idempotent
            )
            if (
                retryable
                and attempt < self.max_retries
                and self._rewind_files(kwargs.get("files"))
            ):
                delay = self._retry_delay(response, attempt)
                self._log_retry(method_name, url, delay, response.status_code, attempt)
                self._sleep(delay)
                attempt += 1
                continue

            return response

    def _log_retry(self, method: str, url: str, delay: float, reason, attempt: int) -> None:
        """Log a retry without headers, query strings, tokens or bodies."""
        logger.warning(
            "Retry %d/%d for %s %s in %.2fs (reason: %s)",
            attempt + 1,
            self.max_retries,
            method,
            urlsplit(url).path,
            delay,
            reason,
        )

    def _backoff_delay(self, attempt: int) -> float:
        """Return the exponential backoff delay for an attempt, capped."""
        return min(self.backoff_factor * 2**attempt, self.max_backoff)

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        """Return the delay requested by the response, capped by max_backoff."""
        retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is None:
            return self._backoff_delay(attempt)
        return min(retry_after, self.max_backoff)

    @staticmethod
    def _parse_retry_after(value):
        """Parse a Retry-After header as seconds or as an HTTP-date."""
        if not value:
            return None

        value = value.strip()
        try:
            seconds = float(value)
        except ValueError:
            pass
        else:
            if math.isfinite(seconds) and seconds >= 0:
                return seconds
            return None

        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at is None:
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0)

    def _rewind_files(self, files) -> bool:
        """Rewind the file objects of a request before retrying it."""
        if not files:
            return True

        values = files.values() if hasattr(files, "values") else files
        for value in values:
            fileobj = value[1] if isinstance(value, tuple) and len(value) >= 2 else value
            if not hasattr(fileobj, "read"):
                continue
            if not self._is_seekable(fileobj):
                return False
            fileobj.seek(0)
        return True

    @staticmethod
    def _is_seekable(fileobj) -> bool:
        """Return True when seek(0) can safely rewind a file object."""
        if not hasattr(fileobj, "seek"):
            return False
        seekable = getattr(fileobj, "seekable", None)
        if callable(seekable) and not seekable():
            return False
        return True

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
            response = self._send(
                "POST", url, data=payload, headers=headers, timeout=self.timeout
            )
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

    def close(self) -> None:
        """Close the underlying session when this client owns it."""
        if self._owns_session and not self._closed:
            self.session.close()
            self._closed = True

    def __enter__(self) -> "MeliClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
