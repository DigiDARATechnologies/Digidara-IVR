"""Separate Chroma-backed RAG for facility procedures with traceable citations."""

import os
from dataclasses import dataclass
from typing import Any

from app.facility.rag.seed_documents import FACILITY_SEED_DOCUMENTS


FACILITY_CHROMA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "chroma", "facility"))
COLLECTION_NAME = "nectar_facility_knowledge_v1"
MAX_DISTANCE = 1.25


@dataclass(frozen=True)
class FacilityCitation:
    source_id: str
    title: str
    document_type: str
    revision: str


@dataclass(frozen=True)
class FacilityRetrievedChunk:
    text: str
    citation: FacilityCitation
    distance: float


class FacilityRagService:
    """Provides isolated retrieval; it never falls back to sales knowledge."""

    def __init__(self, collection: Any | None = None):
        self._collection = collection
        self._unavailable_reason: str | None = None

    def _get_collection(self) -> Any | None:
        if self._collection is not None:
            return self._collection
        try:
            import chromadb

            os.makedirs(FACILITY_CHROMA_DIR, exist_ok=True)
            client = chromadb.PersistentClient(path=FACILITY_CHROMA_DIR)
            self._collection = client.get_or_create_collection(name=COLLECTION_NAME)
            return self._collection
        except Exception as exc:
            self._unavailable_reason = str(exc)
            return None

    def ensure_seeded(self) -> bool:
        collection = self._get_collection()
        if collection is None:
            return False
        try:
            if collection.count() > 0:
                return True
            collection.add(
                ids=[document["id"] for document in FACILITY_SEED_DOCUMENTS],
                documents=[document["text"] for document in FACILITY_SEED_DOCUMENTS],
                metadatas=[
                    {"source_id": document["id"], "title": document["title"], **document["metadata"]}
                    for document in FACILITY_SEED_DOCUMENTS
                ],
            )
            return True
        except Exception as exc:
            self._unavailable_reason = str(exc)
            return False

    def retrieve(self, query: str, top_k: int = 3) -> list[FacilityRetrievedChunk]:
        if not query or not query.strip() or not self.ensure_seeded():
            return []
        try:
            response = self._collection.query(query_texts=[query], n_results=min(top_k, self._collection.count()))
        except Exception as exc:
            self._unavailable_reason = str(exc)
            return []
        documents = response.get("documents", [[]])[0]
        distances = response.get("distances", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        chunks: list[FacilityRetrievedChunk] = []
        for document, distance, metadata in zip(documents, distances, metadatas):
            if distance > MAX_DISTANCE:
                continue
            metadata = metadata or {}
            chunks.append(FacilityRetrievedChunk(
                text=document,
                distance=float(distance),
                citation=FacilityCitation(
                    source_id=str(metadata.get("source_id") or metadata.get("id") or "unknown"),
                    title=str(metadata.get("title") or "Untitled facility document"),
                    document_type=str(metadata.get("document_type") or "procedure"),
                    revision=str(metadata.get("revision") or "unknown"),
                ),
            ))
        return chunks

    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason


def build_grounded_context(chunks: list[FacilityRetrievedChunk]) -> tuple[str, list[dict[str, str]]]:
    """Return prompt-ready evidence and display-ready sources without invented citations."""
    if not chunks:
        return (
            "No approved facility knowledge was retrieved. State that sufficient information was not found; do not invent a procedure.",
            [],
        )
    lines = ["APPROVED FACILITY KNOWLEDGE:"]
    citations: list[dict[str, str]] = []
    for chunk in chunks:
        citation = chunk.citation
        lines.append(f"[{citation.source_id}] {chunk.text}")
        citations.append({
            "source_id": citation.source_id, "title": citation.title,
            "document_type": citation.document_type, "revision": citation.revision,
        })
    return "\n".join(lines), citations
