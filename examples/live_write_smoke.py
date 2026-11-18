"""Live write smoke test for meli-sdk (descriptions only).

It only touches one paused test listing whose SKU is ``MELI-SDK-TEST`` and never refreshes the
token (refresh tokens are single-use):

    export ML_ACCESS_TOKEN="APP_USR-..."      # required
    python examples/live_write_smoke.py --item-id MCO...

The output only shows PASS/FAIL lines, counts, warning codes and HTTP paths: no tokens, names,
addresses or prices.
"""

import argparse
import io
import os
import sys
import time
from urllib.parse import urlsplit

from meli_sdk import MeliClient, TokenStorage
from meli_sdk.exceptions import MeliError

TEST_SKU = "MELI-SDK-TEST"
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
        raise RuntimeError("live_write_smoke.py must never refresh or store a token")


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


def item_sku(item: dict):
    """Return the seller_custom_field or SELLER_SKU attribute of an item."""
    if item.get("seller_custom_field"):
        return item["seller_custom_field"]
    for attribute in item.get("attributes") or []:
        if attribute.get("id") == "SELLER_SKU":
            return attribute.get("value_name") or attribute.get("value")
    return None


def minimal_payload(item: dict, user_product_seller: bool) -> dict:
    """Build a minimal validation payload from the existing item."""
    payload = {
        "category_id": item.get("category_id"),
        "price": item.get("price"),
        "currency_id": item.get("currency_id"),
        "listing_type_id": item.get("listing_type_id"),
        "available_quantity": max(item.get("available_quantity") or 1, 1),
        "buying_mode": item.get("buying_mode") or "buy_it_now",
        "condition": item.get("condition") or "new",
        "attributes": item.get("attributes") or [],
    }
    pictures = item.get("pictures") or []
    if pictures and pictures[0].get("id"):
        payload["pictures"] = [{"id": pictures[0]["id"]}]

    if user_product_seller:
        payload["family_name"] = item.get("family_name") or item.get("title")
    else:
        payload["title"] = item.get("title")
    return payload


def log_requests(client) -> None:
    """Wrap session.request to print method, path and status without response bodies."""
    original = client.session.request

    def request(method, url, **kwargs):
        response = original(method, url, **kwargs)
        path = urlsplit(url).path
        print(f"      {method} {path} -> {response.status_code}")
        return response

    client.session.request = request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-id", required=True, help="paused test listing to touch")
    args = parser.parse_args()

    access_token = os.getenv("ML_ACCESS_TOKEN")
    if not access_token:
        print("Set ML_ACCESS_TOKEN to a valid access token (never a refresh token).")
        return 2

    client = MeliClient(
        client_id=os.getenv("ML_CLIENT_ID", "live-write-smoke"),
        client_secret="unused",
        token_storage=ReadOnlyTokenStorage(access_token),
        user_agent="meli-sdk-live-write-smoke",
    )

    with client:
        item = check("GET item", lambda: client.items.get(args.item_id))
        if not item:
            print("Cannot continue without the item.")
            return 1

        if item.get("status") != "paused":
            print(f"ABORT: item status is {item.get('status')!r}, expected 'paused'.")
            return 1
        if item_sku(item) != TEST_SKU:
            print(f"ABORT: item SKU is not {TEST_SKU!r}.")
            return 1

        log_requests(client)

        user_product_seller = check(
            "items.is_user_product_seller", client.items.is_user_product_seller
        )
        print(f"      user product seller={bool(user_product_seller)}")

        payload = minimal_payload(item, bool(user_product_seller))

        def validate():
            result = client.items.validate(payload)
            warning_codes = [cause.code for cause in result.warnings]
            print(
                f"      valid={result.valid} errors={len(result.errors)} "
                f"warnings={warning_codes}"
            )
            for cause in result.errors:
                print(f"      error {cause.code}: {cause.message}")
            if not result.valid:
                raise AssertionError("payload rebuilt from the test listing is not valid")
            return result

        check("items.validate", validate)

        def roundtrip(label: str, text: str):
            def run():
                client.items.set_description(args.item_id, text)
                current = client.items.get_description(args.item_id)
                if current.get("plain_text") != text:
                    raise AssertionError(f"description {label} did not persist")
                return current

            return run

        check("items.set_description #1 (first write)", roundtrip("1", "Descripcion de prueba 1"))
        check(
            "items.set_description #2 (PUT update)",
            roundtrip("2", "Descripcion de prueba 2"),
        )

        try:
            from PIL import Image, ImageDraw
        except ImportError:
            print("SKIP  picture checks: Pillow is not installed")
        else:

            def picture_roundtrip():
                before = len(item.get("pictures") or [])
                image = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                draw.ellipse((50, 50, 250, 250), fill=(200, 30, 30, 255))
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")

                uploaded = client.items.upload_picture(
                    buffer.getvalue(), filename="sdk-test.png", convert=True
                )
                print(
                    f"      picture id prefix={uploaded.id.split('-')[0]} "
                    f"max_size={uploaded.max_size}"
                )
                client.items.add_picture(args.item_id, uploaded.id)

                updated = client.items.get(args.item_id)
                pictures = updated.get("pictures") or []
                if len(pictures) != before + 1:
                    raise AssertionError("picture count did not grow by one")
                if uploaded.id not in [picture.get("id") for picture in pictures]:
                    raise AssertionError("uploaded picture is not linked")
                return uploaded

            check("items.upload_picture + add_picture", picture_roundtrip)

    passed = sum(ok for _, ok in results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MeliError as exc:
        print(f"Aborted: {type(exc).__name__}: {exc}")
        sys.exit(1)
