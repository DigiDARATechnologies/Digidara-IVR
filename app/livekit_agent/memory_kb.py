"""
In-memory BM25 knowledge base — replaces ChromaDB for the real-time call path.
Language-specific approved documents with millisecond local retrieval.
Pure Python stdlib, zero network calls and zero vector-database dependency.
"""

import json
import math
import re
import string
from typing import Any, Dict, List, Optional, Tuple

from app.services.knowledge_base import ALL_SEED_DOCS
from app.services.knowledge_base_ta import ALL_SEED_DOCS_TA

# `organizations.id=1` is seeded as a fixed row (see app/database/db.py
# init_db()) and is always DigiDARA's own workspace — never a customer's.
DIGIDARA_ORGANIZATION_ID = 1


class Document:
    __slots__ = ("id", "text", "collection", "metadata")
    def __init__(self, id, text, collection, metadata):
        self.id, self.text, self.collection, self.metadata = id, text, collection, metadata


_CORPUS_CACHE: Dict[Tuple[Optional[int], str], List[Document]] = {}


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return [t for t in text.split() if len(t) > 1]


def _normalize_lang(lang: str = "en") -> str:
    normalized = (lang or "en").strip().lower()
    if normalized in {"ta", "ta-in", "tamil"}:
        return "ta"
    return "en"


_TA_QUERY_EXPANSIONS = {
    "fee": "கட்டணம் விலை fees pricing",
    "fees": "கட்டணம் விலை fees pricing",
    "cost": "கட்டணம் விலை fees pricing",
    "price": "கட்டணம் விலை fees pricing",
    "evlo": "எவ்வளவு கட்டணம் விலை fees",
    "evalo": "எவ்வளவு கட்டணம் விலை fees",
    "evolo": "எவ்வளவு கட்டணம் விலை fees",
    "evvalavu": "எவ்வளவு கட்டணம் விலை fees",
    "kaasu": "காசு கட்டணம் விலை fees",
    "amount": "கட்டணம் விலை fees amount",
    "duration": "காலம் duration எத்தனை மாதம்",
    "months": "மாதம் duration காலம்",
    "naal": "நாள் duration காலம்",
    "maasam": "மாதம் duration காலம்",
    "placement": "வேலைவாய்ப்பு career placement resume linkedin interview",
    "job": "வேலைவாய்ப்பு career placement",
    "velai": "வேலை வேலைவாய்ப்பு career placement",
    "irukka": "இருக்கா உள்ளது இருக்கிறது",
    "iruku": "இருக்கு உள்ளது இருக்கிறது",
    "enga": "எங்கே முகவரி location address திருச்சி",
    "where": "எங்கே முகவரி location address",
    "office": "முகவரி location address office",
    "contact": "தொடர்பு தொலைபேசி whatsapp email",
    "phone": "தொலைபேசி contact",
    "whatsapp": "வாட்ஸ்அப் whatsapp தொடர்பு",
    "course": "கோர்ஸ் பயிற்சி training course",
    "courses": "கோர்ஸ் பயிற்சி training course",
    "details": "விவரம் டீடெயில்ஸ் details",
    "detail": "விவரம் டீடெயில்ஸ் details",
    "syllabus": "பாடத்திட்டம் syllabus topics modules",
    "internship": "இன்டர்ன்ஷிப் internship project",
    "certificate": "சான்றிதழ் certificate certification",
    "demo": "டெமோ demo book enroll register",
    "join": "சேர்வது சேர enroll register join",
    "seranum": "சேரணும் சேர்வது enroll register join",
    "batch": "batch வகுப்பு timing date",
    "timing": "timing நேரம் batch date",
    "online": "online இணையவழி mode",
    "offline": "offline நேரடி வகுப்பு திருச்சி mode",
    "weekend": "weekend சனி ஞாயிறு batch timing",
    "beginner": "beginner basics foundation prior experience suitable ஆரம்பநிலை",
    "fresher": "beginner basics foundation prior experience suitable ஆரம்பநிலை",
    "basic": "beginner basics foundation prior experience suitable ஆரம்பநிலை",
    "experience": "prior experience beginner eligibility basics",
    "chatbot": "chatbot whatsapp website virtual assistant customer support lead capture",
    "agent": "AI agent LangChain LangGraph RAG automation",
    "services": "business services consulting chatbot agent digital marketing",
    "service": "business services consulting chatbot agent digital marketing",
    "product": "products AI CRM Lead Flux AI Academy Career Mate College GPT automation",
    "lead flux": "Lead Flux product lead tracking high intent conversion",
    "leadflux": "Lead Flux product lead tracking high intent conversion",
    "founder": "founder Senthil Rajamarthandan நிறுவனர்",
    "iso": "ISO certification quality information security service management",
}


