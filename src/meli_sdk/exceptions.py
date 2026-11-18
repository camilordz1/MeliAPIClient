class MeliError(Exception):
    """Clase base para todas las excepciones de Meli SDK."""
    pass


class MeliAPIError(MeliError):
    """Excepción para errores devueltos por la API de Mercado Libre."""

    def __init__(self, message: str, status_code: int = None, error_code: str = None, response_text: str = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.response_text = response_text

    def __str__(self) -> str:
        code_str = f" [{self.error_code}]" if self.error_code else ""
        status_str = f" (Status: {self.status_code})" if self.status_code else ""
        return f"{super().__str__()}{code_str}{status_str}"


class MeliTokenExpiredError(MeliError):
    """Excepción lanzada cuando el refresh token ha expirado o ya no es válido."""
    pass


class MeliConnectionError(MeliError):
    """Excepción lanzada por fallos de red o de conexión."""
    pass
