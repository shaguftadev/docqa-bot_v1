from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")


class DocumentValidationError(ValueError):
    """Raised when an uploaded file is unsupported or cannot be extracted."""


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int | None
    text: str
    section: str | None = None


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[\t \u00a0]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_document(filename: str, content: bytes) -> list[ExtractedPage]:
    """Extract UTF-8 text or page-aware PDF text; never trust the MIME header."""
    suffix = PurePath(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise DocumentValidationError("Supported file extensions are .pdf, .txt, and .md")
    if not content:
        raise DocumentValidationError("The uploaded file is empty")

    if suffix in {".txt", ".md"}:
        if b"\x00" in content:
            raise DocumentValidationError("The file does not look like UTF-8 text")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentValidationError("Text files must use UTF-8 encoding") from exc
        text = _clean_text(text)
        if not text:
            raise DocumentValidationError("No readable text was found")
        if suffix == ".md":
            pages: list[ExtractedPage] = []
            section: str | None = None
            current: list[str] = []
            for line in text.splitlines():
                match = _HEADING.match(line)
                if match and current:
                    section_text = _clean_text("\n".join(current))
                    if section_text:
                        pages.append(ExtractedPage(None, section_text, section))
                    current = []
                if match:
                    section = match.group(2).strip()
                current.append(line)
            section_text = _clean_text("\n".join(current))
            if section_text:
                pages.append(ExtractedPage(None, section_text, section))
            return pages
        return [ExtractedPage(None, text)]

    if not content.startswith(b"%PDF-"):
        raise DocumentValidationError("PDF content signature is missing")
    try:
        import pymupdf

        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.is_encrypted:
                raise DocumentValidationError("Encrypted PDFs are not supported")
            pages = [
                ExtractedPage(page_number=index, text=_clean_text(page.get_text("text", sort=True)))
                for index, page in enumerate(document, start=1)
            ]
    except DocumentValidationError:
        raise
    except Exception as exc:
        raise DocumentValidationError("The PDF could not be opened or parsed") from exc

    pages = [page for page in pages if page.text]
    if not pages:
        raise DocumentValidationError(
            "No selectable text was found in the PDF; scanned-image OCR is not included in this milestone"
        )
    return pages
