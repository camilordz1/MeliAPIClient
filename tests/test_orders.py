import json
import time
from urllib.parse import parse_qs, urlsplit

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
        "order.date_created.to": "2026-02-28T23:59:59.999-05:00",
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
    assert date_range["end"] == "2026-02-28T23:59:59.999+00:00"


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
    assert date_range["end"] == "2026-02-28T23:59:59.999-05:00"
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
        "order.date_created.to": "2026-02-28T23:59:59.999-05:00",
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
        "order.date_created.to": "2026-02-28T23:59:59.999-05:00",
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


def query_params(call) -> dict:
    """Return the query string of a mocked request as a flat dict."""
    parsed = urlsplit(call.request.url)
    return {key: values[0] for key, values in parse_qs(parsed.query).items()}


def page(ids, total):
    """Build a search page body."""
    return {"results": [{"id": order_id} for order_id in ids], "paging": {"total": total}}


def test_iter_all_walks_all_pages(client, mocked):
    """iter_all follows offset, offset+n... until paging.total is reached."""
    first = list(range(1, 51))
    second = list(range(51, 101))
    third = list(range(101, 121))
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page(first, 120))
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page(second, 120))
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page(third, 120))

    orders = list(client.orders.iter_all(year=2026, month=2))

    assert [order["id"] for order in orders] == list(range(1, 121))
    assert len(mocked.calls) == 3
    assert [query_params(call)["offset"] for call in mocked.calls] == ["0", "50", "100"]


def test_iter_all_stops_on_empty_results(client, mocked):
    """An empty page stops the generator."""
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page(range(1, 51), 120))
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page([], 120))

    orders = list(client.orders.iter_all(year=2026, month=2))

    assert len(orders) == 50
    assert len(mocked.calls) == 2


def test_iter_all_is_lazy(client, mocked):
    """Taking the first item fetches only the first page."""
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page(range(1, 51), 120))

    iterator = client.orders.iter_all(year=2026, month=2)
    first = next(iterator)

    assert first["id"] == 1
    assert len(mocked.calls) == 1


def test_iter_all_passes_filters(client, mocked):
    """The filters are sent on every page."""
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page([1], 2))
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page([2], 2))

    orders = list(
        client.orders.iter_all(year=2026, month=2, status="paid", sort="date_desc")
    )

    assert [order["id"] for order in orders] == [1, 2]
    for call in mocked.calls:
        params = query_params(call)
        assert params["order.status"] == "paid"
        assert params["sort"] == "date_desc"
        assert params["order.date_created.from"] == "2026-02-01T00:00:00.000-05:00"
        assert params["order.date_created.to"] == "2026-02-28T23:59:59.999-05:00"


@pytest.mark.parametrize("page_size", [0, 51, True])
def test_iter_all_rejects_invalid_page_size(client, mocked, page_size):
    """page_size must be an int between 1 and 50, checked on the first next()."""
    with pytest.raises(ValueError):
        next(client.orders.iter_all(year=2026, month=2, page_size=page_size))


def search_params(offset, **overrides):
    """Build the full query params for an orders search page."""
    params = {
        "seller": "12345",
        "order.date_created.from": "2026-02-01T00:00:00.000-05:00",
        "order.date_created.to": "2026-02-28T23:59:59.999-05:00",
        "limit": "50",
        "sort": "date_asc",
        "offset": str(offset),
    }
    params.update(overrides)
    return params


def test_date_range_end_includes_last_millisecond(client):
    """The range includes the last millisecond of the month."""
    assert client.orders.date(2026, 2)["end"] == "2026-02-28T23:59:59.999-05:00"


def test_iter_all_resolves_period_once(client, mocked):
    """The month is resolved once, so crossing midnight mid-iteration keeps the range."""
    with freeze_time("2026-03-01T04:59:59Z") as freezer:
        mocked.add(
            responses.GET,
            f"{API_URL}/orders/search",
            json=page(range(1, 51), 60),
            match=[responses.matchers.query_param_matcher(search_params(0))],
        )
        mocked.add(
            responses.GET,
            f"{API_URL}/orders/search",
            json=page(range(51, 61), 60),
            match=[responses.matchers.query_param_matcher(search_params(50))],
        )

        iterator = client.orders.iter_all()
        orders = [next(iterator) for _ in range(50)]
        freezer.move_to("2026-03-01T05:00:01Z")
        orders.extend(iterator)

    assert [order["id"] for order in orders] == list(range(1, 61))


def test_iter_all_resolves_seller_once(client, storage, mocked):
    """A user_id change during iteration does not change the seller param."""
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page([1], 3))
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page([2], 3))
    mocked.add(responses.GET, f"{API_URL}/orders/search", json=page([3], 3))

    iterator = client.orders.iter_all(year=2026, month=2)
    first = next(iterator)

    token = storage.load_token()
    token["user_id"] = 777
    storage.save_token(token)

    rest = list(iterator)

    assert [first["id"], *[order["id"] for order in rest]] == [1, 2, 3]
    sellers = [query_params(call)["seller"] for call in mocked.calls]
    assert sellers == ["12345", "12345", "12345"]


@pytest.mark.parametrize("extra_params", [{"offset": 5}, {"limit": 10}])
def test_iter_all_rejects_offset_or_limit_in_extra_params(client, mocked, extra_params):
    """Pagination keys cannot be overridden through extra_params."""
    with pytest.raises(ValueError):
        next(client.orders.iter_all(year=2026, month=2, extra_params=extra_params))
