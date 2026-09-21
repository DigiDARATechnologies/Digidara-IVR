"""Tests that the ChromaDB-backed /knowledge-base admin API (DigiDARA's own
dashboard-chat knowledge base) is restricted to DigiDARA's own workspace,
not visible or editable by customer organizations."""

import unittest

from fastapi import HTTPException

from app.api.rag import DIGIDARA_ORGANIZATION_ID, _require_digidara_workspace


class RequireDigidaraWorkspaceTests(unittest.TestCase):
    def test_allows_the_digidara_workspace(self):
        admin = {"organization_id": DIGIDARA_ORGANIZATION_ID}
        self.assertEqual(admin, _require_digidara_workspace(admin))

    def test_rejects_a_customer_organization(self):
        with self.assertRaises(HTTPException) as raised:
            _require_digidara_workspace({"organization_id": 42})
        self.assertEqual(403, raised.exception.status_code)

    def test_rejects_when_organization_id_is_missing(self):
        with self.assertRaises(HTTPException) as raised:
            _require_digidara_workspace({})
        self.assertEqual(403, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
