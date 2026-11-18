class Metrics:
    """Clase para obtener métricas, reputación, tendencias y opiniones en Mercado Libre."""

    def __init__(self, client) -> None:
        self.client = client

    def get_seller_info(self, seller_id: int = None) -> dict:
        """Obtiene la información pública y de rendimiento de un vendedor."""
        if seller_id is None:
            token_data = self.client.token_storage.load_token()
            seller_id = token_data.get("user_id")
            if not seller_id:
                raise ValueError("seller_id es requerido o no se pudo obtener del token activo.")

        return self.client.request("GET", f"/users/{seller_id}")

    def get_seller_reputation(self, seller_id: int = None) -> dict:
        """
        Obtiene exclusivamente las métricas de reputación del vendedor
        (reclamos, envíos con retraso, cancelaciones e historial de color).
        """
        info = self.get_seller_info(seller_id)
        return info.get("seller_reputation", {})

    def get_item_reviews(self, item_id: str, limit: int = 50, offset: int = 0) -> dict:
        """
        Obtiene las reseñas y opiniones de compradores para un ID de producto específico.
        """
        params = {"limit": limit, "offset": offset}
        return self.client.request("GET", f"/reviews/item/{item_id}", params=params)

    def get_trends(self, site_id: str, category_id: str = None) -> list:
        """
        Obtiene las tendencias de palabras clave de búsqueda más populares para un site_id
        (ej. MCO, MLA).
        Si se especifica category_id, filtra por esa categoría específica.
        """
        params = {}
        if category_id:
            params["category"] = category_id

        # El endpoint de tendencias comúnmente devuelve un listado directamente
        response = self.client.request("GET", f"/sites/{site_id}/trends/search", params=params)
        return response if isinstance(response, list) else []

    def get_questions(
        self,
        seller_id: int = None,
        item_id: str = None,
        status: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Busca las preguntas recibidas por un vendedor, filtrando opcionalmente por producto o
        estado.
        Utiliza por defecto la recomendación oficial de api_version=4.
        """
        if seller_id is None:
            token_data = self.client.token_storage.load_token()
            seller_id = token_data.get("user_id")
            if not seller_id:
                raise ValueError("seller_id es requerido o no se pudo obtener del token activo.")

        params = {
            "seller_id": seller_id,
            "api_version": 4,
            "limit": limit,
            "offset": offset,
        }

        if item_id:
            params["item"] = item_id
        if status:
            params["status"] = status

        return self.client.request("GET", "/questions/search", params=params)
