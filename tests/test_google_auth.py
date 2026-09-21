"""Tests for Google Sign-In credential verification and account resolution."""

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services import workspace_service
from app.services.auth_service import GoogleTokenError, WorkspaceRequiredError, verify_google_id_token


class VerifyGoogleIdTokenTests(unittest.TestCase):
    def test_rejects_when_client_id_not_configured(self):
        with patch.dict(os.environ, {"GOOGLE_OAUTH_CLIENT_ID": ""}):
            with self.assertRaises(GoogleTokenError):
                verify_google_id_token("some-credential")

    def test_returns_normalized_claims_for_a_valid_token(self):
        with patch.dict(os.environ, {"GOOGLE_OAUTH_CLIENT_ID": "client-123"}), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value={
                 "email": "Person@Example.com",
                 "email_verified": True,
                 "name": "Test Person",
                 "sub": "google-subject-1",
             }):
            claims = verify_google_id_token("valid-credential")
        self.assertEqual(claims["email"], "person@example.com")
        self.assertEqual(claims["full_name"], "Test Person")
        self.assertEqual(claims["google_subject"], "google-subject-1")

    def test_rejects_unverified_email(self):
        with patch.dict(os.environ, {"GOOGLE_OAUTH_CLIENT_ID": "client-123"}), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value={
                 "email": "person@example.com", "email_verified": False,
             }):
            with self.assertRaises(GoogleTokenError):
                verify_google_id_token("valid-credential")

    def test_wraps_library_verification_failure(self):
        with patch.dict(os.environ, {"GOOGLE_OAUTH_CLIENT_ID": "client-123"}), \
             patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("bad token")):
            with self.assertRaises(GoogleTokenError):
                verify_google_id_token("tampered-credential")


class FindOrCreateUserViaGoogleTests(unittest.TestCase):
    def _conn_with(self, fetchone_result):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = fetchone_result
        cursor.lastrowid = 55
        return conn, cursor

    def test_existing_single_org_user_signs_in_and_touches_last_login(self):
        conn, cursor = self._conn_with({
            "id": 9, "organization_id": 3, "email": "person@example.com",
            "full_name": "Person", "role_code": "admin", "is_active": 1,
            "workspace_slug": "acme", "organization_name": "Acme",
            "matching_accounts": 1,
        })
        user = workspace_service.find_or_create_user_via_google(
            conn, email="Person@Example.com", full_name="Person"
        )
        self.assertEqual(user["id"], 9)
        self.assertEqual(user["workspace_slug"], "acme")
        update_call = cursor.execute.call_args_list[-1]
        self.assertIn("last_login_at", update_call.args[0])
        conn.commit.assert_called()

    def test_ambiguous_email_across_workspaces_fails_closed(self):
        conn, _cursor = self._conn_with({
            "id": 9, "organization_id": 3, "email": "person@example.com",
            "full_name": "Person", "role_code": "admin", "is_active": 1,
            "workspace_slug": "acme", "organization_name": "Acme",
            "matching_accounts": 2,
        })
        with self.assertRaises(WorkspaceRequiredError):
            workspace_service.find_or_create_user_via_google(
                conn, email="person@example.com", full_name="Person"
            )

    def test_new_email_auto_provisions_a_workspace_with_no_password(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        # First fetchone: no existing app_user match. Second: slug-uniqueness
        # check finds nothing taken. lastrowid drives org id then user id.
        cursor.fetchone.side_effect = [None, None]
        cursor.lastrowid = 21
        user = workspace_service.find_or_create_user_via_google(
            conn, email="new.person@acme.com", full_name="New Person"
        )
        self.assertEqual(user["role_code"], "admin")
        self.assertEqual(user["email"], "new.person@acme.com")
        insert_calls = [c for c in cursor.execute.call_args_list if "INSERT INTO app_users" in c.args[0]]
        self.assertEqual(len(insert_calls), 1)
        self.assertIn("NULL", insert_calls[0].args[0])
        conn.commit.assert_called()


if __name__ == "__main__":
    unittest.main()
