import json
import requests
from typing import Union, Any, Dict


class Actions:
    """Clase base de conveniencia para las llamadas HTTP de la API clásica (Legacy)."""

    def get(self, url: str, headers: dict, params: dict = None, data: dict = None) -> Union[dict, bool]:
        """Realiza una petición GET clásica, con comprobación y auto-refresco del token."""
        if params is None:
            params = {}
        if data is None:
            data = {}

        # Auto-refresh del token si la instancia hereda y tiene session
        if hasattr(self, "session") and hasattr(self.session, "access"):
            self.session.access()
            headers = self.session.headers

        try:
            response = requests.request("GET", url, headers=headers, params=params, data=data)
        except requests.RequestException:
            return False

        if response.status_code == 404:
            return False

        try:
            return response.json()
        except ValueError:
            # Si no es JSON pero responde OK, o si falla la decodificación
            return {}

    def post(self, url: str, headers: dict, params: dict = None, data: dict = None, file: dict = None, **kwargs) -> Union[dict, None]:
        """Realiza una petición POST clásica. Corrige errores en nombres de parámetros."""
        if params is None:
            params = {}
        if data is None:
            data = {}
        
        # Resolver incompatibilidad de 'fl' vs 'file' en el upload original
        files = file or kwargs.get("fl") or kwargs.get("files")

        # Auto-refresh del token si la instancia hereda y tiene session
        if hasattr(self, "session") and hasattr(self.session, "access"):
            self.session.access()
            headers = self.session.headers

        try:
            response = requests.request("POST", url, headers=headers, params=params, data=data, files=files)
        except requests.RequestException:
            return print("[ERROR] Error de conexión en POST")

        if response.status_code == 404:
            try:
                error_resp = response.json()
            except ValueError:
                error_resp = response.text
            return print("[ERROR] ", error_resp)

        elif response.status_code == 204:
            try:
                resp = response.json()
            except ValueError:
                resp = response.text
            return print(resp)

        try:
            return response.json()
        except ValueError:
            return None

