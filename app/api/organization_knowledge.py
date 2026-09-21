"""
Organization-scoped Knowledge Base API.

Lets each organization upload its own documents, which get chunked and
stored in `knowledge_chunks` and merged into that organization's own
in-memory BM25 index — the retrieval mechanism the live call path
(`app/api/openai_realtime.py`) actually uses. Separate from
`app/api/rag.py`'s ChromaDB-backed endpoints, which back the dashboard
chat/Playground assistant instead and are not organization-scoped.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.auth import current_admin
from app.database.db import get_db
from app.services import org_knowledge_service

router = APIRouter(prefix="/organization-knowledge-base", tags=["Organization Knowledge Base"])

SUPPORTED_LANGS = {"en", "ta"}


class OrgDocumentOut(BaseModel):
    doc_id: str
    lang: str
    collection: str
    chunk_count: int
    updated_at: Optional[str] = None


class AddResult(BaseModel):
    doc_id: str
    collection: str
    lang: str
    chunks_inserted: int


class DeleteResult(BaseModel):
    doc_id: str
    deleted: bool


@router.get("/documents", response_model=List[OrgDocumentOut], summary="List this organization's own documents")
def list_documents(admin: dict = Depends(current_admin), db=Depends(get_db)):
    rows = org_knowledge_service.list_documents(db, admin["organization_id"])
    return [
        OrgDocumentOut(
            doc_id=row["doc_id"], lang=row["lang"], collection=row["collection"],
            chunk_count=row["chunk_count"],
            updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
        )
        for row in rows
    ]


@router.post(
    "/documents",
    response_model=AddResult,
    status_code=status.HTTP_201_CREATED,
    summary="Add or update a document in this organization's own knowledge base",
)
async def add_document(
    collection: str = Form(..., description="Topic label, e.g. 'pricing', 'faq', 'policies'"),
    doc_id: str = Form(..., description="Unique document identifier (slug-style)"),
    lang: str = Form("en", description="Language this document is written in: 'en' or 'ta'"),
    text: str = Form("", description="Document text to chunk and index"),
    file: Optional[UploadFile] = File(None, description="A .pdf, .docx, or .txt file to extract text from"),
    admin: dict = Depends(current_admin),
    db=Depends(get_db),
):
    """
    Chunks and indexes a document into this organization's own knowledge
    base, used by their live calls. If a document with the same `doc_id`
    already exists for this organization, it is replaced (upsert semantics).

    Accepts pasted `text`, an uploaded `file` (PDF/DOCX/TXT), or both —
    when both are given, the extracted file text is appended after the
    pasted text.
    """
    lang_normalized = lang.strip().lower()
    if lang_normalized not in SUPPORTED_LANGS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"lang must be one of {sorted(SUPPORTED_LANGS)}",
        )

    combined_text = text.strip()
    if file is not None and file.filename:
        try:
            file_bytes = await file.read()
            extracted = org_knowledge_service.extract_text_from_file(file.filename, file_bytes)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not read {file.filename!r}: {exc}",
            ) from exc
        combined_text = f"{combined_text}\n\n{extracted}".strip() if combined_text else extracted.strip()

    if not combined_text:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide document text, upload a file, or both.",
        )

    chunks = org_knowledge_service.add_document(
        db, admin["organization_id"], lang=lang_normalized, collection=collection,
        doc_id=doc_id, text=combined_text,
    )
    return AddResult(doc_id=doc_id, collection=collection, lang=lang_normalized, chunks_inserted=chunks)


@router.delete("/documents/{doc_id}", response_model=DeleteResult, summary="Delete one of this organization's own documents")
def delete_document(doc_id: str, admin: dict = Depends(current_admin), db=Depends(get_db)):
    deleted = org_knowledge_service.delete_document(db, admin["organization_id"], doc_id)
    return DeleteResult(doc_id=doc_id, deleted=deleted)
