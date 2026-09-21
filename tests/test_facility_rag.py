"""Grounding and citation tests for the isolated Facility RAG service."""

import unittest

from app.facility.rag.service import FacilityRagService, build_grounded_context


class _Collection:
    def __init__(self):
        self.documents = []
        self.metadatas = []

    def count(self):
        return len(self.documents)

    def add(self, ids, documents, metadatas):
        self.documents.extend(documents)
        self.metadatas.extend(metadatas)

    def query(self, query_texts, n_results):
        return {
            "documents": [[self.documents[0], self.documents[1]]],
            "distances": [[0.2, 1.7]],
            "metadatas": [[self.metadatas[0], self.metadatas[1]]],
        }


class FacilityRagTests(unittest.TestCase):
    def test_retrieval_filters_weak_matches_and_keeps_traceable_source(self):
        chunks = FacilityRagService(_Collection()).retrieve("What should I check for AHU low airflow?")

        self.assertEqual(1, len(chunks))
        self.assertEqual("hvac_low_airflow_v1", chunks[0].citation.source_id)
        context, citations = build_grounded_context(chunks)
        self.assertIn("[hvac_low_airflow_v1]", context)
        self.assertEqual("AHU low-airflow troubleshooting procedure", citations[0]["title"])

    def test_no_evidence_instructs_the_caller_not_to_invent_a_procedure(self):
        context, citations = build_grounded_context([])

        self.assertEqual([], citations)
        self.assertIn("do not invent", context)


if __name__ == "__main__":
    unittest.main()
