"""Organization-scoped knowledge base content for the live call path.

Each organization's own uploaded documents are chunked and stored in
`knowledge_chunks`, keyed by (organization_id, lang). This is the durable
source of truth the in-memory BM25 index used on live calls
(`app.livekit_agent.memory_kb`) rebuilds from — the index itself is a
disposable, rebuildable cache, never the source of truth.

Separate from `app.services.rag_service` (ChromaDB), which backs the
dashboard chat/Playground assistant and is not read by the live call path.
"""

from __future__ import annotations

import io
import json
from typing import Any, Optional

from app.livekit_agent.memory_kb import invalidate_org_index
from app.services.rag_service import chunk_text

SUPPORTED_UPLOAD_EXTENSIONS = (".pdf", ".docx", ".txt")


def extract_text_from_file(filename: str, content: bytes) -> str:
    """Extracts plain text from an uploaded .pdf, .docx, or .txt file.

    Raises ValueError for anything else — callers should surface that as a
    422, not a 500.
    """
    lowered = (filename or "").lower()
    if lowered.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if lowered.endswith(".docx"):
        from docx import Document

        document = Document(io.BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    if lowered.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")
    raise ValueError(
        f"Unsupported file type for {filename!r}; supported: {', '.join(SUPPORTED_UPLOAD_EXTENSIONS)}"
    )


def add_document(
    db, organization_id: int, *, lang: str, collection: str, doc_id: str,
    text: str, metadata: Optional[dict] = None,
) -> int:
    """Chunks and upserts a document into an organization's own knowledge
    base. Replaces any existing chunks for the same doc_id (so re-posting
    the same doc_id updates its content). Returns the number of chunks
    written."""
    chunks = chunk_text(text)
    metadata_json = json.dumps(metadata or {}, default=str)

    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM knowledge_chunks WHERE organization_id=%s AND doc_id=%s",
        (organization_id, doc_id),
    )
    for index, chunk in enumerate(chunks):
        cursor.execute(
            """INSERT INTO knowledge_chunks
                   (organization_id, lang, collection, doc_id, chunk_index, chunk_text, metadata_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (organization_id, lang, collection, doc_id, index, chunk, metadata_json),
        )
    db.commit()
    invalidate_org_index(organization_id, lang)
    return len(chunks)


def delete_document(db, organization_id: int, doc_id: str) -> bool:
    """Deletes every chunk of one of an organization's own documents."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT DISTINCT lang FROM knowledge_chunks WHERE organization_id=%s AND doc_id=%s",
        (organization_id, doc_id),
    )
    langs = [row["lang"] for row in cursor.fetchall()]
    if not langs:
        return False
    cursor.execute(
        "DELETE FROM knowledge_chunks WHERE organization_id=%s AND doc_id=%s",
        (organization_id, doc_id),
    )
    db.commit()
    for lang in langs:
        invalidate_org_index(organization_id, lang)
    return True


def list_documents(db, organization_id: int) -> list[dict[str, Any]]:
    """Lists an organization's own uploaded documents (one row per doc_id,
    not per chunk)."""
    cursor = db.cursor()
    cursor.execute(
        """SELECT doc_id, lang, collection, COUNT(*) AS chunk_count, MAX(updated_at) AS updated_at
           FROM knowledge_chunks WHERE organization_id=%s
           GROUP BY doc_id, lang, collection
           ORDER BY updated_at DESC""",
        (organization_id,),
    )
    return list(cursor.fetchall())