def _expand_query(query: str, lang: str = "en") -> str:
    if _normalize_lang(lang) != "ta":
        return query
    lowered = (query or "").lower()
    extra = []
    for key, expansion in _TA_QUERY_EXPANSIONS.items():
        if key in lowered:
            extra.append(expansion)
    return f"{query} {' '.join(extra)}".strip()


def _preferred_collections(query: str, lang: str = "en") -> List[str]:
    if _normalize_lang(lang) != "ta":
        return []
    lowered = (query or "").lower()
    preferences = []
    if any(word in lowered for word in ["internship", "இன்டர்ன", "இண்டர்ன"]):
        preferences.append("internships")
    if any(word in lowered for word in ["placement", "job", "career", "வேலை", "வேலைவாய்ப்பு"]):
        preferences.append("career")
    if any(word in lowered for word in [
        "fee", "fees", "cost", "price", "amount", "evlo", "evalo", "evolo",
        "evvalavu", "kaasu", "கட்டணம்", "விலை", "காசு", "எவ்வளவு",
    ]):
        preferences.append("pricing")
    if any(word in lowered for word in ["contact", "phone", "whatsapp", "office", "enga", "where", "முகவரி", "தொடர்பு"]):
        preferences.append("contact")
    if any(word in lowered for word in [
        "course", "courses", "duration", "syllabus", "batch", "timing",
        "online", "offline", "maasam", "naal", "beginner", "fresher",
        "basic", "கோர்ஸ்", "பயிற்சி", "மாதம்", "ஆரம்பநிலை",
    ]):
        preferences.append("courses")
    if any(word in lowered for word in [
        "service", "services", "chatbot", "consulting", "digital marketing",
        "ai agent", "business solution", "சேவை", "சாட்பாட்",
    ]):
        preferences.append("services")
    if any(word in lowered for word in [
        "product", "lead flux", "leadflux", "ai crm", "career mate",
        "college gpt", "academy", "தயாரிப்பு",
    ]):
        preferences.append("products")
    if any(word in lowered for word in ["founder", "senthil", "நிறுவனர்"]):
        preferences.append("founder")
    if any(word in lowered for word in [
        "company", "digidara", "iso", "certification", "நிறுவனம்",
    ]):
        preferences.append("company")
    return preferences


def _seed_docs_for(lang: str):
    return ALL_SEED_DOCS_TA if _normalize_lang(lang) == "ta" else ALL_SEED_DOCS


def _load_org_chunks(db: Any, organization_id: int, lang: str) -> List[Document]:
    """Reads one organization's own uploaded chunks from `knowledge_chunks`.

    This is the only place a DB round trip happens in this module, and it
    only runs on a cache miss (first use after startup or after an upload
    invalidates the cache) — not on the per-turn retrieval hot path.
    """
    cursor = db.cursor()
    cursor.execute(
        """SELECT collection, doc_id, chunk_index, chunk_text, metadata_json
           FROM knowledge_chunks WHERE organization_id=%s AND lang=%s
           ORDER BY doc_id, chunk_index""",
        (organization_id, lang),
    )
    docs: List[Document] = []
    for row in cursor.fetchall():
        metadata = json.loads(row["metadata_json"]) if row.get("metadata_json") else {}
        docs.append(Document(
            f"{row['doc_id']}__{row['chunk_index']}", row["chunk_text"], row["collection"], metadata,
        ))
    return docs


