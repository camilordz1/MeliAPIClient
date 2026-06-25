import unittest
from unittest.mock import patch, MagicMock
import os
import json
import tempfile
import time
from MeliAPIClient import Session, Order, Bill, Ship


class TestLegacyCompatibility(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_files = []
        
        # Crear archivos JSON mockeados para emular ml_keys.json y ml_token.json
        self.keys_file = self.create_temp_json({"client_id": "c123", "client_secret": "sabc"})
        self.token_file = self.create_temp_json({
            "access_token": "legacy_acc",
            "refresh_token": "legacy_ref",
            "expires_in": 3600,
            "created_at": time.time(),
            "expires_at": time.time() + 3600,
            "user_id": 99999
        })
        self.user_file = self.create_temp_json({"id": 99999})


    def create_temp_json(self, data: dict) -> str:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp.write(json.dumps(data).encode("utf-8"))
            name = tmp.name
        self.temp_files.append(name)
        return name

    def tearDown(self) -> None:
        for name in self.temp_files:
            if os.path.exists(name):
                os.remove(name)

    @patch("requests.request")
    def test_legacy_session_and_resources(self, mock_req) -> None:
        # Mock de peticiones exitosas
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok", "user_id": 99999}'
        mock_response.json.return_value = {"status": "ok", "user_id": 99999}
        mock_req.return_value = mock_response

        # Inicializar sesión legacy
        session = Session(self.keys_file, self.token_file, self.user_file)
        self.assertEqual(session.ml_user["id"], 99999)
        self.assertTrue(session.headers["Authorization"].startswith("Bearer "))

        # Inicializar recursos legacy
        orders = Order(session)
        bills = Bill(session)
        ship = Ship(session)

        expected_headers = {
            "Authorization": "Bearer legacy_acc",
            "Accept": "application/json",
            "format-new": "true"
        }

        # 1. Probar Order.list (debe llamar a orders/search)
        orders.list(year=2024, month=5)
        mock_req.assert_called_with(
            "GET",
            "https://api.mercadolibre.com/orders/search",
            headers=expected_headers,
            params={
                "seller": 99999,
                "order.date_created.from": unittest.mock.ANY,
                "order.date_created.to": unittest.mock.ANY,
                "limit": 50,
                "sort": "date_asc",
                "offset": 0
            }
        )

        # 2. Probar Order.info (debe llamar a /orders/{id})
        orders.info(123)
        mock_req.assert_called_with(
            "GET",
            "https://api.mercadolibre.com/orders/123",
            headers=expected_headers,
        )

        # 3. Probar Bill.info
        bills.info(123)
        mock_req.assert_called_with(
            "GET",
            "https://api.mercadolibre.com/orders/123/billing_info",
            headers=expected_headers,
        )

        # 4. Probar Ship.info
        ship.info(456)
        mock_req.assert_called_with(
            "GET",
            "https://api.mercadolibre.com/shipments/456",
            headers=expected_headers,
        )


if __name__ == "__main__":
    unittest.main()

