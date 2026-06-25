import unittest
import os
import tempfile
from MeliAPIClient.storage import FileTokenStorage, MemoryTokenStorage, CallbackTokenStorage


class TestTokenStorage(unittest.TestCase):

    def test_memory_storage(self) -> None:
        initial = {"access_token": "abc", "refresh_token": "def"}
        storage = MemoryTokenStorage(initial)
        self.assertEqual(storage.load_token(), initial)

        new_data = {"access_token": "new", "refresh_token": "new_ref"}
        storage.save_token(new_data)
        self.assertEqual(storage.load_token(), new_data)

    def test_file_storage(self) -> None:
        # Usar un archivo temporal
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            storage = FileTokenStorage(tmp_path)
            # Archivo vacío o recién creado debe retornar dict vacío
            self.assertEqual(storage.load_token(), {})

            test_token = {"access_token": "123", "refresh_token": "456", "expires_in": 3600}
            storage.save_token(test_token)
            
            # Cargar y verificar
            loaded = storage.load_token()
            self.assertEqual(loaded["access_token"], "123")
            self.assertEqual(loaded["refresh_token"], "456")
            self.assertEqual(loaded["expires_in"], 3600)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_callback_storage(self) -> None:
        db_mock = {"token": {"access_token": "db_token"}}

        def load_cb() -> dict:
            return db_mock["token"]

        def save_cb(new_token: dict) -> None:
            db_mock["token"] = new_token

        storage = CallbackTokenStorage(load_cb, save_cb)
        self.assertEqual(storage.load_token(), {"access_token": "db_token"})

        storage.save_token({"access_token": "db_token_updated"})
        self.assertEqual(db_mock["token"], {"access_token": "db_token_updated"})


if __name__ == "__main__":
    unittest.main()
