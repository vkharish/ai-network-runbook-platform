"""Document parsing and chunking for the RAG ingestion pipeline."""

import re
from pathlib import Path
from typing import Any

import markdown as md_lib
from pypdf import PdfReader

from backend.core.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_pdf(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n\n".join(pages)


def _parse_markdown(file_path: Path) -> str:
    raw = file_path.read_text(encoding="utf-8")
    html = md_lib.markdown(raw)
    # Strip HTML tags — keep readable plain text
    plain = re.sub(r"<[^>]+>", " ", html)
    # Collapse extra whitespace
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    return plain.strip()


def _parse_text(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


def parse_document(file_path: Path) -> str:
    """Parse a PDF, Markdown, or plain-text file and return raw text."""
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        text = _parse_pdf(file_path)
    elif suffix in (".md", ".markdown"):
        text = _parse_markdown(file_path)
    else:
        text = _parse_text(file_path)

    log.info("document_parsed", source=file_path.name, chars=len(text))
    return text


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _find_break(text: str, limit: int) -> int:
    """Return the best split position at or before *limit* using natural boundaries."""
    for sep in ["\n\n", "\n", ". ", "! ", "? ", " "]:
        pos = text.rfind(sep, 0, limit)
        if pos > limit // 2:
            return pos + len(sep)
    return limit


def split_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> list[str]:
    """Sliding-window splitter that respects paragraph / sentence boundaries."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks: list[str] = []
    pos = 0

    while pos < len(text):
        end = min(pos + chunk_size, len(text))
        if end < len(text):
            end = _find_break(text, end)

        chunk = text[pos:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break
        pos = max(pos + 1, end - overlap)

    return chunks


def chunk_document(
    text: str,
    source: str,
    runbook_id: str,
    chunk_size: int = 1000,
    overlap: int = 200,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return a list of chunk dicts ready to be embedded and stored."""
    raw_chunks = split_text(text, chunk_size, overlap)
    result: list[dict[str, Any]] = []

    for i, chunk in enumerate(raw_chunks):
        result.append(
            {
                "text": chunk,
                "metadata": {
                    "source": source,
                    "runbook_id": runbook_id,
                    "chunk_index": i,
                    # Tags serialised as JSON string because ChromaDB metadata
                    # values must be scalar (str / int / float / bool).
                    "tags": ",".join(tags) if tags else "",
                },
            }
        )

    log.info("document_chunked", source=source, total_chunks=len(result))
    return result
