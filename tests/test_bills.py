import pytest
import responses

from MeliAPIClient.exceptions import MeliAPIError

API_URL = "https://api.mercadolibre.com"
PDF_BYTES = b"%PDF-1.4 test"


def test_upload_fiscal_document_posts_multipart_field(client, mocked, tmp_path):
    """The fiscal document is uploaded as a multipart file field."""
    pdf_path = tmp_path / "factura.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    mocked.add(responses.POST, f"{API_URL}/packs/123/fiscal_documents", json={})

    client.bills.upload_fiscal_document(123, str(pdf_path))

    request = mocked.calls[0].request
    assert request.method == "POST"
    assert b'name="fiscal_document"' in request.body
    assert PDF_BYTES in request.body


@pytest.mark.xfail(
    strict=True,
    reason="Known bug: no MIME type; Zincro patches it; fixed in F2-01",
)
def test_upload_fiscal_document_sends_pdf_mime(client, mocked, tmp_path):
    """The fiscal document part must declare the PDF MIME type."""
    pdf_path = tmp_path / "factura.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    mocked.add(responses.POST, f"{API_URL}/packs/123/fiscal_documents", json={})

    client.bills.upload_fiscal_document(123, str(pdf_path))

    assert b"Content-Type: application/pdf" in mocked.calls[0].request.body


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


@pytest.mark.xfail(
    strict=True, reason="Known bug: bool(dict) is always True; fixed in F2-02"
)
def test_has_fiscal_document_empty_list_is_false(client, mocked):
    """An empty fiscal_documents list means no document."""
    mocked.add(
        responses.GET,
        f"{API_URL}/packs/123/fiscal_documents",
        json={"fiscal_documents": []},
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
