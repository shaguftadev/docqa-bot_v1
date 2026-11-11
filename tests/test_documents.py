import pymupdf
import pytest

from app.documents.chunking import chunk_pages
from app.documents.extractor import DocumentValidationError, ExtractedPage, extract_document


def test_extract_utf8_text_and_markdown_sections() -> None:
    plain = extract_document("faq.txt", "Returns are accepted within 30 days.".encode())
    markdown = extract_document("policy.md", b"# Returns\nDamaged items can be returned.\n\n## Refunds\nRefunds take five days.")

    assert plain[0].page_number is None
    assert plain[0].text == "Returns are accepted within 30 days."
    assert [page.section for page in markdown] == ["Returns", "Refunds"]
    assert "Damaged items" in markdown[0].text


def test_pdf_extraction_keeps_one_based_page_numbers() -> None:
    document = pymupdf.open()
    page_one = document.new_page()
    page_one.insert_text((72, 72), "Return policy: 30 days.")
    page_two = document.new_page()
    page_two.insert_text((72, 72), "Damaged items are handled by support.")
    content = document.tobytes()
    document.close()

    pages = extract_document("returns.pdf", content)

    assert [page.page_number for page in pages] == [1, 2]
    assert "30 days" in pages[0].text


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("faq.docx", b"text", "Supported file extensions"),
        ("faq.txt", b"\xff", "UTF-8"),
        ("fake.pdf", b"not a pdf", "signature"),
        ("empty.md", b"   ", "No readable text"),
    ],
)
def test_invalid_documents_are_rejected(filename: str, content: bytes, message: str) -> None:
    with pytest.raises(DocumentValidationError, match=message):
        extract_document(filename, content)


def test_chunking_overlaps_and_preserves_page_and_section() -> None:
    pages = [ExtractedPage(page_number=4, section="Returns", text="alpha beta gamma delta epsilon zeta")]

    chunks = chunk_pages(pages, chunk_size=16, overlap=4)

    assert len(chunks) > 1
    assert all(chunk.page_number == 4 and chunk.section == "Returns" for chunk in chunks)
    assert all(len(chunk.text) <= 16 for chunk in chunks)
    assert chunks[0].text.split()[-1] in chunks[1].text.split()


def test_chunking_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_pages([ExtractedPage(None, "text")], chunk_size=10, overlap=10)
