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
