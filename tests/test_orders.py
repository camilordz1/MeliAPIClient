import pytest
import responses

API_URL = "https://api.mercadolibre.com"


def test_search_builds_params_for_month(client, mocked):
    """Searching a month builds the seller, date range and pagination params."""
    params = {
        "seller": "12345",
        "order.date_created.from": "2026-02-01T00:00:00.000-00:00",
        "order.date_created.to": "2026-02-28T23:59:59.000-00:00",
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


@pytest.mark.xfail(
    strict=True, reason="Known bug: hardcoded -00:00 offset; fixed in F2-03"
)
def test_date_range_uses_colombia_offset(client):
    """The Colombia (MCO) date range must end with the -05:00 offset."""
    assert client.orders.date(2026, 2)["start"].endswith("-05:00")


def test_get_and_get_pack_paths(client, mocked):
    """get and get_pack hit the order and pack detail endpoints."""
    mocked.add(responses.GET, f"{API_URL}/orders/1", json={"id": 1})
    mocked.add(responses.GET, f"{API_URL}/packs/2", json={"id": 2})

    assert client.orders.get(1) == {"id": 1}
    assert client.orders.get_pack(2) == {"id": 2}
