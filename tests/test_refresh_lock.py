import contextlib
import json
import threading
import time
from pathlib import Path

import responses

from meli_sdk import CallbackTokenStorage, FileTokenStorage, MemoryTokenStorage, TokenStorage
from meli_sdk.client import MeliClient

API_URL = "https://api.mercadolibre.com"
REFRESH_BODY = {
    "access_token": "APP_USR-new",
    "refresh_token": "TG-refresh-2",
    "expires_in": 21600,
    "user_id": 12345,
}


def expired_token() -> dict:
    """Return a token that expired ten seconds ago."""
    now = time.time()
    return {
        "access_token": "APP_USR-old",
        "refresh_token": "TG-refresh-1",
        "expires_in": 21600,
        "created_at": now - 21600,
        "expires_at": now - 10,
        "user_id": 12345,
    }


def fresh_token(access_token: str = "APP_USR-other") -> dict:
    """Return a valid token for the next six hours."""
    now = time.time()
    return {
        "access_token": access_token,
        "refresh_token": "TG-refresh-9",
        "expires_in": 21600,
        "created_at": now,
        "expires_at": now + 21600,
        "user_id": 12345,
    }


def make_client(token_storage) -> MeliClient:
    """Return a MeliClient with the given storage and no real sleeps."""
    client = MeliClient(
        client_id="cid", client_secret="csecret", token_storage=token_storage
    )
    client._sleep = lambda seconds: None
    return client


def run_threads(workers) -> list:
    """Start every worker at once, join with a timeout and return any errors."""
    barrier = threading.Barrier(len(workers))
    errors = []

    def run(worker):
        barrier.wait(timeout=5)
        try:
            worker()
        except Exception as exc:  # noqa: BLE001 - collected for the assertion
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    return threads, errors


def test_concurrent_requests_refresh_once(mocked):
    """Eight threads with an expired token trigger a single refresh."""
    storage = MemoryTokenStorage(expired_token())
    client = make_client(storage)
    refresh_calls = []
    auth_headers = []

    def refresh_callback(request):
        refresh_calls.append(request)
        time.sleep(0.05)
        return (200, {}, json.dumps(REFRESH_BODY))

    def users_callback(request):
        auth_headers.append(request.headers["Authorization"])
        return (200, {}, json.dumps({"id": 12345}))

    mocked.add_callback(responses.POST, f"{API_URL}/oauth/token", callback=refresh_callback)
    mocked.add_callback(responses.GET, f"{API_URL}/users/me", callback=users_callback)

    workers = [lambda: client.request("GET", "/users/me") for _ in range(8)]
    threads, errors = run_threads(workers)

    assert [thread for thread in threads if thread.is_alive()] == []
    assert errors == []
    assert len(refresh_calls) == 1
    assert len(auth_headers) == 8
    assert set(auth_headers) == {"Bearer APP_USR-new"}


def test_two_clients_sharing_memory_storage_refresh_once(mocked):
    """Two clients over one storage still refresh only once."""
    storage = MemoryTokenStorage(expired_token())
    clients = [make_client(storage), make_client(storage)]
    refresh_calls = []
    auth_headers = []

    def refresh_callback(request):
        refresh_calls.append(request)
        time.sleep(0.05)
        return (200, {}, json.dumps(REFRESH_BODY))

    def users_callback(request):
        auth_headers.append(request.headers["Authorization"])
        return (200, {}, json.dumps({"id": 12345}))

    mocked.add_callback(responses.POST, f"{API_URL}/oauth/token", callback=refresh_callback)
    mocked.add_callback(responses.GET, f"{API_URL}/users/me", callback=users_callback)

    workers = [
        (lambda client=clients[index % 2]: client.request("GET", "/users/me"))
        for index in range(8)
    ]
    threads, errors = run_threads(workers)

    assert [thread for thread in threads if thread.is_alive()] == []
    assert errors == []
    assert len(refresh_calls) == 1
    assert len(auth_headers) == 8
    assert set(auth_headers) == {"Bearer APP_USR-new"}


class FreshOnLockStorage(MemoryTokenStorage):
    """Storage whose lock simulates another process refreshing first."""

    def lock(self):
        storage = self

        class _Lock:
            def __enter__(self):
                storage.save_token(fresh_token("APP_USR-fresh"))

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        return _Lock()


def test_refresh_skipped_when_storage_was_refreshed_meanwhile(mocked):
    """A token refreshed under the lock is reused instead of refreshing again."""
    storage = FreshOnLockStorage(expired_token())
    client = make_client(storage)
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    assert client.request("GET", "/users/me") == {"id": 12345}

    assert [call.request.method for call in mocked.calls] == ["GET"]
    assert mocked.calls[0].request.headers["Authorization"] == "Bearer APP_USR-fresh"


def test_callback_storage_lock_wraps_whole_refresh(mocked):
    """The storage lock spans load, post and save of the refresh."""
    events = []
    state = expired_token()

    def load_token_callback():
        events.append("load")
        return dict(state)

    def save_token_callback(token_data):
        events.append("save")
        state.clear()
        state.update(token_data)

    @contextlib.contextmanager
    def database_lock():
        events.append("lock_enter")
        try:
            yield
        finally:
            events.append("lock_exit")

    storage = CallbackTokenStorage(
        load_token_callback, save_token_callback, lock_callback=database_lock
    )
    client = make_client(storage)

    def refresh_callback(request):
        events.append("post")
        return (200, {}, json.dumps(REFRESH_BODY))

    mocked.add_callback(responses.POST, f"{API_URL}/oauth/token", callback=refresh_callback)
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    client.request("GET", "/users/me")

    start = events.index("lock_enter")
    assert events[start:] == ["lock_enter", "load", "post", "save", "lock_exit"]


def test_callback_storage_without_lock_callback_still_refreshes(mocked):
    """A callback storage without lock_callback keeps working."""
    state = expired_token()
    storage = CallbackTokenStorage(
        lambda: dict(state), lambda token_data: state.update(token_data)
    )
    client = make_client(storage)
    mocked.add(responses.POST, f"{API_URL}/oauth/token", json=REFRESH_BODY)
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    assert client.request("GET", "/users/me") == {"id": 12345}
    assert state["access_token"] == "APP_USR-new"


def test_file_storage_shares_lock_per_path():
    """File storages for the same absolute path share one lock."""
    relative = "ml_token_lock_test.json"
    first = FileTokenStorage(relative)
    second = FileTokenStorage(str(Path(relative).resolve()))
    other = FileTokenStorage("another_token_path.json")

    assert first.lock() is second.lock()
    assert other.lock() is not first.lock()


class MinimalStorage(TokenStorage):
    """Storage that only implements load_token and save_token."""

    def __init__(self, token_data: dict) -> None:
        self.token = dict(token_data)

    def load_token(self) -> dict:
        return self.token

    def save_token(self, token_data: dict) -> None:
        self.token = token_data


def test_custom_storage_without_lock_method_override_works(mocked):
    """A custom storage that does not override lock() still refreshes."""
    storage = MinimalStorage(expired_token())
    client = make_client(storage)
    mocked.add(responses.POST, f"{API_URL}/oauth/token", json=REFRESH_BODY)
    mocked.add(responses.GET, f"{API_URL}/users/me", json={"id": 12345})

    assert client.request("GET", "/users/me") == {"id": 12345}
    assert storage.load_token()["access_token"] == "APP_USR-new"
