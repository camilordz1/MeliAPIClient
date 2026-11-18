import unittest
from unittest.mock import patch, MagicMock
import time
from meli_sdk.client import MeliClient
from meli_sdk.storage import MemoryTokenStorage
from meli_sdk.exceptions import MeliAPIError, MeliTokenExpiredError


class TestMeliClient(unittest.TestCase):

    def setUp(self) -> None:
        self.storage = MemoryTokenStorage({
            "access_token": "mock_access_token",
            "refresh_token": "mock_refresh_token",
            "expires_in": 21600,
            "created_at": time.time(),
            "expires_at": time.time() + 21600,
            "user_id": 12345
        })
        self.client = MeliClient(
            client_id="client_123",
            client_secret="secret_abc",
            token_storage=self.storage
        )

    @patch("requests.request")
    def test_request_successful(self, mock_req) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'
        mock_response.json.return_value = {"status": "ok"}
        mock_req.return_value = mock_response

        res = self.client.request("GET", "/test-endpoint")
        self.assertEqual(res, {"status": "ok"})
        mock_req.assert_called_once()
        # Verificar que se mandaron las cabeceras requeridas
        headers = mock_req.call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer mock_access_token")
        self.assertEqual(headers["format-new"], "true")

    @patch("requests.request")
    def test_request_api_error(self, mock_req) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"message": "Bad Request", "error": "invalid_param"}'
        mock_response.json.return_value = {"message": "Bad Request", "error": "invalid_param"}
        mock_req.return_value = mock_response

        with self.assertRaises(MeliAPIError) as ctx:
            self.client.request("GET", "/test-endpoint")
        
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.error_code, "invalid_param")

    @patch("requests.post")
    @patch("requests.request")
    def test_auto_token_refresh(self, mock_req, mock_post) -> None:
        # Hacer que el token expire restándole tiempo
        token_data = self.storage.load_token()
        token_data["expires_at"] = time.time() - 10  # expirado hace 10s
        self.storage.save_token(token_data)

        # Mockear respuesta del refresh token
        mock_refresh_resp = MagicMock()
        mock_refresh_resp.status_code = 200
        mock_refresh_resp.json.return_value = {
            "access_token": "new_access_token_789",
            "refresh_token": "new_refresh_token_xyz",
            "expires_in": 21600,
            "user_id": 12345
        }
        mock_post.return_value = mock_refresh_resp

        # Mockear petición final
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"data": "refreshed"}'
        mock_resp.json.return_value = {"data": "refreshed"}
        mock_req.return_value = mock_resp

        # Realizar petición
        res = self.client.request("GET", "/orders/123")
        self.assertEqual(res, {"data": "refreshed"})

        # Verificar que se llamó a refrescar y luego a la petición con el nuevo token
        mock_post.assert_called_once()
        headers = mock_req.call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer new_access_token_789")

        # Verificar que el storage se actualizó
        updated_token = self.storage.load_token()
        self.assertEqual(updated_token["access_token"], "new_access_token_789")
        self.assertEqual(updated_token["refresh_token"], "new_refresh_token_xyz")

    @patch("requests.request")
    def test_items_resource(self, mock_req) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "MLA111", "price": 150.0}'
        mock_resp.json.return_value = {"id": "MLA111", "price": 150.0}
        mock_req.return_value = mock_resp

        # 1. Test update price
        self.client.items.update_price("MLA111", 150.0)
        mock_req.assert_called_with(
            "PUT",
            "https://api.mercadolibre.com/items/MLA111",
            headers=unittest.mock.ANY,
            json={"price": 150.0}
        )

    @patch("requests.request")
    def test_metrics_resource(self, mock_req) -> None:
        # Mock para get_item_reviews
        mock_resp_reviews = MagicMock()
        mock_resp_reviews.status_code = 200
        mock_resp_reviews.json.return_value = {"reviews": [{"rating": 5, "comment": "Excellent"}]}
        mock_req.return_value = mock_resp_reviews

        reviews = self.client.metrics.get_item_reviews("MLA111", limit=10)
        self.assertEqual(reviews["reviews"][0]["comment"], "Excellent")
        mock_req.assert_called_with(
            "GET",
            "https://api.mercadolibre.com/reviews/item/MLA111",
            headers=unittest.mock.ANY,
            params={"limit": 10, "offset": 0}
        )

        # Mock para get_trends
        mock_resp_trends = MagicMock()
        mock_resp_trends.status_code = 200
        mock_resp_trends.json.return_value = [{"keyword": "iphone", "position": 1}]
        mock_req.return_value = mock_resp_trends

        trends = self.client.metrics.get_trends("MCO", category_id="MCO1430")
        self.assertEqual(trends[0]["keyword"], "iphone")
        mock_req.assert_called_with(
            "GET",
            "https://api.mercadolibre.com/sites/MCO/trends/search",
            headers=unittest.mock.ANY,
            params={"category": "MCO1430"}
        )

        # Mock para get_questions
        mock_resp_questions = MagicMock()
        mock_resp_questions.status_code = 200
        mock_resp_questions.json.return_value = {"questions": [{"id": 999, "text": "Stock?"}]}
        mock_req.return_value = mock_resp_questions

        questions = self.client.metrics.get_questions(seller_id=12345, item_id="MLA111", status="unanswered")
        self.assertEqual(questions["questions"][0]["text"], "Stock?")
        mock_req.assert_called_with(
            "GET",
            "https://api.mercadolibre.com/questions/search",
            headers=unittest.mock.ANY,
            params={
                "seller_id": 12345,
                "api_version": 4,
                "limit": 50,
                "offset": 0,
                "item": "MLA111",
                "status": "unanswered"
            }
        )


if __name__ == "__main__":
    unittest.main()

