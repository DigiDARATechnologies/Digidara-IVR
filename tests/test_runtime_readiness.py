import os
import unittest
from unittest.mock import MagicMock, patch

from app.services import runtime_readiness_service


class RuntimeReadinessTests(unittest.TestCase):
    def test_production_configuration_requires_stable_secure_values(self):
        values = {
            "ENVIRONMENT": "production", "PLIVO_AUTH_ID": "MA" + "x" * 18,
            "PLIVO_AUTH_TOKEN": "token", "PLIVO_FROM_NUMBER": "+919876543210",
            "OPENAI_API_KEY": "k" * 30, "JWT_SECRET": "j" * 32,
            "DATA_ENCRYPTION_KEY": "d" * 32, "PLIVO_VALIDATE_SIGNATURES": "true",
            "WEBHOOK_BASE_URL": "https://voice.example.com", "PLIVO_STREAM_BASE_URL": "wss://voice.example.com",
            "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        }
        with patch.dict(os.environ, values, clear=True):
            checks = {item["name"]: item["status"] for item in runtime_readiness_service.configuration_checks()}
        self.assertEqual("configured", checks["Public webhook and stream URLs"])
        self.assertEqual("configured", checks["Browser origin allow-list"])
        self.assertEqual("configured", checks["Plivo credentials"])

    def test_production_rejects_quick_tunnel_and_insecure_cors(self):
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production", "WEBHOOK_BASE_URL": "https://test.trycloudflare.com",
            "PLIVO_STREAM_BASE_URL": "wss://test.trycloudflare.com", "CORS_ALLOWED_ORIGINS": "http://localhost:5173",
        }, clear=True):
            checks = {item["name"]: item["status"] for item in runtime_readiness_service.configuration_checks()}
        self.assertEqual("action_required", checks["Public webhook and stream URLs"])
        self.assertEqual("action_required", checks["Browser origin allow-list"])

    def test_worker_heartbeat_uses_single_non_secret_record(self):
        db = MagicMock()
        runtime_readiness_service.record_worker_heartbeat(db, "crm_delivery", "worker-1")
        sql, values = db.cursor.return_value.execute.call_args.args
        self.assertIn("runtime_worker_heartbeats", sql)
        self.assertEqual(("crm_delivery", "worker-1"), values)
        db.commit.assert_called_once()

    def test_worker_check_marks_missing_heartbeat(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None
        self.assertEqual({"name": "CRM delivery worker", "status": "not_seen"}, runtime_readiness_service.worker_check(db))


if __name__ == "__main__":
    unittest.main()
