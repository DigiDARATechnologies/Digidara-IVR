"""
RAG (Retrieval-Augmented Generation) service backed by ChromaDB.

Design goals:
- Local, persistent vector store (no separate server to run/manage).
- Free, local embeddings (ChromaDB's bundled ONNX MiniLM model) — no extra
  API cost and no heavy ML framework (PyTorch/CUDA) dependency.
- Six required collections: company, services, courses, faq, pricing,
  internships — plus optional ones (case_studies, policies, contact)
  created on demand.
- NEVER let a RAG failure break a live phone call. Every public function in
  this module degrades gracefully: if ChromaDB or the embedding model can't
  be reached (e.g. first-run model download blocked by a firewall), the
  assistant simply proceeds without retrieved context instead of crashing
  the call. This is critical for production reliability.
"""

import os
import re
import threading
from typing import Dict, List, Optional, TypedDict

from app.services.knowledge_base import (
    ALL_SEED_DOCS,
    OPTIONAL_COLLECTIONS,
    REQUIRED_COLLECTIONS,
)

CHROMA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "chroma")
)

_client = None
_collections: Dict[str, "object"] = {}
_init_lock = threading.Lock()
_rag_available = True  # Flipped to False if Chroma/embeddings can't load.
_init_error: Optional[str] = None


class RetrievedChunk(TypedDict):
    text: str
    collection: str
    distance: float
    metadata: Dict[str, str]


def _get_client():
    """Lazily creates the persistent ChromaDB client (thread-safe)."""
    global _client, _rag_available, _init_error
    if _client is not None:
        return _client
    with _init_lock:
        if _client is not None:
            return _client
        try:
            import chromadb

            os.makedirs(CHROMA_DIR, exist_ok=True)
            _client = chromadb.PersistentClient(path=CHROMA_DIR)
            return _client
        except Exception as e:
            _rag_available = False
            _init_error = str(e)
            print(f"[RAG] ChromaDB failed to initialize, RAG will be disabled: {e}")
            return None


def _get_collection(name: str):
    """Gets or creates a named collection. Returns None if RAG is unavailable."""
    global _rag_available, _init_error
    if not _rag_available:
        return None
    if name in _collections:
        return _collections[name]
    client = _get_client()
    if client is None:
        return None
    try:
        col = client.get_or_create_collection(name=name)
        _collections[name] = col
        return col
    except Exception as e:
        _rag_available = False
        _init_error = str(e)
        print(f"[RAG] Failed to get/create collection '{name}': {e}")
        return None


def is_available() -> bool:
    """Whether RAG is currently usable. False after any init failure."""
    return _rag_available


def last_error() -> Optional[str]:
    return _init_error


