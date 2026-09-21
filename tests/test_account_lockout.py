import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api.auth import LoginInput, login
from app.services.auth_service import account_lockout_policy


class AccountLockoutTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "AUTH_MAX_FAILED_LOGIN_ATTEMPTS": "3",
            "AUTH_ACCOUNT_LOCKOUT_SECONDS": "60",
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    @staticmethod
    def _user(**overrides):
        user = {
            "id": 7,
            "organization_id": 9,
            "organization_name": "Test Organization",
            "workspace_slug": "test-workspace",
            "email": "admin@example.com",
            "password_hash": "stored-hash",
            "full_name": "Admin User",
            "role_code": "admin",
            "is_active": True,
            "failed_login_attempts": 0,
            "locked_until": None,
            "is_locked": 0,
            "matching_accounts": 1,
        }
        user.update(overrides)
        return user

    def test_threshold_failure_atomically_locks_and_returns_retry_time(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.side_effect = [
            self._user(failed_login_attempts=2),
            {"failed_login_attempts": 3, "is_locked": 1, "retry_after_seconds": 60},
        ]
        with patch("app.services.auth_service.verify_password", return_value=False):
            with self.assertRaises(HTTPException) as raised:
                login(LoginInput(email="ADMIN@example.com", password="wrong"), db)

        self.assertEqual(429, raised.exception.status_code)
        self.assertEqual(60, raised.exception.detail["retry_after_seconds"])
        self.assertEqual("60", raised.exception.headers["Retry-After"])
        update = db.cursor.return_value.execute.call_args_list[1]
        self.assertIn("failed_login_attempts=failed_login_attempts+1", update.args[0])
        self.assertIn("TIMESTAMPADD", update.args[0])
        self.assertEqual((3, 60, 7), update.args[1])
        db.commit.assert_called_once()

    def test_pre_threshold_failure_returns_authoritative_remaining_attempts(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.side_effect = [
            self._user(failed_login_attempts=0),
            {"failed_login_attempts": 1, "is_locked": 0, "retry_after_seconds": 0},
        ]
        with patch("app.services.auth_service.verify_password", return_value=False):
            with self.assertRaises(HTTPException) as raised:
                login(LoginInput(email="admin@example.com", password="wrong"), db)

        self.assertEqual(401, raised.exception.status_code)
        self.assertEqual(2, raised.exception.detail["attempts_remaining"])

    def test_locked_account_is_rejected_before_password_verification(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = self._user(
            is_locked=1, retry_after_seconds=321
        )
        with patch("app.services.auth_service.verify_password") as verify:
            with self.assertRaises(HTTPException) as raised:
                login(LoginInput(email="admin@example.com", password="correct"), db)

        self.assertEqual(429, raised.exception.status_code)
        self.assertEqual("account_locked", raised.exception.detail["code"])
        self.assertEqual(321, raised.exception.detail["retry_after_seconds"])
        verify.assert_not_called()
        db.commit.assert_not_called()

    def test_three_failures_block_the_next_attempt_even_with_correct_password(self):
        state = {"failed": 0, "locked": False}
        cursor = MagicMock()

        def execute(sql, params):
            if sql.lstrip().startswith("SELECT"):
                cursor.fetchone.return_value = self._user(
                    failed_login_attempts=state["failed"],
                    is_locked=int(state["locked"]),
                )
            elif "failed_login_attempts=failed_login_attempts+1" in sql:
                state["failed"] += 1
                if state["failed"] >= params[0]:
                    state["locked"] = True
            elif "failed_login_attempts=0" in sql:
                state.update(failed=0, locked=False)

        cursor.execute.side_effect = execute
        db = MagicMock()
        db.cursor.return_value = cursor
        with patch(
            "app.services.auth_service.verify_password",
            side_effect=lambda password, _: password == "correct",
        ) as verify:
            for _ in range(2):
                with self.assertRaises(HTTPException) as failed:
                    login(LoginInput(email="admin@example.com", password="wrong"), db)
                self.assertEqual(401, failed.exception.status_code)
            with self.assertRaises(HTTPException) as threshold:
                login(LoginInput(email="admin@example.com", password="wrong"), db)
            with self.assertRaises(HTTPException) as locked:
                login(LoginInput(email="admin@example.com", password="correct"), db)

        self.assertEqual(429, threshold.exception.status_code)
        self.assertEqual(429, locked.exception.status_code)
        self.assertEqual(3, state["failed"])
        self.assertTrue(state["locked"])
        self.assertEqual(3, verify.call_count)

    def test_success_resets_failure_count_and_lock_timestamp(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = self._user(
            failed_login_attempts=2,
            locked_until="2026-08-06 12:00:00",
            is_locked=0,
        )
        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.api.auth.issue_token", return_value="signed-token"),
        ):
            response = login(
                LoginInput(email="admin@example.com", password="correct"), db
            )

        self.assertEqual("signed-token", response["token"])
        update = db.cursor.return_value.execute.call_args_list[1]
        self.assertIn("failed_login_attempts=0,locked_until=NULL", update.args[0])
        self.assertEqual((7,), update.args[1])
        db.commit.assert_called_once()

    def test_unknown_or_inactive_account_uses_generic_error_without_update(self):
        for user in (
            None,
            self._user(is_active=False),
        ):
            with self.subTest(user=user):
                db = MagicMock()
                db.cursor.return_value.fetchone.return_value = user
                with self.assertRaises(HTTPException) as raised:
                    login(LoginInput(email="missing@example.com", password="wrong"), db)
                self.assertEqual(401, raised.exception.status_code)
                self.assertEqual("Invalid email or password", raised.exception.detail["message"])
                self.assertNotIn("attempts_remaining", raised.exception.detail)
                self.assertEqual(1, db.cursor.return_value.execute.call_count)
                db.commit.assert_not_called()

    def test_ambiguous_email_requests_workspace_without_password_check(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = self._user(
            matching_accounts=2
        )
        with patch("app.services.auth_service.verify_password") as verify:
            with self.assertRaises(HTTPException) as raised:
                login(
                    LoginInput(email="admin@example.com", password="correct"), db
                )
        self.assertEqual(401, raised.exception.status_code)
        self.assertEqual("workspace_required", raised.exception.detail["code"])
        verify.assert_not_called()

    def test_workspace_slug_scopes_the_account_lookup(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = self._user()
        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.api.auth.issue_token", return_value="signed-token"),
        ):
            response = login(
                LoginInput(
                    email="admin@example.com",
                    password="correct",
                    workspace_slug="test-workspace",
                ),
                db,
            )

        lookup = db.cursor.return_value.execute.call_args_list[0]
        self.assertIn("o.slug=%s", lookup.args[0])
        self.assertEqual(("admin@example.com", "test-workspace"), lookup.args[1])
        self.assertEqual("test-workspace", response["user"]["workspace_slug"])

    def test_policy_is_configurable_but_safely_bounded(self):
        self.assertEqual((3, 60), account_lockout_policy())
        with patch.dict(os.environ, {
            "AUTH_MAX_FAILED_LOGIN_ATTEMPTS": "1",
            "AUTH_ACCOUNT_LOCKOUT_SECONDS": "999999",
        }):
            self.assertEqual((3, 86400), account_lockout_policy())
        with patch.dict(os.environ, {"AUTH_MAX_FAILED_LOGIN_ATTEMPTS": "bad"}):
            with self.assertRaisesRegex(ValueError, "must be an integer"):
                account_lockout_policy()


if __name__ == "__main__":
    unittest.main()
