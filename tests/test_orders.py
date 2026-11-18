import json
import time

import pytest
import responses
from freezegun import freeze_time

from meli_sdk import Order, Session

API_URL = "https://api.mercadolibre.com"


def make_legacy_session(tmp_path, user_id: int = 99999) -> Session:
    """Build a legacy Session from temp JSON files with a valid token."""
    now = time.time()
    keys_file = tmp_path / "ml_keys.json"
    keys_file.write_text(json.dumps({"client_id": "cid", "client_secret": "csecret"}))
    token_file = tmp_path / "ml_token.json"
    token_file.write_text(
        json.dumps({
            "access_token": "APP_USR-valid",
            "refresh_token": "TG-refresh-1",
            "expires_in": 21600,
            "created_at": now,
            "expires_at": now + 21600,
            "user_id": user_id,
        })
    )
    user_file = tmp_path / "ml_user.json"
    user_file.write_text(json.dumps({"id": user_id}))
    return Session(str(keys_file), str(token_file), str(user_file))


def test_search_builds_params_for_month(client, mocked):
    """Searching a month builds the seller, date range and pagination params."""
    params = {
        "seller": "12345",
        "order.date_created.from": "2026-02-01T00:00:00.000-05:00",
        "order.date_created.to": "2026-02-28T23:59:59.000-05:00",
        "limit": "50",
        "offset": "0",
        "sort": "date_asc",
    }
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/search",
        json={"results": []},
        match=[responses.matchers.query_param_matcher(params)],
    )

    assert client.orders.search(year=2026, month=2) == {"results": []}


def test_search_without_seller_and_without_user_id_raises_value_error(
    client, storage, mocked
):
    """A missing seller_id and a token without user_id raise ValueError."""
    token = storage.load_token()
    token.pop("user_id")
    storage.save_token(token)

    with pytest.raises(ValueError):
        client.orders.search(year=2026, month=2)


def test_date_range_uses_colombia_offset(client):
    """The Colombia (MCO) date range must end with the -05:00 offset."""
    assert client.orders.date(2026, 2)["start"].endswith("-05:00")


def test_date_custom_offset(client):
    """A custom offset changes the range and its suffix."""
    date_range = client.orders.date(2026, 2, utc_offset="+00:00")

    assert date_range["start"] == "2026-02-01T00:00:00.000+00:00"
    assert date_range["end"] == "2026-02-28T23:59:59.000+00:00"


@pytest.mark.parametrize("utc_offset", ["-5", "05:00", "-25:00", "-05:60", "abc"])
def test_date_rejects_invalid_offset(client, utc_offset):
    """Malformed or out-of-range offsets are rejected."""
    with pytest.raises(ValueError):
        client.orders.date(2026, 2, utc_offset=utc_offset)


@pytest.mark.parametrize("year,month", [(2026, None), (None, 2)])
def test_date_requires_year_and_month_together(client, year, month):
    """Year and month must be given together."""
    with pytest.raises(ValueError, match="year and month must be given together"):
        client.orders.date(year, month)


def test_date_without_year_month_uses_offset_now(client):
    """Without year/month the current month is computed in the seller offset."""
    with freeze_time("2026-03-01T03:00:00Z"):
        date_range = client.orders.date()

    assert date_range["start"] == "2026-02-01T00:00:00.000-05:00"
    assert date_range["end"] == "2026-02-28T23:59:59.000-05:00"
    assert date_range["year"] == 2026
    assert date_range["month"] == "Feb"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start": 0},
        {"end": 32},
        {"start": 10, "end": 5},
        {"end": 29},
    ],
)
def test_date_validates_start_end(client, kwargs):
    """Start and end must be valid days inside the month, in order."""
    with pytest.raises(ValueError):
        client.orders.date(2026, 2, **kwargs)


def test_search_status_sort_and_extra_params(client, mocked):
    """Optional search filters are sent exactly as given."""
    params = {
        "seller": "12345",
        "order.date_created.from": "2026-02-01T00:00:00.000-05:00",
        "order.date_created.to": "2026-02-28T23:59:59.000-05:00",
        "limit": "50",
        "offset": "0",
        "sort": "date_desc",
        "order.status": "paid",
        "foo": "bar",
    }
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/search",
        json={"results": []},
        match=[responses.matchers.query_param_matcher(params)],
    )

    client.orders.search(
        year=2026,
        month=2,
        status="paid",
        sort="date_desc",
        extra_params={"foo": "bar"},
    )


def test_search_rejects_invalid_sort(client, mocked):
    """Only the two documented sort values are accepted."""
    with pytest.raises(ValueError):
        client.orders.search(year=2026, month=2, sort="date_sideways")


def test_get_and_get_pack_paths(client, mocked):
    """get and get_pack hit the order and pack detail endpoints."""
    mocked.add(responses.GET, f"{API_URL}/orders/1", json={"id": 1})
    mocked.add(responses.GET, f"{API_URL}/packs/2", json={"id": 2})

    assert client.orders.get(1) == {"id": 1}
    assert client.orders.get_pack(2) == {"id": 2}


def test_legacy_order_list_uses_colombia_offset(mocked, tmp_path):
    """The legacy Order.list uses the Colombia range too."""
    session = make_legacy_session(tmp_path)
    params = {
        "seller": "99999",
        "order.date_created.from": "2026-02-01T00:00:00.000-05:00",
        "order.date_created.to": "2026-02-28T23:59:59.000-05:00",
        "limit": "50",
        "offset": "0",
        "sort": "date_asc",
    }
    mocked.add(
        responses.GET,
        f"{API_URL}/orders/search",
        json={"results": []},
        match=[responses.matchers.query_param_matcher(params)],
    )

    assert Order(session).list(year=2026, month=2) == {"results": []}
