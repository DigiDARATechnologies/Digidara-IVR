import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api.auth import AdminInput, create_admin, current_admin
from app.api.call import read_call_log
from app.api.chat import ChatRequest, website_assistant
from app.api.insights import analytics_report, dashboard_summary, usage_summary
from app.api.lead_score import get_customer_memory, list_lead_qualifications
from app.schemas.customer import CustomerCreate
from app.services import (
    call_log_service,
    campaign_service,
    customer_service,
    telephony_service,
)
from app.services.auth_service import decode_token, issue_token


class AuthenticationTenantContextTests(unittest.TestCase):
    def test_token_carries_signed_organization_context(self):
        user = {
            "id": 7,
            "organization_id": 42,
            "email": "admin@example.com",
            "role_code": "admin",
        }
        with patch.dict(os.environ, {"JWT_SECRET": "x" * 40}):
            claims = decode_token(issue_token(user))
        self.assertEqual(42, claims["organization_id"])

    def test_current_admin_rejects_token_database_tenant_mismatch(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = {
            "id": 7,
            "organization_id": 99,
            "email": "admin@example.com",
            "full_name": "Admin",
            "role_code": "admin",
            "is_active": True,
        }
        with patch("app.api.auth.decode_token", return_value={
            "sub": 7, "organization_id": 42,
        }):
            with self.assertRaises(HTTPException) as raised:
                current_admin("Bearer token", db)
        self.assertEqual(401, raised.exception.status_code)

    def test_created_admin_inherits_authenticated_organization(self):
        db = MagicMock()
        db.cursor.return_value.lastrowid = 18
        with patch("app.api.auth.hash_password", return_value="hash"):
            create_admin(
                AdminInput(
                    full_name="Second Admin",
                    email="second@example.com",
                    password="long-password",
                ),
                admin={"id": 7, "organization_id": 42},
                db=db,
            )
        first_insert = db.cursor.return_value.execute.call_args_list[0]
        audit_insert = db.cursor.return_value.execute.call_args_list[1]
        self.assertEqual(42, first_insert.args[1][0])
        self.assertEqual((42, 7, "18"), audit_insert.args[1])


class TenantScopedServiceTests(unittest.TestCase):
    def test_customer_reads_and_writes_include_organization(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None
        self.assertIsNone(customer_service.get_customer_by_id(db, 5, 42))
        read = db.cursor.return_value.execute.call_args
        self.assertIn("organization_id = %s", read.args[0])
        self.assertEqual((5, 42), read.args[1])

        with patch.object(
            customer_service, "get_customer_by_id", return_value={"id": 8}
        ) as get_created:
            customer_service.create_customer(
                db,
                42,
                CustomerCreate(
                    name="Tenant Customer", email="same@example.com",
                    language="english",
                ),
            )
        insert = db.cursor.return_value.execute.call_args
        self.assertIn("organization_id", insert.args[0])
        self.assertEqual(42, insert.args[1][0])
        get_created.assert_called_once_with(db, db.cursor.return_value.lastrowid, 42)

    def test_campaign_and_call_reads_include_organization(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None
        campaign_service.get_campaign_by_id(db, 3, 42)
        campaign_read = db.cursor.return_value.execute.call_args
        self.assertEqual((3, 42), campaign_read.args[1])

        call_log_service.get_call_log_by_id(db, 9, 42)
        call_read = db.cursor.return_value.execute.call_args
        self.assertIn("organization_id = %s", call_read.args[0])
        self.assertEqual((9, 42), call_read.args[1])

    def test_foreign_call_detail_is_returned_as_not_found(self):
        with patch(
            "app.api.call.call_log_service.get_call_log_by_id", return_value=None
        ) as lookup:
            with self.assertRaises(HTTPException) as raised:
                read_call_log(9, admin={"organization_id": 42}, db=MagicMock())
        self.assertEqual(404, raised.exception.status_code)
        lookup.assert_called_once_with(unittest.mock.ANY, 9, 42)

    def test_outbound_call_rejects_foreign_customer_or_campaign_context(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None
        provider = MagicMock()
        provider.name = "plivo"
        with patch.object(
            telephony_service, "get_telephony_provider", return_value=provider
        ):
            result = telephony_service.start_outbound_call(
                db, 42, 5, "9876543210", 3
            )
        self.assertEqual("invalid_context", result["status"])
        provider.create_call.assert_not_called()
        query = db.cursor.return_value.execute.call_args
        self.assertEqual((3, 42, 5, 42), query.args[1])


class TenantScopedAggregateTests(unittest.TestCase):
    @staticmethod
    def _empty_db():
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.return_value = {}
        cursor.fetchall.return_value = []
        return db

    def test_all_analytics_queries_receive_organization_filter(self):
        for function in (dashboard_summary, usage_summary, analytics_report):
            with self.subTest(function=function.__name__):
                db = self._empty_db()
                function(admin={"organization_id": 42}, db=db)
                for executed in db.cursor.return_value.execute.call_args_list:
                    sql, params = executed.args
                    self.assertIn("organization_id", sql)
                    self.assertIn(42, tuple(params))

    def test_indirect_lead_and_memory_queries_join_through_customer_tenant(self):
        db = self._empty_db()
        list_lead_qualifications(admin={"organization_id": 42}, db=db)
        qualification_query = db.cursor.return_value.execute.call_args
        self.assertIn("c.organization_id = %s", qualification_query.args[0])
        self.assertEqual(42, qualification_query.args[1][0])

        get_customer_memory(5, admin={"organization_id": 42}, db=db)
        memory_query = db.cursor.return_value.execute.call_args
        self.assertIn("JOIN customers", memory_query.args[0])
        self.assertEqual((5, 42), memory_query.args[1])

    def test_dashboard_assistant_filters_and_persists_same_organization(self):
        db = self._empty_db()
        with patch("app.api.chat._dashboard_reply", return_value="reply"):
            website_assistant(
                ChatRequest(message="metrics", page="dashboard"),
                admin={"id": 7, "organization_id": 42},
                db=db,
            )
        calls = db.cursor.return_value.execute.call_args_list
        for executed in calls[:4]:
            self.assertIn("organization_id", executed.args[0])
            self.assertIn(42, tuple(executed.args[1]))
        self.assertEqual(42, calls[-2].args[1][0])
        self.assertEqual(42, calls[-1].args[1][0])


if __name__ == "__main__":
    unittest.main()
