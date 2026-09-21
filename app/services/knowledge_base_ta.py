"""Reviewed Tamil knowledge used by live voice calls.

The old implementation split ``knowledge_ta.txt`` with keyword heuristics.
Large sections were consequently assigned to unrelated collections, and formal
document prose leaked into speech.  Live calls now use only explicit,
fact-aligned chunks reviewed for conversational Tamil Nadu delivery.

``knowledge_ta.txt`` remains a reference/archive; it is deliberately not loaded
automatically into the production voice prompt.
"""

from typing import Any, Dict, List

from app.services.knowledge_uploaded_update import TA_UPDATES

KBDocument = Dict[str, Any]

REQUIRED_COLLECTIONS_TA = (
    "company",
    "founder",
    "courses",
    "internships",
    "services",
    "products",
    "career",
    "pricing",
    "contact",
    "enrollment",
)


def _reviewed_tamil_docs() -> Dict[str, List[KBDocument]]:
    docs = {
        collection: [dict(document) for document in TA_UPDATES.get(collection, [])]
        for collection in REQUIRED_COLLECTIONS_TA
    }
    missing = [collection for collection, items in docs.items() if not items]
    if missing:
        raise RuntimeError(
            "Reviewed Tamil knowledge is missing required collections: "
            + ", ".join(missing)
        )
    return docs


ALL_SEED_DOCS_TA: Dict[str, List[KBDocument]] = _reviewed_tamil_docs()