def chunk_text(text: str, max_chars: int = 600, overlap: int = 80) -> List[str]:
    """
    Splits long text into overlapping chunks on sentence boundaries where
    possible, so each chunk stays semantically coherent for embedding.
    Short documents (most FAQ-style entries) return as a single chunk.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            # start new chunk, carrying a small overlap from the end of the
            # previous chunk for continuity
            tail = current[-overlap:] if current else ""
            current = f"{tail} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks or [text]


def ensure_seeded() -> None:
    """
    Ensures all required collections exist and are populated with the seed
    DigiDARA knowledge base content on first run. Safe to call on every
    backend startup — it only inserts documents that aren't already present
    (checked by collection document count), so re-running this never
    duplicates data.

    Fails fast: if the very first insert attempt fails (e.g. the embedding
    model couldn't be downloaded because of a restrictive firewall), RAG is
    disabled for the rest of the process instead of retrying the same
    failing call once per collection — that would otherwise add several
    seconds of dead time to backend startup with no benefit.
    """
    global _rag_available, _init_error
    if not is_available():
        return

    # Fast preflight: try a trivial embed on a throwaway collection first.
    # If the embedding backend (model download, etc.) is broken, this fails
    # in milliseconds instead of us discovering it mid-way through seeding
    # six collections with multiple documents each.
    client = _get_client()
    if client is None:
        return
    try:
        preflight_col = client.get_or_create_collection(name="rag-preflight-check")
        preflight_col.add(documents=["preflight check"], ids=["preflight_0"])
        client.delete_collection(name="rag-preflight-check")
    except Exception as e:
        _rag_available = False
        _init_error = str(e)
        print(
            f"[RAG] Preflight embedding check failed, disabling RAG for this "
            f"session: {e}\n"
            f"[RAG] The assistant will run without retrieved context until "
            f"the backend is restarted with working network access to "
            f"download the embedding model (commonly blocked by corporate "
            f"firewalls/proxies on first run)."
        )
        return

    for collection_name in REQUIRED_COLLECTIONS:
        if not is_available():
            break  # a previous iteration already disabled RAG; stop early

        col = _get_collection(collection_name)
        if col is None:
            continue
        docs = ALL_SEED_DOCS.get(collection_name, [])
        if not docs:
            continue
        try:
            existing_count = col.count()
        except Exception:
            existing_count = 0
        if existing_count > 0:
            continue  # already seeded

        ids, texts, metadatas = [], [], []
        for doc in docs:
            chunks = chunk_text(doc["text"])
            for idx, chunk in enumerate(chunks):
                ids.append(f"{doc['id']}__{idx}")
                texts.append(chunk)
                metadatas.append({**doc["metadata"], "source": "seed"})
        try:
            col.add(documents=texts, ids=ids, metadatas=metadatas)
            print(f"[RAG] Seeded collection '{collection_name}' with {len(texts)} chunk(s).")
        except Exception as e:
            _rag_available = False
            _init_error = str(e)
            print(
                f"[RAG] Failed to seed collection '{collection_name}': {e}\n"
                f"[RAG] Disabling RAG for this session — the assistant will run "
                f"without retrieved context until the backend is restarted with "
                f"working network access to download the embedding model. This "
                f"is most likely caused by a corporate firewall/proxy intercepting "
                f"the one-time ONNX model download on first run."
            )
            break


def add_document(
    collection_name: str,
    doc_id: str,
    text: str,
    metadata: Optional[Dict[str, str]] = None,
) -> int:
    """
    Chunks and inserts a new document into the given collection (creating
    the collection if it doesn't exist yet — supports the optional
    case_studies/policies/contact collections being created on first use).
    Returns the number of chunks inserted, or 0 if RAG is unavailable.
    """
    if not is_available():
        return 0
    col = _get_collection(collection_name)
    if col is None:
        return 0

    chunks = chunk_text(text)
    ids = [f"{doc_id}__{i}" for i in range(len(chunks))]
    metadatas = [{**(metadata or {}), "source": metadata.get("source", "uploaded") if metadata else "uploaded"} for _ in chunks]
    try:
        col.upsert(documents=chunks, ids=ids, metadatas=metadatas)
        return len(chunks)
    except Exception as e:
        print(f"[RAG] Failed to add document '{doc_id}' to '{collection_name}': {e}")
        return 0


def delete_document(collection_name: str, doc_id: str) -> bool:
    """Deletes all chunks belonging to a document (by id prefix)."""
    if not is_available():
        return False
    col = _get_collection(collection_name)
    if col is None:
        return False
    try:
        existing = col.get()
        ids_to_delete = [i for i in existing.get("ids", []) if i.startswith(f"{doc_id}__") or i == doc_id]
        if ids_to_delete:
            col.delete(ids=ids_to_delete)
        return True
    except Exception as e:
        print(f"[RAG] Failed to delete document '{doc_id}' from '{collection_name}': {e}")
        return False


def list_documents(collection_name: str) -> List[Dict[str, str]]:
    """Lists distinct document ids (by stripping the __chunkindex suffix) in a collection."""
    if not is_available():
        return []
    col = _get_collection(collection_name)
    if col is None:
        return []
    try:
        existing = col.get()
        seen: Dict[str, Dict[str, str]] = {}
        ids = existing.get("ids", [])
        metadatas = existing.get("metadatas", [{}] * len(ids))
        documents = existing.get("documents", [""] * len(ids))
        for i, full_id in enumerate(ids):
            base_id = full_id.split("__")[0]
            if base_id not in seen:
                seen[base_id] = {
                    "id": base_id,
                    "preview": (documents[i][:120] if i < len(documents) else ""),
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                }
        return list(seen.values())
    except Exception as e:
        print(f"[RAG] Failed to list documents in '{collection_name}': {e}")
        return []


# Collections searched by default for a general customer question, in
# priority order. FAQ first since it tends to have the most direct
# question-shaped matches.
DEFAULT_SEARCH_COLLECTIONS = [
    "company",
    "courses",
    "internships",
    "services",
    "products",
    "career",
    "contact",
    "enrollment",
    "pricing",
    "founder",
]


def retrieve(
    query: str,
    collections: Optional[List[str]] = None,
    top_k: int = 3,
    max_distance: float = 1.5,
) -> List[RetrievedChunk]:
    """
    Retrieves the most relevant chunks for a query across the given
    collections (or DEFAULT_SEARCH_COLLECTIONS if none specified).

    `max_distance` filters out weak/irrelevant matches — ChromaDB's default
    distance metric is L2, where LOWER means more similar. Chunks above
    this threshold are dropped so the assistant doesn't ground its answer
    in an unrelated FAQ entry just because it was the "least bad" match.

    Returns an empty list (never raises) if RAG is unavailable or nothing
    relevant is found — callers should treat an empty list as "no grounding
    available" and apply the no-hallucination prompt rule.
    """
    if not is_available() or not query or not query.strip():
        return []

    target_collections = collections or DEFAULT_SEARCH_COLLECTIONS
    results: List[RetrievedChunk] = []

    for collection_name in target_collections:
        col = _get_collection(collection_name)
        if col is None:
            continue
        try:
            count = col.count()
            if count == 0:
                continue
            res = col.query(query_texts=[query], n_results=min(top_k, count))
        except Exception as e:
            print(f"[RAG] Query failed on collection '{collection_name}': {e}")
            continue

        docs = res.get("documents", [[]])[0]
        distances = res.get("distances", [[]])[0]
        metadatas = res.get("metadatas", [[]])[0]

        for doc, dist, meta in zip(docs, distances, metadatas):
            if dist <= max_distance:
                results.append({
                    "text": doc,
                    "collection": collection_name,
                    "distance": dist,
                    "metadata": meta or {},
                })

    # Sort by relevance (lowest distance = most similar) across all
    # searched collections combined, then keep only the strongest matches.
    results.sort(key=lambda r: r["distance"])
    return results[: top_k * 2]


def build_context_block(chunks: List[RetrievedChunk]) -> str:
    """
    Formats retrieved chunks into a system-prompt-ready context block.
    Returns an empty string if there are no chunks, so callers can check
    `if context:` to decide whether grounded info was found at all.
    """
    if not chunks:
        return ""
    lines = ["RETRIEVED KNOWLEDGE (use ONLY this information to answer factual questions):"]
    for chunk in chunks:
        lines.append(f"- {chunk['text']}")
    return "\n".join(lines)
