import json
import os
from typing import Callable, Optional


class TokenStorage:
    """Clase base abstracta (interfaz) para el almacenamiento y recuperación de tokens."""

    def load_token(self) -> dict:
        """Carga y devuelve los datos del token actual (ej. access_token, refresh_token)."""
        raise NotImplementedError("Debe implementar el método load_token.")

    def save_token(self, token_data: dict) -> None:
        """Guarda la información actualizada del token."""
        raise NotImplementedError("Debe implementar el método save_token.")


class FileTokenStorage(TokenStorage):
    """Almacena el token en un archivo JSON local. Admite múltiples sesiones usando rutas diferentes."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load_token(self) -> dict:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def save_token(self, token_data: dict) -> None:
        # Crear directorios padres si no existen
        dir_name = os.path.dirname(self.file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
            
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)


class MemoryTokenStorage(TokenStorage):
    """Guarda el token únicamente en memoria RAM. Útil para scripts efímeros y testing."""

    def __init__(self, initial_token: Optional[dict] = None) -> None:
        self.token = initial_token or {}

    def load_token(self) -> dict:
        return self.token

    def save_token(self, token_data: dict) -> None:
        self.token = token_data


class CallbackTokenStorage(TokenStorage):
    """
    Guarda y carga el token delegando en callbacks definidos por el usuario.
    Ideal para bases de datos relacionales u ORMs (SQLAlchemy, Django, Redis, etc.).
    """

    def __init__(self, load_callback: Callable[[], dict], save_callback: Callable[[dict], None]) -> None:
        self.load_callback = load_callback
        self.save_callback = save_callback

    def load_token(self) -> dict:
        return self.load_callback() or {}

    def save_token(self, token_data: dict) -> None:
        self.save_callback(token_data)
