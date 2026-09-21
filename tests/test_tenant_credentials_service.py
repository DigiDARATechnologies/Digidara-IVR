"""Tests for per-tenant encrypted provider credential storage."""

import os
import unittest
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

from app.services import tenant_credentials_service as creds

TEST_KEY = Fernet.generate_key().decode()


class SetAndGetCredentialTests(unittest.TestCase):
    def _conn_returning(self, ciphertext_row):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = ciphertext_row
        return conn, cursor

    def test_set_credential_rejects_unknown_provider(self):
        conn = MagicMock()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": TEST_KEY}):
            with self.assertRaises(creds.UnknownProviderError):
                creds.set_credential(conn, 1, "twilio", {"api_key": "x"})

    def test_set_credential_rejects_all_blank_fields(self):
        conn = MagicMock()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": TEST_KEY}):
            with self.assertRaises(ValueError):
                creds.set_credential(conn, 1, "openai", {"api_key": "   "})

    def test_set_credential_requires_encryption_key(self):
        conn = MagicMock()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": ""}):
            with self.assertRaises(creds.CredentialEncryptionError):
                creds.set_credential(conn, 1, "openai", {"api_key": "sk-test"})

    def test_round_trip_encrypts_and_decrypts_correctly(self):
        conn, cursor = self._conn_returning(None)
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": TEST_KEY}):
            creds.set_credential(conn, 5, "openai", {"api_key": "sk-live-abcdef1234"})
            stored_ciphertext = cursor.execute.call_args[0][1][2]
            self.assertNotIn("sk-live", stored_ciphertext)

            cursor.fetchone.return_value = {"credential_ciphertext": stored_ciphertext}
            result = creds.get_credential(conn, 5, "openai")
        self.assertEqual(result["api_key"], "sk-live-abcdef1234")

    def test_get_credential_returns_none_when_not_configured(self):
        conn, _cursor = self._conn_returning(None)
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": TEST_KEY}):
            self.assertIsNone(creds.get_credential(conn, 1, "plivo"))

    def test_last_four_masks_a_configured_secret(self):
        conn, cursor = self._conn_returning(None)
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": TEST_KEY}):
            creds.set_credential(conn, 5, "openai", {"api_key": "sk-live-abcdef1234"})
        last_four = cursor.execute.call_args[0][1][4]
        self.assertEqual(last_four, "1234")


class ResolveCredentialFallbackTests(unittest.TestCase):
    def test_resolve_plivo_falls_back_to_env_when_nothing_stored(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = None
        with patch.dict(os.environ, {
            "DATA_ENCRYPTION_KEY": TEST_KEY,
            "PLIVO_AUTH_ID": "env-auth-id",
            "PLIVO_AUTH_TOKEN": "env-token",
            "PLIVO_FROM_NUMBER": "+10000000000",
        }):
            result = creds.resolve_plivo_credentials(conn, organization_id=1)
        self.assertEqual(result["auth_id"], "env-auth-id")

    def test_resolve_plivo_prefers_tenant_credentials_when_configured(self):
        conn = MagicMock()
        with patch.dict(os.environ, {
            "DATA_ENCRYPTION_KEY": TEST_KEY,
            "PLIVO_AUTH_ID": "env-auth-id",
        }), patch.object(
            creds, "get_credential",
            return_value={"auth_id": "tenant-auth-id", "auth_token": "tenant-token", "from_number": "+19999999999"},
        ):
            result = creds.resolve_plivo_credentials(conn, organization_id=1)
        self.assertEqual(result["auth_id"], "tenant-auth-id")

    def test_resolve_plivo_with_no_organization_id_uses_env_only(self):
        conn = MagicMock()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": TEST_KEY, "PLIVO_AUTH_ID": "env-auth-id"}), \
             patch.object(creds, "get_credential") as get_mock:
            result = creds.resolve_plivo_credentials(conn, organization_id=None)
        get_mock.assert_not_called()
        self.assertEqual(result["auth_id"], "env-auth-id")

    def test_resolve_openai_api_key_falls_back_to_env(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = None
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": TEST_KEY, "OPENAI_API_KEY": "env-key"}):
            self.assertEqual(creds.resolve_openai_api_key(conn, 1), "env-key")


class ListCredentialStatusTests(unittest.TestCase):
    def test_lists_every_provider_with_configured_flag(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            {"provider": "openai", "last_four": "1234", "rotated_at": "2026-08-07 10:00:00"}
        ]
        result = creds.list_credential_status(conn, 1)
        by_provider = {entry["provider"]: entry for entry in result}
        self.assertTrue(by_provider["openai"]["configured"])
        self.assertFalse(by_provider["plivo"]["configured"])
        self.assertIsNone(by_provider["plivo"]["last_four"])


if __name__ == "__main__":
    unittest.main()
