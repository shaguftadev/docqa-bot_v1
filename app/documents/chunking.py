from dataclasses import dataclass

from app.documents.extractor import ExtractedPage


@dataclass(frozen=True)
class DocumentChunk:
    index: int
    text: str
    page_number: int | None
    section: str | None
    char_start: int
    char_end: int


def chunk_pages(pages: list[ExtractedPage], chunk_size: int, overlap: int) -> list[DocumentChunk]:
    """Split by character count while preserving source page and section metadata."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between zero and chunk_size - 1")

    chunks: list[DocumentChunk] = []
    for page in pages:
        text = page.text.strip()
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                # Prefer a word/paragraph boundary, but keep chunks reasonably full.
                boundary = max(text.rfind("\n", start + chunk_size // 2, end), text.rfind(" ", start + chunk_size // 2, end))
                if boundary > start:
                    end = boundary
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    DocumentChunk(
                        index=len(chunks),
                        text=chunk_text,
                        page_number=page.page_number,
                        section=page.section,
                        char_start=start,
                        char_end=end,
                    )
                )
            if end >= len(text):
                break
            next_start = max(start + 1, end - overlap)
            if text[next_start:next_start + 1].isspace():
                next_start += 1
            start = next_start
    return chunks
