from datetime import datetime
import json
import os
from typing import Union
from dotenv import load_dotenv
from .client import MeliClient
from .storage import FileTokenStorage


class Session:
    """Capa de compatibilidad clásica para la gestión de sesiones y tokens."""

    def __init__(
        self,
        keys: Union[dict, str] = None,
        token: Union[dict, str] = None,
        user: Union[dict, str] = None,
    ) -> None:
        self.headers: dict = {"Authorization": "", "format-new": "true"}

        # Load .env lazily: only the legacy Session depends on environment variables
        if not keys or not token:
            load_dotenv()

        # Si no se proporcionan parámetros, usar las variables de entorno
        self.ml_keys = read(keys) if keys else self.load_env_keys()
        self.ml_token = read(token) if token else self.load_env_token()
        self.ml_user = read(user) if user else {}

        # Determinar el archivo para persistir el token
        token_path = token if isinstance(token, str) and token.endswith(".json") else "ml_token.json"
        
        self.token_storage = FileTokenStorage(token_path)
        
        # Si el token se pasó como un diccionario, o si el archivo no existe, lo inicializamos
        if isinstance(token, dict) or not os.path.exists(token_path):
            self.token_storage.save_token(self.ml_token)

        # Inicializar el cliente moderno internamente
        self.client = MeliClient(
            client_id=self.ml_keys.get("client_id", ""),
            client_secret=self.ml_keys.get("client_secret", ""),
            token_storage=self.token_storage,
        )

        self.access()

    def access(self) -> dict:
        """Actualiza el token de acceso si ha expirado delegando en el cliente moderno."""
        self.client.ensure_token_valid()
        self.ml_token = self.token_storage.load_token()
        self.headers["Authorization"] = f"Bearer {self.ml_token.get('access_token')}"
        return self.ml_token

    def refresh(self) -> dict:
        """Obtiene un nuevo token de acceso usando el refresh token."""
        refresh_token_str = self.ml_token.get("refresh_token")
        if not refresh_token_str:
            raise ValueError("No refresh token available to perform renewal.")
            
        self.ml_token = self.client.refresh_token(refresh_token_str)
        self.headers["Authorization"] = f"Bearer {self.ml_token.get('access_token')}"
        return self.ml_token

    def load_env_keys(self) -> dict:
        """Carga las credenciales de Mercado Libre desde las variables de entorno."""
        return {
            "client_id": os.getenv("ML_CLIENT_ID"),
            "client_secret": os.getenv("ML_CLIENT_SECRET"),
        }

    def load_env_token(self) -> dict:
        """Carga el token desde las variables de entorno."""
        return {
            "access_token": os.getenv("ML_ACCESS_TOKEN"),
            "refresh_token": os.getenv("ML_REFRESH_TOKEN"),
            "date": os.getenv("ML_TOKEN_DATE", datetime.isoformat(datetime.now())),
        }


def read(file_name: Union[dict, str]) -> dict:
    """Lee un archivo JSON o retorna directamente el diccionario proporcionado."""
    if isinstance(file_name, str) and file_name.endswith(".json"):
        if not os.path.exists(file_name):
            return {}
        with open(file_name, "r") as content:
            return json.load(content)
    return file_name