def _build_corpus(lang: str = "en", organization_id: Optional[int] = None, db: Any = None) -> List[Document]:
    """Builds one organization's live-call corpus.

    The hardcoded DigiDARA seed content is DigiDARA's own business
    information (courses, pricing, founder, ISO certs) — it is only ever
    included for DigiDARA's own workspace (`DIGIDARA_ORGANIZATION_ID`) or
    for unscoped legacy callers that pass no `organization_id` at all
    (today's pre-multi-tenant behavior, preserved for `chat.py`/`call.py`/
    `groq_service.py`). Every other organization's corpus is built purely
    from its own uploaded `knowledge_chunks` — DigiDARA's content never
    bleeds into another organization's live calls, even as a "starter"
    default.
    """
    lang_key = _normalize_lang(lang)
    cache_key = (organization_id, lang_key)
    if cache_key in _CORPUS_CACHE:
        return _CORPUS_CACHE[cache_key]

    include_seed = organization_id is None or organization_id == DIGIDARA_ORGANIZATION_ID
    corpus: List[Document] = []
    if include_seed:
        for collection, docs in _seed_docs_for(lang_key).items():
            for doc in docs:
                corpus.append(Document(doc["id"], doc["text"], collection, doc.get("metadata", {})))

    if organization_id is not None:
        if db is not None:
            corpus.extend(_load_org_chunks(db, organization_id, lang_key))
            print(f"[InMemoryKB] Loaded {len(corpus)} {lang_key} documents into RAM for org {organization_id}.")
        else:
            print(
                f"[InMemoryKB] organization_id={organization_id} requested with no db connection — "
                f"serving {'the DigiDARA baseline' if include_seed else 'an empty corpus'} for this build."
            )
    else:
        print(f"[InMemoryKB] Loaded {len(corpus)} {lang_key} documents into RAM.")

    _CORPUS_CACHE[cache_key] = corpus
    return corpus


class _BM25Index:
    def __init__(self, corpus: List[Document], k1: float = 1.5, b: float = 0.75):
        self._docs = corpus
        self._k1, self._b = k1, b
        self._tf: List[Dict[str, float]] = []
        self._df: Dict[str, int] = {}
        self._avgdl = 0.0
        self._N = len(corpus)
        self._build()

    def _build(self):
        total_len = 0
        for doc in self._docs:
            tokens = _tokenize(doc.text)
            total_len += len(tokens)
            tf: Dict[str, float] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            self._tf.append(tf)
            for t in set(tokens):
                self._df[t] = self._df.get(t, 0) + 1
        self._avgdl = total_len / max(self._N, 1)

    def query(self, q: str, top_k: int = 4) -> List[Tuple[float, Document]]:
        tokens = _tokenize(q)
        if not tokens:
            return []
        scores = [0.0] * self._N
        for token in tokens:
            df = self._df.get(token, 0)
            if df == 0:
                continue
            idf = math.log((self._N - df + 0.5) / (df + 0.5) + 1)
            for i, tf_map in enumerate(self._tf):
                tf = tf_map.get(token, 0)
                if tf == 0:
                    continue
                dl = sum(tf_map.values())
                score = idf * (tf * (self._k1 + 1)) / (
                    tf + self._k1 * (1 - self._b + self._b * dl / self._avgdl)
                )
                scores[i] += score
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(scores[i], self._docs[i]) for i, s in ranked[:top_k] if s > 0]


_INDEX_CACHE: Dict[Tuple[Optional[int], str], _BM25Index] = {}


def get_index(lang: str = "en", organization_id: Optional[int] = None, db: Any = None) -> _BM25Index:
    lang_key = _normalize_lang(lang)
    cache_key = (organization_id, lang_key)
    if cache_key not in _INDEX_CACHE:
        corpus = _build_corpus(lang_key, organization_id, db)
        _INDEX_CACHE[cache_key] = _BM25Index(corpus)
        label = f"org {organization_id}" if organization_id is not None else "shared baseline"
        print(f"[InMemoryKB] {lang_key} BM25 index built for {label}.")
    return _INDEX_CACHE[cache_key]


