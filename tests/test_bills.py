import io
import json
import time

import pytest
import responses

from meli_sdk import Bill, Session
from meli_sdk.exceptions import MeliAPIError

API_URL = "https://api.mercadolibre.com"
PDF_BYTES = b"%PDF-1.4 test"
UPLOAD_URL = f"{API_URL}/packs/123/fiscal_documents"


def make_legacy_session(tmp_path) -> Session:
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
            "user_id": 12345,
        })
    )
    return Session(str(keys_file), str(token_file), {})


def test_upload_fiscal_document_posts_multipart_field(client, mocked, tmp_path):
    """The fiscal document is uploaded as a multipart file field."""
    pdf_path = tmp_path / "factura.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    mocked.add(responses.POST, UPLOAD_URL, json={})

    client.bills.upload_fiscal_document(123, str(pdf_path))

    request = mocked.calls[0].request
    assert request.method == "POST"
    assert b'name="fiscal_document"' in request.body
    assert PDF_BYTES in request.body


def test_upload_fiscal_document_sends_pdf_mime(client, mocked, tmp_path):
    """The fiscal document part must declare the PDF MIME type."""
    pdf_path = tmp_path / "factura.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    mocked.add(responses.POST, UPLOAD_URL, json={})

    client.bills.upload_fiscal_document(123, str(pdf_path))

    assert b"Content-Type: application/pdf" in mocked.calls[0].request.body


def test_upload_from_path_uses_basename_and_pdf_mime(client, mocked, tmp_path):
    """A path input uses its basename as filename and the PDF MIME type."""
    pdf_path = tmp_path / "factura.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    mocked.add(responses.POST, UPLOAD_URL, json={})

    client.bills.upload_fiscal_document(123, pdf_path)

    body = mocked.calls[0].request.body
    assert b'filename="factura.pdf"' in body
    assert b"Content-Type: application/pdf" in body


def test_upload_from_bytes(client, mocked):
    """A bytes input is uploaded as factura.pdf without a temp file."""
    mocked.add(responses.POST, UPLOAD_URL, json={})

    client.bills.upload_fiscal_document(123, PDF_BYTES)

    body = mocked.calls[0].request.body
    assert PDF_BYTES in body
    assert b'filename="factura.pdf"' in body
    assert b"Content-Type: application/pdf" in body


def test_upload_from_file_object(client, mocked):
    """A file object without a name uses the default filename."""
    mocked.add(responses.POST, UPLOAD_URL, json={})

    client.bills.upload_fiscal_document(123, io.BytesIO(PDF_BYTES))

    body = mocked.calls[0].request.body
    assert PDF_BYTES in body
    assert b'filename="factura.pdf"' in body
    assert b"Content-Type: application/pdf" in body


def test_upload_explicit_filename_wins(client, mocked):
    """An explicit filename replaces the default one."""
    mocked.add(responses.POST, UPLOAD_URL, json={})

    client.bills.upload_fiscal_document(123, PDF_BYTES, filename="custom.pdf")

    assert b'filename="custom.pdf"' in mocked.calls[0].request.body


def test_upload_bytes_is_retried_with_body_on_429(client, mocked):
    """A retried bytes upload sends the whole document both times."""
    client._sleep = lambda seconds: None
    mocked.add(responses.POST, UPLOAD_URL, status=429)
    mocked.add(responses.POST, UPLOAD_URL, status=200, json={})

    client.bills.upload_fiscal_document(123, PDF_BYTES)

    assert len(mocked.calls) == 2
    assert PDF_BYTES in mocked.calls[0].request.body
    assert PDF_BYTES in mocked.calls[1].request.body


@pytest.mark.parametrize("kind", ["bytes", "path", "fileobj"])
def test_upload_rejects_non_pdf(client, mocked, tmp_path, kind):
    """A document without the %PDF- signature is rejected before any HTTP call."""
    if kind == "bytes":
        document = b"hello"
    elif kind == "path":
        text_path = tmp_path / "factura.pdf"
        text_path.write_bytes(b"PK\x03\x04 not a pdf")
        document = text_path
    else:
        document = io.BytesIO(b"PK\x03\x04")

    with pytest.raises(ValueError):
        client.bills.upload_fiscal_document(123, document)


def test_upload_rejects_empty_document(client, mocked):
    """An empty document is rejected before any HTTP call."""
    with pytest.raises(ValueError):
        client.bills.upload_fiscal_document(123, b"")


@pytest.mark.parametrize("document", [123, ["a"]])
def test_upload_rejects_unsupported_type(client, mocked, document):
    """Types that are not path-like, bytes or file objects are rejected."""
    with pytest.raises(TypeError):
        client.bills.upload_fiscal_document(123, document)


def test_has_fiscal_document_404_is_false(client, mocked):
    """A missing fiscal document resource means no document."""
    mocked.add(
        responses.GET,
        f"{API_URL}/packs/123/fiscal_documents",
        status=404,
        json={"message": "not found"},
    )

    assert client.bills.has_fiscal_document(123) is False


def test_has_fiscal_document_with_documents_is_true(client, mocked):
    """A pack with fiscal documents reports True."""
    mocked.add(
        responses.GET,
        f"{API_URL}/packs/123/fiscal_documents",
        json={"fiscal_documents": [{"id": "x"}]},
    )

    assert client.bills.has_fiscal_document(123) is True


def test_has_fiscal_document_empty_list_is_false(client, mocked):
    """An empty fiscal_documents list means no document."""
    mocked.add(
        responses.GET,
        f"{API_URL}/packs/123/fiscal_documents",
        json={"fiscal_documents": []},
    )

    assert client.bills.has_fiscal_document(123) is False


@pytest.mark.parametrize("payload", [{}, {"fiscal_documents": "nope"}])
def test_has_fiscal_document_without_key_is_false(client, mocked, payload):
    """A response without a fiscal_documents list means no document."""
    mocked.add(
        responses.GET,
        f"{API_URL}/packs/123/fiscal_documents",
        json=payload,
    )

    assert client.bills.has_fiscal_document(123) is False


def test_has_fiscal_document_reraises_other_errors(client, mocked):
    """Errors other than 404 are propagated as MeliAPIError."""
    mocked.add(
        responses.GET,
        f"{API_URL}/packs/123/fiscal_documents",
        status=500,
        json={"message": "boom"},
    )

    with pytest.raises(MeliAPIError):
        client.bills.has_fiscal_document(123)


def test_legacy_bill_upload_still_works(mocked, tmp_path):
    """The legacy Bill.upload keeps working with positional arguments."""
    pdf_path = tmp_path / "factura.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    session = make_legacy_session(tmp_path)
    mocked.add(responses.POST, UPLOAD_URL, json={})

    Bill(session).upload(123, str(pdf_path))

    body = mocked.calls[0].request.body
    assert PDF_BYTES in body
    assert b"Content-Type: application/pdf" in body
