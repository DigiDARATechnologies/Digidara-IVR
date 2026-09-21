"""Tests for organization-scoped BM25 retrieval on the live call path.

Every case here uses a mocked db cursor — no real database, no network.
"""

import unittest
from unittest.mock import MagicMock

from app.livekit_agent import memory_kb


def _db_with_rows(rows):
    db = MagicMock()
    cursor = MagicMock()
    db.cursor.return_value = cursor
    cursor.fetchall.return_value = rows
    return db


class LoadOrgChunksTests(unittest.TestCase):
    def test_parses_rows_into_documents_with_composite_ids(self):
        db = _db_with_rows([
            {"collection": "pricing", "doc_id": "refund_policy", "chunk_index": 0,
             "chunk_text": "Refunds within 45 days.", "metadata_json": '{"source": "upload"}'},
        ])
        docs = memory_kb._load_org_chunks(db, 12345, "en")
        self.assertEqual(1, len(docs))
        self.assertEqual("refund_policy__0", docs[0].id)
        self.assertEqual("Refunds within 45 days.", docs[0].text)
        self.assertEqual("pricing", docs[0].collection)
        self.assertEqual({"source": "upload"}, docs[0].metadata)

    def test_handles_missing_metadata_json(self):
        db = _db_with_rows([
            {"collection": "faq", "doc_id": "d1", "chunk_index": 0,
             "chunk_text": "text", "metadata_json": None},
        ])
        docs = memory_kb._load_org_chunks(db, 1, "en")
        self.assertEqual({}, docs[0].metadata)


class BuildCorpusOrgScopingTests(unittest.TestCase):
    def setUp(self):
        # Use distinct org ids per test to avoid cross-test cache collisions
        # on the module-level cache dicts. id(self) is never
        # DIGIDARA_ORGANIZATION_ID (1), so these represent a real customer.
        self._org = id(self)
        memory_kb.invalidate_org_index(self._org)
        memory_kb.invalidate_org_index(memory_kb.DIGIDARA_ORGANIZATION_ID)

    def test_no_organization_id_returns_seed_only_corpus_unchanged(self):
        baseline = memory_kb._build_corpus("en")
        again = memory_kb._build_corpus("en")
        self.assertEqual(len(baseline), len(again))
        self.assertTrue(all("__" not in doc.id for doc in baseline))

    def test_non_digidara_organization_without_db_gets_an_empty_corpus_not_digidara_content(self):
        corpus = memory_kb._build_corpus("en", organization_id=self._org, db=None)
        self.assertEqual(0, len(corpus))

    def test_non_digidara_organization_is_scoped_to_only_its_own_uploads(self):
        baseline_len = len(memory_kb._build_corpus("en"))
        self.assertGreater(baseline_len, 0)  # sanity: DigiDARA's own baseline isn't empty
        db = _db_with_rows([
            {"collection": "pricing", "doc_id": "acme_pricing", "chunk_index": 0,
             "chunk_text": "Acme charges 999 rupees per month.", "metadata_json": None},
        ])
        corpus = memory_kb._build_corpus("en", organization_id=self._org, db=db)
        self.assertEqual(1, len(corpus))
        self.assertEqual("acme_pricing__0", corpus[0].id)

    def test_digidara_own_org_still_gets_the_seed_baseline_merged_with_its_own_uploads(self):
        baseline_len = len(memory_kb._build_corpus("en"))
        db = _db_with_rows([
            {"collection": "pricing", "doc_id": "digidara_promo", "chunk_index": 0,
             "chunk_text": "Limited time offer on the GenAI course.", "metadata_json": None},
        ])
        corpus = memory_kb._build_corpus(
            "en", organization_id=memory_kb.DIGIDARA_ORGANIZATION_ID, db=db,
        )
        self.assertEqual(baseline_len + 1, len(corpus))
        self.assertTrue(any(doc.id == "digidara_promo__0" for doc in corpus))

    def test_result_is_cached_until_invalidated(self):
        db = _db_with_rows([
            {"collection": "pricing", "doc_id": "d1", "chunk_index": 0,
             "chunk_text": "text", "metadata_json": None},
        ])
        first = memory_kb._build_corpus("en", organization_id=self._org, db=db)
        self.assertEqual(1, len(first))
        # A second call with an empty-returning db should still hit cache,
        # not requery — proving the cache, not the db, served this call.
        empty_db = _db_with_rows([])
        second = memory_kb._build_corpus("en", organization_id=self._org, db=empty_db)
        self.assertEqual(len(first), len(second))

        memory_kb.invalidate_org_index(self._org, "en")
        third = memory_kb._build_corpus("en", organization_id=self._org, db=empty_db)
        self.assertEqual(0, len(third))