def invalidate_org_index(organization_id: int, lang: Optional[str] = None) -> None:
    """Evicts a stale cached corpus/index after an organization's knowledge
    base changes, so the next call rebuilds it from `knowledge_chunks`."""
    langs = [_normalize_lang(lang)] if lang else ["en", "ta"]
    for lang_key in langs:
        cache_key = (organization_id, lang_key)
        _CORPUS_CACHE.pop(cache_key, None)
        _INDEX_CACHE.pop(cache_key, None)


_SIMPLE_TURNS = {
    "yes", "yeah", "yep", "sure", "ok", "okay", "alright", "fine",
    "no", "nope", "not really", "got it", "i see", "understood",
    "of course", "definitely", "absolutely", "sounds good", "perfect",
    "great", "nice", "cool", "thank you", "thanks", "bye", "goodbye",
    "next week", "next month", "tomorrow", "today",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "morning", "evening", "afternoon",
    "ஆமா", "சரி", "ஓகே", "இல்ல", "இல்லை", "நன்றி", "சரிங்க", "ஆமாங்க", "பரவாயில்ல",
}

_KNOWLEDGE_NOUNS = {
    "course", "courses", "internship", "internships", "fee", "fees", "cost",
    "price", "service", "services", "product", "products", "certificate",
    "training", "program", "programs", "batch", "syllabus", "founder",
    "contact", "location", "address", "demo", "enroll", "register",
    "chatbot", "agent", "consulting", "digital", "marketing", "python",
    "data", "science", "analytics", "ai", "ml", "genai", "placement",
    "job", "career", "office", "phone", "whatsapp", "duration", "details",
    "evlo", "evalo", "enga",
    "கோர்ஸ்", "இண்டர்ன்ஷிப்", "கட்டணம்", "முகவரி", "தொடர்பு", "வேலைவாய்ப்பு",
}


def is_simple_turn(text: str) -> bool:
    normalized = text.strip().lower().rstrip(".,!?")
    if normalized in _SIMPLE_TURNS:
        return True
    words = normalized.split()
    if len(words) <= 2:
        if any(w in _KNOWLEDGE_NOUNS for w in words):
            return False
        return True
    if len(words) == 3 and "?" not in text:
        if any(w in _KNOWLEDGE_NOUNS for w in words):
            return False
        return True
    return False


def search(
    query: str, lang: str = "en", top_k: int = 3, min_score: float = 0.2,
    organization_id: Optional[int] = None, db: Any = None,
) -> str:
    """BM25 search — 0.1-0.2ms, no network, no ChromaDB.

    Pass `organization_id` (and a `db` connection) to search that
    organization's own uploaded content. DigiDARA's own hardcoded content
    is only included for DigiDARA's own workspace (`DIGIDARA_ORGANIZATION_ID`)
    or for callers that omit `organization_id` entirely (today's pre-
    multi-tenant behavior, kept for existing callers that don't yet pass
    one) — every other organization gets a corpus built purely from its
    own uploads, never DigiDARA's business content as a fallback.
    """
    if is_simple_turn(query):
        return ""
    lang_key = _normalize_lang(lang)
    index = get_index(lang_key, organization_id, db)
    expanded_query = _expand_query(query, lang_key)
    results = index.query(expanded_query, top_k=max(top_k * 4, top_k))
    preferred = _preferred_collections(query, lang_key)
    if preferred:
        results = sorted(
            results,
            key=lambda item: item[0] + (3.0 if item[1].collection in preferred else 0.0),
            reverse=True,
        )
    results = results[:top_k]
    if not results:
        return ""
    lines = ["DigiDara Tamil Knowledge Base:" if lang_key == "ta" else "DigiDara Knowledge Base:"]
    for score, doc in results:
        if score >= min_score:
            text = doc.text[:500] if len(doc.text) > 500 else doc.text
            lines.append(f"- {text}")
    return "\n".join(lines) if len(lines) > 1 else ""


