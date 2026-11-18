"""Read-only smoke test of meli-sdk against a real Mercado Libre account.

It only sends GET requests and never refreshes the token. Mercado Libre refresh tokens are
single-use, so refreshing here could invalidate the token that another app (for example a
production integration) holds. Pass a valid access token through the environment:

    export ML_ACCESS_TOKEN="APP_USR-..."      # required, valid for up to 6 hours
    export ML_CLIENT_ID="..."                 # optional, only used in the User-Agent check
    python examples/live_smoke.py

The output only shows counts, ids and PASS/FAIL lines: no tokens, names or addresses.
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from itertools import islice

from meli_sdk import MeliClient, TokenStorage
from meli_sdk.exceptions import MeliAPIError, MeliError

COLOMBIA = timezone(timedelta(hours=-5))
results = []


class ReadOnlyTokenStorage(TokenStorage):
    """Holds one access token in memory and refuses to persist a refreshed one."""

    def __init__(self, access_token: str) -> None:
        self._token = {
            "access_token": access_token,
            "expires_at": time.time() + 3600,
        }

    def load_token(self) -> dict:
        return dict(self._token)

    def save_token(self, token_data: dict) -> None:
        raise RuntimeError("live_smoke.py must never refresh or store a token")


def check(name: str, func) -> object:
    """Run one check and record PASS/FAIL without printing sensitive data."""
    try:
        value = func()
    except Exception as exc:  # noqa: BLE001 - report every failure and keep going
        results.append((name, False))
        print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        return None
    results.append((name, True))
    print(f"PASS  {name}")
    return value


def main() -> int:
    access_token = os.getenv("ML_ACCESS_TOKEN")
    if not access_token:
        print("Set ML_ACCESS_TOKEN to a valid access token (never a refresh token).")
        return 2

    client = MeliClient(
        client_id=os.getenv("ML_CLIENT_ID", "live-smoke"),
        client_secret="unused",
        token_storage=ReadOnlyTokenStorage(access_token),
        user_agent="meli-sdk-live-smoke",
    )

    with client:
        me = check("GET /users/me", lambda: client.request("GET", "/users/me"))
        if not me:
            print("Cannot continue without /users/me (expired or invalid access token?).")
            return 1
        seller_id = me["id"]
        print(f"      seller id={seller_id} site={me.get('site_id')}")

        now = datetime.now(COLOMBIA)
        first_month = (now.year, now.month)
        prev = (now.replace(day=1) - timedelta(days=1))
        months = [first_month, (prev.year, prev.month)]

        orders = []
        for year, month in months:
            def walk(year=year, month=month):
                return list(
                    islice(
                        client.orders.iter_all(seller_id=seller_id, year=year, month=month),
                        120,
                    )
                )

            batch = check(f"orders.iter_all {year}-{month:02d} (up to 120)", walk) or []
            print(f"      orders fetched={len(batch)}")

            def in_window(batch=batch, year=year, month=month):
                for order in batch:
                    created = datetime.fromisoformat(order["date_created"]).astimezone(COLOMBIA)
                    if (created.year, created.month) != (year, month):
                        raise AssertionError(f"order {order['id']} outside {year}-{month:02d}")
                return True

            if batch:
                check(f"orders inside {year}-{month:02d} in Colombia time", in_window)
            orders.extend(batch)

        if orders:
            order = orders[0]
            pack_id = order.get("pack_id") or order["id"]
            has_doc = check(
                "bills.has_fiscal_document",
                lambda: client.bills.has_fiscal_document(pack_id),
            )
            print(f"      pack {pack_id} has fiscal document={has_doc}")

            def billing():
                try:
                    return sorted(client.bills.get_billing_info(order["id"]))
                except MeliAPIError as exc:
                    if exc.status_code == 404:
                        return ["<404: no billing info>"]
                    raise

            keys = check("bills.get_billing_info", billing)
            print(f"      billing info keys={keys}")

            shipping_id = (order.get("shipping") or {}).get("id")
            if shipping_id:
                shipment = check(
                    "shipments.get", lambda: client.shipments.get(shipping_id)
                )
                if shipment:
                    print(f"      shipment status={shipment.get('status')}")
        else:
            print("SKIP  bills/shipments checks: no orders in the last two months")

        ids = check(
            "items.iter_all (scan, up to 150)",
            lambda: list(islice(client.items.iter_all(seller_id=seller_id), 150)),
        ) or []
        print(f"      item ids fetched={len(ids)} unique={len(set(ids))}")

        if ids:
            sample = ids[:25]

            def multiget():
                items = client.items.get_many(
                    sample,
                    attributes=["title", "price", "category_id", "listing_type_id"],
                )
                returned = [item["id"] for item in items]
                expected = [item_id for item_id in sample if item_id in set(returned)]
                if returned != expected:
                    raise AssertionError("get_many did not keep the input order")
                if not all("price" in item for item in items):
                    raise AssertionError("requested attribute missing")
                return items

            items = check("items.get_many (2 batches, attributes)", multiget) or []
            print(f"      items returned={len(items)} of {len(sample)}")

            if items and items[0].get("price"):
                sample_item = items[0]

                def listing_prices():
                    prices = client.items.get_listing_prices(
                        sample_item["price"],
                        category_id=sample_item.get("category_id"),
                    )
                    if not prices:
                        raise AssertionError("empty listing prices")
                    return prices

                prices = check("items.get_listing_prices", listing_prices)
                print(f"      listing prices returned={len(prices or [])}")

                if sample_item.get("listing_type_id"):

                    def listing_price():
                        value = client.items.get_listing_price(
                            sample_item["price"],
                            sample_item["listing_type_id"],
                            category_id=sample_item.get("category_id"),
                        )
                        print(
                            f"      percentage_fee={value.percentage_fee} "
                            f"currency={value.currency_id}"
                        )
                        return value

                    check("items.get_listing_price", listing_price)

                def free_shipping_quote():
                    quote = client.shipments.get_free_shipping_quote(
                        item_id=sample_item["id"]
                    )
                    print(
                        f"      billable_weight={quote.billable_weight} "
                        f"currency={quote.currency_id}"
                    )
                    return quote

                check("shipments.get_free_shipping_quote", free_shipping_quote)

    passed = sum(ok for _, ok in results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MeliError as exc:
        print(f"Aborted: {type(exc).__name__}: {exc}")
        sys.exit(1)