class SearchIsolationTests(unittest.TestCase):
    def setUp(self):
        self.org_a = id(self) + 1
        self.org_b = id(self) + 2
        memory_kb.invalidate_org_index(self.org_a)
        memory_kb.invalidate_org_index(self.org_b)

    def test_only_the_uploading_organization_sees_its_own_content(self):
        db_a = _db_with_rows([
            {"collection": "pricing", "doc_id": "zylo_refund", "chunk_index": 0,
             "chunk_text": "Zylo Widget refunds are honored within 45 days of purchase.",
             "metadata_json": None},
        ])
        db_b = _db_with_rows([])

        query = "what is the refund policy for the zylo widget"
        result_a = memory_kb.search(
            query, lang="en", organization_id=self.org_a, db=db_a, min_score=0.0,
        )
        result_b = memory_kb.search(
            query, lang="en", organization_id=self.org_b, db=db_b, min_score=0.0,
        )
        result_default = memory_kb.search(query, lang="en", min_score=0.0)

        self.assertIn("Zylo", result_a)
        self.assertNotIn("Zylo", result_b)
        self.assertNotIn("Zylo", result_default)

    def test_default_call_signature_is_unchanged_for_existing_callers(self):
        # Callers that never pass organization_id/db (chat.py, call.py,
        # groq_service.py, conversation_relay.py) must keep working exactly
        # as before.
        result = memory_kb.search("what courses do you offer", lang="en")
        self.assertIsInstance(result, str)


class GetFastContextOrgScopingTests(unittest.TestCase):
    """get_fast_context() is the once-per-call system-prompt injection —
    the second DigiDARA-hardcoded injection point flagged (but not fixed)
    when search() was first made organization-aware."""

    def setUp(self):
        self._org = id(self)
        memory_kb.invalidate_org_index(self._org)
        memory_kb.invalidate_org_index(memory_kb.DIGIDARA_ORGANIZATION_ID)

    def test_no_organization_id_still_returns_digidara_facts_for_legacy_callers(self):
        result = memory_kb.get_fast_context("en")
        self.assertIn("DigiDARA", result)
        self.assertIn("pricing_info", result)

    def test_digidara_own_org_still_gets_its_curated_facts(self):
        result = memory_kb.get_fast_context("en", organization_id=memory_kb.DIGIDARA_ORGANIZATION_ID)
        self.assertIn("DigiDARA", result)
        self.assertIn("pricing_info", result)

    def test_new_customer_organization_with_no_uploads_gets_an_empty_briefing(self):
        result = memory_kb.get_fast_context("en", organization_id=self._org, db=_db_with_rows([]))
        self.assertEqual("", result)

    def test_customer_organization_with_uploads_sees_only_its_own_content(self):
        db = _db_with_rows([
            {"collection": "pricing", "doc_id": "acme_pricing", "chunk_index": 0,
             "chunk_text": "Acme Corp charges 999 rupees per month for the Zylo Widget.",
             "metadata_json": None},
        ])
        result = memory_kb.get_fast_context("en", organization_id=self._org, db=db)
        self.assertIn("Zylo", result)
        self.assertNotIn("DigiDARA", result)
        self.assertIn("acme_pricing", result)


if __name__ == "__main__":
    unittest.main()
