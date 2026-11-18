import pytest
import responses

API_URL = "https://api.mercadolibre.com"


def test_create_posts_json(client, mocked):
    """Creating an item posts the body as JSON."""
    body = {"title": "Test item", "price": 100.0, "currency_id": "COP"}
    mocked.add(
        responses.POST,
        f"{API_URL}/items",
        json={"id": "MCO1"},
        match=[responses.matchers.json_params_matcher(body)],
    )

    assert client.items.create(body) == {"id": "MCO1"}


def test_update_price_puts_price(client, mocked):
    """Updating the price sends a PUT with only the price field."""
    mocked.add(
        responses.PUT,
        f"{API_URL}/items/MCO1",
        json={"id": "MCO1", "price": 150.0},
        match=[responses.matchers.json_params_matcher({"price": 150.0})],
    )

    assert client.items.update_price("MCO1", 150.0) == {
        "id": "MCO1",
        "price": 150.0,
    }


def test_update_stock_puts_available_quantity(client, mocked):
    """Updating the stock sends a PUT with only the available_quantity field."""
    mocked.add(
        responses.PUT,
        f"{API_URL}/items/MCO1",
        json={"id": "MCO1", "available_quantity": 3},
        match=[
            responses.matchers.json_params_matcher({"available_quantity": 3})
        ],
    )

    assert client.items.update_stock("MCO1", 3) == {
        "id": "MCO1",
        "available_quantity": 3,
    }


def test_get_visits_joins_ids(client, mocked):
    """A list of item ids is joined into a single comma-separated query param."""
    mocked.add(
        responses.GET,
        f"{API_URL}/items/visits",
        json={"results": []},
        match=[
            responses.matchers.query_param_matcher({"ids": "MCO1,MCO2"})
        ],
    )

    assert client.items.get_visits(["MCO1", "MCO2"]) == {"results": []}


def test_search_uses_token_user_id(client, mocked):
    """Searching items uses the seller id from the active token."""
    mocked.add(
        responses.GET,
        f"{API_URL}/users/12345/items/search",
        json={"results": []},
        match=[
            responses.matchers.query_param_matcher(
                {"offset": "0", "limit": "50"}
            )
        ],
    )

    assert client.items.search() == {"results": []}


def items_page(ids, scroll_id=None, include_scroll=True):
    """Build an items search page body."""
    body = {"results": ids}
    if include_scroll:
        body["scroll_id"] = scroll_id
    return body


def test_iter_all_uses_scan_and_follows_scroll_id(client, mocked):
    """iter_all uses scan mode and sends the latest scroll_id, never offset."""
    first = [f"MCO{index}" for index in range(1, 101)]
    second = [f"MCO{index}" for index in range(101, 131)]
    url = f"{API_URL}/users/12345/items/search"
    mocked.add(
        responses.GET,
        url,
        json=items_page(first, "S1"),
        match=[
            responses.matchers.query_param_matcher(
                {"search_type": "scan", "limit": "100"}
            )
        ],
    )
    mocked.add(
        responses.GET,
        url,
        json=items_page(second, "S2"),
        match=[
            responses.matchers.query_param_matcher(
                {"search_type": "scan", "limit": "100", "scroll_id": "S1"}
            )
        ],
    )
    mocked.add(
        responses.GET,
        url,
        json=items_page([], "S3"),
        match=[
            responses.matchers.query_param_matcher(
                {"search_type": "scan", "limit": "100", "scroll_id": "S2"}
            )
        ],
    )

    assert list(client.items.iter_all()) == first + second
    assert len(mocked.calls) == 3


def test_iter_all_is_lazy(client, mocked):
    """Taking the first id fetches only the first page."""
    url = f"{API_URL}/users/12345/items/search"
    mocked.add(responses.GET, url, json=items_page(["MCO1", "MCO2"], "S1"))

    iterator = client.items.iter_all()
    first = next(iterator)

    assert first == "MCO1"
    assert len(mocked.calls) == 1


def test_iter_all_stops_without_scroll_id(client, mocked):
    """A page without a usable scroll_id is yielded and then stops."""
    url = f"{API_URL}/users/12345/items/search"
    mocked.add(responses.GET, url, json=items_page(["MCO1"], scroll_id=None))

    assert list(client.items.iter_all()) == ["MCO1"]
    assert len(mocked.calls) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page_size": 0},
        {"page_size": 101},
        {"page_size": True},
        {"extra_params": {"offset": 0}},
        {"extra_params": {"limit": 10}},
        {"extra_params": {"search_type": "scan"}},
        {"extra_params": {"scroll_id": "x"}},
    ],
)
def test_iter_all_rejects_invalid_args(client, mocked, kwargs):
    """Page size and pagination extra params are rejected on the first next()."""
    with pytest.raises(ValueError):
        next(client.items.iter_all(**kwargs))


def test_iter_all_uses_token_user_id_once(client, storage, mocked):
    """The seller id is resolved once, even if the token changes mid-iteration."""
    url = f"{API_URL}/users/12345/items/search"
    mocked.add(
        responses.GET,
        url,
        json=items_page(["MCO1"], "S1"),
        match=[
            responses.matchers.query_param_matcher(
                {"search_type": "scan", "limit": "100"}
            )
        ],
    )
    mocked.add(
        responses.GET,
        url,
        json=items_page([], "S2"),
        match=[
            responses.matchers.query_param_matcher(
                {"search_type": "scan", "limit": "100", "scroll_id": "S1"}
            )
        ],
    )

    iterator = client.items.iter_all()
    first = next(iterator)

    token = storage.load_token()
    token["user_id"] = 777
    storage.save_token(token)

    rest = list(iterator)

    assert [first, *rest] == ["MCO1"]
