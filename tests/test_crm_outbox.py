import hashlib
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.schemas.crm import CrmConnectionInput
from app.services import crm_outbox_service
from app.workers import crm_delivery_worker
from app.api import crm as crm_api


class CrmConnectionValidationTests(unittest.TestCase):
    def test_requires_https_and_rejects_private_destinations(self):
        for url in (
            "http://crm.example.com/hook",
            "https://localhost/hook",
            "https://127.0.0.1/hook",
            "https://10.1.2.3/hook",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    CrmConnectionInput(webhook_url=url, signing_secret="a" * 24)

    def test_accepts_public_https_destination(self):
        value = CrmConnectionInput(
            webhook_url="https://crm.example.com/webhooks/digidara",
            signing_secret="a" * 24,
        )
        self.assertEqual("https://crm.example.com/webhooks/digidara", value.webhook_url)


class CrmOutboxPersistenceTests(unittest.TestCase):
    def test_event_waits_for_configuration_and_is_idempotent(self):
        db = MagicMock()
        db.cursor.return_value.lastrowid = 15
        with patch.object(crm_outbox_service, "get_active_connection", return_value=None):
            event_id = crm_outbox_service.emit_event(
                db, organization_id=42, event_type="call_completed",
                aggregate_type="call_log", aggregate_id="99",
                payload={"call": {"id": 99}}, idempotency_key="call_completed:v1:99",
            )
        sql, params = db.cursor.return_value.execute.call_args.args
        self.assertIn("ON DUPLICATE KEY UPDATE", sql)
        self.assertIn("waiting_configuration", params)
        self.assertIn("call_completed:v1:99", params)
        self.assertEqual(15, event_id)
        db.commit.assert_called_once()

    def test_reemitting_the_same_idempotency_key_resets_delivery_state(self):
        """A corrected event (e.g. a call re-scored after its full recording
        was transcribed) must actually go out again, even if the first,
        rushed version already delivered or exhausted its retries -- a
        plain no-op duplicate would leave a connected CRM stuck with stale
        data forever."""
        db = MagicMock()
        db.cursor.return_value.lastrowid = 15
        with patch.object(crm_outbox_service, "get_active_connection", return_value={"id": 7}):
            crm_outbox_service.emit_event(
                db, organization_id=42, event_type="call_completed",
                aggregate_type="call_log", aggregate_id="99",
                payload={"call": {"id": 99, "qualification": "hot"}},
                idempotency_key="call_completed:v1:99",
            )
        sql, _params = db.cursor.return_value.execute.call_args.args
        for reset_field in ("payload_json=VALUES(payload_json)", "status=VALUES(status)", "attempts=0", "delivered_at=NULL"):
            self.assertIn(reset_field, sql)

    def test_event_can_join_the_call_transaction_without_early_commit(self):
        db = MagicMock()
        db.cursor.return_value.lastrowid = 15
        with patch.object(crm_outbox_service, "get_active_connection", return_value={"id": 4}):
            crm_outbox_service.emit_event(
                db, organization_id=42, event_type="call_completed",
                aggregate_type="call_log", aggregate_id="99",
                payload={"call": {"id": 99}}, idempotency_key="call_completed:v1:99",
                commit=False,
            )
        db.commit.assert_not_called()

    def test_manual_retry_is_tenant_scoped(self):
        db = MagicMock()
        db.cursor.return_value.rowcount = 1
        with patch.object(crm_outbox_service, "get_active_connection", return_value={"id": 4}):
            updated = crm_outbox_service.requeue_event(db, 42, 15)
        sql, params = db.cursor.return_value.execute.call_args.args
        self.assertIn("organization_id=%s", sql)
        self.assertEqual((4, 15, 42), params)
        self.assertTrue(updated)

    def test_claim_uses_skip_locked_for_parallel_workers(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchall.side_effect = [[{"id": 1}, {"id": 2}], [{"id": 1}, {"id": 2}]]
        rows = crm_outbox_service.claim_batch(db, worker_id="worker-a", limit=2)
        select_sql = cursor.execute.call_args_list[1].args[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", select_sql)
        self.assertEqual(2, len(rows))


class CrmWorkerTests(unittest.TestCase):
    def _event(self):
        return {
            "id": 15, "organization_id": 42, "event_type": "call_completed",
            "idempotency_key": "call_completed:v1:99",
            "payload_json": json.dumps({"call": {"id": 99}}, separators=(",", ":")),
            "is_active": True,
        }

    @patch("app.workers.crm_delivery_worker._assert_public_destination")
    @patch("app.workers.crm_delivery_worker.httpx.Client")
    @patch("app.workers.crm_delivery_worker.tenant_credentials_service.resolve_crm_webhook")
    @patch("app.workers.crm_delivery_worker.crm_outbox_service.mark_delivered")
    def test_successful_delivery_is_signed_and_marked_delivered(
        self, mark_delivered, resolve, client_class, public_destination,
    ):
        resolve.return_value = {
            "webhook_url": "https://crm.example.com/hook", "signing_secret": "secret-value-12345",
        }
        response = MagicMock(status_code=202)
        client_class.return_value.__enter__.return_value.post.return_value = response
        event = self._event()
        crm_delivery_worker.deliver_event(MagicMock(), event)
        _, kwargs = client_class.return_value.__enter__.return_value.post.call_args
        expected = hmac.new(
            b"secret-value-12345", event["payload_json"].encode(), hashlib.sha256,
        ).hexdigest()
        self.assertEqual(f"sha256={expected}", kwargs["headers"]["X-DigiDARA-Signature"])
        self.assertEqual("call_completed:v1:99", kwargs["headers"]["X-DigiDARA-Idempotency-Key"])
        mark_delivered.assert_called_once_with(unittest.mock.ANY, 15, 202)

    @patch("app.workers.crm_delivery_worker.socket.getaddrinfo")
    def test_private_dns_resolution_is_blocked(self, getaddrinfo):
        getaddrinfo.return_value = [(None, None, None, None, ("127.0.0.1", 443))]
        with self.assertRaises(ValueError):
            crm_delivery_worker._assert_public_destination("https://crm.example.com/hook")

    @patch("app.workers.crm_delivery_worker._assert_public_destination", side_effect=ValueError("private"))
    @patch("app.workers.crm_delivery_worker.tenant_credentials_service.resolve_crm_webhook")
    @patch("app.workers.crm_delivery_worker.crm_outbox_service.mark_failed")
    def test_invalid_destination_is_dead_lettered_without_retry(self, mark_failed, resolve, public_destination):
        resolve.return_value = {
            "webhook_url": "https://crm.example.com/hook", "signing_secret": "secret-value-12345",
        }
        crm_delivery_worker.deliver_event(MagicMock(), self._event())
        self.assertFalse(mark_failed.call_args.kwargs["retryable"])


class CrmConnectionTestTests(unittest.TestCase):
    @patch("app.workers.crm_delivery_worker._assert_public_destination")
    @patch("app.api.crm.httpx.Client")
    @patch("app.api.crm.tenant_credentials_service.resolve_crm_webhook")
    @patch("app.api.crm.crm_outbox_service.get_active_connection")
    def test_connection_probe_is_signed_and_records_success(self, get_connection, resolve, client_class, public_destination):
        get_connection.return_value = {"id": 4, "is_active": True}
        resolve.return_value = {
            "webhook_url": "https://crm.example.com/hook",
            "signing_secret": "secret-value-12345",
        }
        client_class.return_value.__enter__.return_value.post.return_value = MagicMock(status_code=204)
        db = MagicMock()
        result = crm_api.test_connection(admin={"organization_id": 42, "id": 3}, db=db)
        self.assertEqual({"status": "success", "response_status": 204}, result)
        _, kwargs = client_class.return_value.__enter__.return_value.post.call_args
        signature = hmac.new(b"secret-value-12345", kwargs["content"], hashlib.sha256).hexdigest()
        self.assertEqual(f"sha256={signature}", kwargs["headers"]["X-DigiDARA-Signature"])
        self.assertTrue(any("last_test_status='success'" in call.args[0] for call in db.cursor.return_value.execute.call_args_list))

    @patch("app.api.crm.tenant_credentials_service.resolve_crm_webhook", return_value=None)
    @patch("app.api.crm.crm_outbox_service.get_active_connection", return_value=None)
    def test_connection_probe_requires_active_configuration(self, get_connection, resolve):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as raised:
            crm_api.test_connection(admin={"organization_id": 42, "id": 3}, db=MagicMock())
        self.assertEqual(409, raised.exception.status_code)


class CrmSchemaTests(unittest.TestCase):
    def test_schema_has_durable_outbox_constraints(self):
        with open("schema.sql", encoding="utf-8") as handle:
            schema = handle.read()
        self.assertIn("CREATE TABLE IF NOT EXISTS crm_outbox", schema)
        self.assertIn("uq_crm_outbox_idempotency", schema)
        self.assertIn("idx_crm_outbox_claim", schema)


if __name__ == "__main__":
    unittest.main()
