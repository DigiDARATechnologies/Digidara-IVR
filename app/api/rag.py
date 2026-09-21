"""
RAG Knowledge Base admin API.

Provides endpoints so non-developers can manage the DigiDara knowledge base
through the frontend's Knowledge Base page, without touching code or files.

All endpoints degrade gracefully: if ChromaDB is unavailable (e.g. first
run with a blocked network, or a cold start before the model is downloaded),
they return a clear error message explaining the situation rather than a
500 crash.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import current_admin
from app.services import rag_service
from app.services.knowledge_base import REQUIRED_COLLECTIONS, OPTIONAL_COLLECTIONS

# organizations.id=1 is seeded as a fixed row (app/database/db.py init_db())
# and is always DigiDARA's own workspace — never a customer's.
DIGIDARA_ORGANIZATION_ID = 1


def _require_digidara_workspace(admin: dict = Depends(current_admin)) -> dict:
    """This admin console manages DigiDARA's own dashboard-chat knowledge
    base content (the hardcoded seed collections), not any customer
    organization's — restricted to DigiDARA's own workspace. Customer
    organizations manage their own live-call content at
    /organization-knowledge-base instead."""
    if admin.get("organization_id") != DIGIDARA_ORGANIZATION_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This knowledge base belongs to the DigiDARA workspace only.",
        )
    return admin


router = APIRouter(
    prefix="/knowledge-base",
    tags=["Knowledge Base"],
    dependencies=[Depends(current_admin), Depends(_require_digidara_workspace)],
)

ALL_KNOWN_COLLECTIONS = REQUIRED_COLLECTIONS + OPTIONAL_COLLECTIONS


def _require_rag():
    """Raises 503 with a clear explanation if RAG isn't available."""
    if not rag_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The RAG knowledge base is not available yet. "
                "This usually means the embedding model is still being "
                "downloaded on first run (can take 1-2 minutes on a fast "
                "connection), or the download was blocked by a firewall/proxy. "
                f"Last error: {rag_service.last_error()}"
            ),
        )


class KBStatus(BaseModel):
    available: bool
    error: Optional[str] = None
    collections: List[str] = []


class DocumentIn(BaseModel):
    collection: str = Field(..., description="Target collection (e.g. 'faq', 'services', 'courses')")
    doc_id: str = Field(..., description="Unique document identifier (slug-style, e.g. 'faq_pricing_2025')")
    text: str = Field(..., description="Full document text to chunk and embed")
    source: Optional[str] = Field("admin_upload", description="Source label for this document")


class DocumentOut(BaseModel):
    id: str
    preview: str
    metadata: dict = {}


class AddResult(BaseModel):
    doc_id: str
    collection: str
    chunks_inserted: int


class DeleteResult(BaseModel):
    doc_id: str
    collection: str
    deleted: bool


@router.get("/status", response_model=KBStatus, summary="Check RAG knowledge base availability")
def get_rag_status():
    """Returns whether the RAG knowledge base is available, and which
    collections exist. Use this to confirm the embedding model was
    downloaded successfully on first startup."""
    available = rag_service.is_available()
    collections = []
    if available:
        for col_name in ALL_KNOWN_COLLECTIONS:
            col = rag_service._get_collection(col_name)
            if col is not None:
                try:
                    if col.count() >= 0:
                        collections.append(col_name)
                except Exception:
                    pass
    return KBStatus(
        available=available,
        error=rag_service.last_error(),
        collections=collections,
    )


@router.get(
    "/collections",
    response_model=List[str],
    summary="List all available collections",
)
def list_collections():
    """Returns the names of all collections that exist in ChromaDB."""
    _require_rag()
    return ALL_KNOWN_COLLECTIONS


@router.get(
    "/collections/{collection}/documents",
    response_model=List[DocumentOut],
    summary="List all documents in a collection",
)
def list_documents(collection: str):
    """Returns all distinct document IDs and previews in the given collection."""
    _require_rag()
    if collection not in ALL_KNOWN_COLLECTIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown collection '{collection}'. Valid collections: {ALL_KNOWN_COLLECTIONS}",
        )
    docs = rag_service.list_documents(collection)
    return [DocumentOut(**d) for d in docs]


@router.post(
    "/documents",
    response_model=AddResult,
    status_code=status.HTTP_201_CREATED,
    summary="Add or update a document in the knowledge base",
)
def add_document(doc: DocumentIn):
    """
    Chunks and embeds a document into the specified collection. If a
    document with the same `doc_id` already exists, it is replaced
    (upsert semantics) — so you can update content by posting the same
    doc_id with new text.
    """
    _require_rag()
    if not doc.text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Document text cannot be empty.",
        )
    chunks = rag_service.add_document(
        collection_name=doc.collection,
        doc_id=doc.doc_id,
        text=doc.text,
        metadata={"collection": doc.collection, "source": doc.source or "admin_upload"},
    )
    if chunks == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document was not inserted — check server logs for details.",
        )
    return AddResult(doc_id=doc.doc_id, collection=doc.collection, chunks_inserted=chunks)


@router.delete(
    "/collections/{collection}/documents/{doc_id}",
    response_model=DeleteResult,
    summary="Delete a document from the knowledge base",
)
def delete_document(collection: str, doc_id: str):
    """Removes all chunks belonging to the given document from the collection."""
    _require_rag()
    deleted = rag_service.delete_document(collection, doc_id)
    return DeleteResult(doc_id=doc_id, collection=collection, deleted=deleted)


@router.post(
    "/search",
    summary="Test the RAG retrieval (debug endpoint)",
)
def search_kb(
    query: str = Query(..., description="Test query to retrieve relevant chunks for"),
    collection: Optional[str] = Query(None, description="Search a specific collection, or leave blank for all"),
    top_k: int = Query(3, description="Number of chunks to retrieve"),
):
    """
    Debug endpoint: returns the raw chunks that would be retrieved for a
    given customer query, so you can verify the knowledge base is working
    correctly before a live call. Available from the Knowledge Base page.
    """
    _require_rag()
    collections = [collection] if collection else None
    chunks = rag_service.retrieve(query, collections=collections, top_k=top_k)
    return {
        "query": query,
        "chunks_found": len(chunks),
        "context_block": rag_service.build_context_block(chunks),
        "chunks": [
            {
                "text": c["text"],
                "collection": c["collection"],
                "distance": round(c["distance"], 4),
                "metadata": c["metadata"],
            }
            for c in chunks
        ],
    }