def get_full_context_for_system_prompt(lang: str = "en") -> str:
    """Returns compact DigiDara knowledge for injection into the system prompt once per call."""
    lang_key = _normalize_lang(lang)
    corpus = _build_corpus(lang_key)

    if lang_key == "ta":
        lines = ["=== DigiDara Technologies Tamil Knowledge Base ==="]
        priority_collections = [
            "company", "courses", "internships", "services", "products",
            "career", "pricing", "contact", "enrollment", "founder",
        ]
        seen_collections = set()
        for collection in priority_collections:
            for doc in corpus:
                if doc.collection == collection and collection not in seen_collections:
                    seen_collections.add(collection)
                    lines.append(f"\n[{doc.collection.upper()}]\n{doc.text[:1800]}")
                    break
        return "\n".join(lines)

    priority_ids = [
        "company_overview", "company_quick_facts", "company_mission_vision",
        "courses_overview", "course_genai_agentic", "course_ai_ml",
        "course_data_science", "course_digital_marketing",
        "internship_overview", "internship_tracks",
        "services_overview", "products_overview",
        "career_support_overview", "contact_details",
        "book_demo", "pricing_info", "founder_profile",
    ]
    lines = ["=== DigiDara Technologies Knowledge Base ==="]
    seen = set()
    for doc in corpus:
        if doc.id in priority_ids and doc.id not in seen:
            seen.add(doc.id)
            lines.append(f"\n[{doc.collection.upper()}]\n{doc.text}")
    return "\n".join(lines)


_FAST_CONTEXT_PRIORITY = (
    "pricing_info",
    "contact_details",
    "book_demo",
    "enrollment_process",
    "company_overview",
    "courses_overview",
    "course_data_science",
    "course_ai_ml",
    "course_genai_agentic",
    "course_digital_marketing",
    "course_python_fullstack",
    "course_ai_managers",
    "uploaded_ai_systems_engineer",
    "uploaded_business_masterclass",
    "internship_overview",
    "internship_tracks",
    "services_overview",
    "products_overview",
    "career_support_overview",
    "founder_profile",
)


def _canonical_id(doc: Document) -> str:
    return str(doc.metadata.get("canonical_id") or doc.id)


def get_fast_context(
    lang: str = "en", max_chars: int = 7000,
    organization_id: Optional[int] = None, db: Any = None,
) -> str:
    """Small approved bilingual core injected once per call, at call start.

    DigiDARA's own curated "approved facts" (the `source_marker`/priority-id
    filtering below) apply only to DigiDARA's own workspace — or to
    unscoped legacy callers that pass no `organization_id`, preserving
    today's behavior for them. A customer organization gets everything
    from its own corpus instead, since `_build_corpus` already excludes
    DigiDARA's content for any organization other than DigiDARA's own —
    there's no separate "approved" curation step needed for an org's own
    uploads, and none of DigiDARA's business facts get injected as a
    fallback.
    """
    lang_key = _normalize_lang(lang)
    corpus = _build_corpus(lang_key, organization_id, db)
    is_digidara = organization_id is None or organization_id == DIGIDARA_ORGANIZATION_ID

    if is_digidara:
        source_marker = "user_master_knowledge_tamil" if lang_key == "ta" else "user_master_knowledge"
        approved = [
            doc
            for doc in corpus
            if doc.metadata.get("source") == source_marker
            or doc.id in {"pricing_info", "contact_details", "book_demo", "enrollment_process"}
        ]
        priority = {canonical_id: rank for rank, canonical_id in enumerate(_FAST_CONTEXT_PRIORITY)}
        selected = sorted(
            approved,
            key=lambda doc: (priority.get(_canonical_id(doc), len(priority)), _canonical_id(doc)),
        )
        preamble = (
            "DigiDARA approved facts. Use them to answer the latest question; "
            "do not read or list this text verbatim:"
        )
    else:
        selected = corpus
        preamble = (
            "Approved facts. Use them to answer the latest question; "
            "do not read or list this text verbatim:"
        )

    lines = [preamble]
    seen = set()
    for doc in selected:
        canonical_id = _canonical_id(doc)
        if canonical_id in seen:
            continue
        addition = f"\n[{doc.collection}:{canonical_id}] {doc.text}"
        if sum(len(line) for line in lines) + len(addition) > max_chars:
            continue
        seen.add(canonical_id)
        lines.append(addition)
    return "".join(lines) if len(lines) > 1 else ""
