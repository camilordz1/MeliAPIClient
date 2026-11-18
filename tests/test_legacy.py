import json
import os
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlparse

import responses

from meli_sdk import Bill, Order, Session, Ship

API_URL = "https://api.mercadolibre.com"


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

    def assert_legacy_headers(self, headers) -> None:
        self.assertEqual(headers["Authorization"], "Bearer legacy_acc")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["format-new"], "true")

    def test_legacy_session_and_resources(self) -> None:
        with responses.RequestsMock(assert_all_requests_are_fired=True) as mocked:
            mocked.add(responses.GET, f"{API_URL}/orders/search", json={"status": "ok"})
            mocked.add(responses.GET, f"{API_URL}/orders/123", json={"status": "ok"})
            mocked.add(
                responses.GET, f"{API_URL}/orders/123/billing_info", json={"status": "ok"}
            )
            mocked.add(responses.GET, f"{API_URL}/shipments/456", json={"status": "ok"})

            # Inicializar sesión legacy
            session = Session(self.keys_file, self.token_file, self.user_file)
            self.assertEqual(session.ml_user["id"], 99999)
            self.assertTrue(session.headers["Authorization"].startswith("Bearer "))

            # Inicializar recursos legacy
            orders = Order(session)
            bills = Bill(session)
            ship = Ship(session)

            # 1. Probar Order.list (debe llamar a orders/search)
            orders.list(year=2024, month=5)
            search_call = mocked.calls[0].request
            self.assertEqual(search_call.method, "GET")
            self.assertTrue(search_call.url.startswith(f"{API_URL}/orders/search?"))
            params = {
                key: values[0]
                for key, values in parse_qs(urlparse(search_call.url).query).items()
            }
            self.assertEqual(params["seller"], "99999")
            self.assertIn("order.date_created.from", params)
            self.assertIn("order.date_created.to", params)
            self.assertEqual(params["limit"], "50")
            self.assertEqual(params["sort"], "date_asc")
            self.assertEqual(params["offset"], "0")
            self.assert_legacy_headers(search_call.headers)

            # 2. Probar Order.info (debe llamar a /orders/{id})
            orders.info(123)
            info_call = mocked.calls[1].request
            self.assertEqual(info_call.method, "GET")
            self.assertEqual(info_call.url, f"{API_URL}/orders/123")
            self.assert_legacy_headers(info_call.headers)

            # 3. Probar Bill.info
            bills.info(123)
            bill_call = mocked.calls[2].request
            self.assertEqual(bill_call.method, "GET")
            self.assertEqual(bill_call.url, f"{API_URL}/orders/123/billing_info")
            self.assert_legacy_headers(bill_call.headers)

            # 4. Probar Ship.info
            ship.info(456)
            ship_call = mocked.calls[3].request
            self.assertEqual(ship_call.method, "GET")
            self.assertEqual(ship_call.url, f"{API_URL}/shipments/456")
            self.assert_legacy_headers(ship_call.headers)


if __name__ == "__main__":
    unittest.main()
