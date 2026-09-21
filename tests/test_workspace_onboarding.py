import unittest
from unittest.mock import MagicMock, patch

from app.api.auth import WorkspaceInput, create_workspace
from app.services import workspace_service


class WorkspaceProvisioningTests(unittest.TestCase):
    def test_new_workspace_and_first_admin_are_committed_together(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.return_value = None

        def execute(sql, _params):
            if "INSERT INTO organizations" in sql:
                cursor.lastrowid = 41
            elif "INSERT INTO app_users" in sql:
                cursor.lastrowid = 73

        cursor.execute.side_effect = execute
        with patch.object(workspace_service, "hash_password", return_value="hash"):
            user = workspace_service.create_workspace_with_admin(
                db,
                organization_name="Example Company",
                workspace_slug="example-company",
                admin_name="First Admin",
                admin_email="ADMIN@example.com",
                admin_password="not-stored-plaintext",
            )

        self.assertEqual(41, user["organization_id"])
        self.assertEqual(73, user["id"])
        self.assertEqual("admin@example.com", user["email"])
        self.assertEqual("example-company", user["workspace_slug"])
        statements = cursor.execute.call_args_list
        self.assertIn("INSERT INTO organizations", statements[1].args[0])
        self.assertEqual(
            ("Example Company", "example-company"), statements[1].args[1]
        )
        self.assertIn("INSERT INTO app_users", statements[2].args[0])
        self.assertEqual(41, statements[2].args[1][0])
        self.assertIn("workspace_created", statements[3].args[0])
        db.commit.assert_called_once()
        db.rollback.assert_not_called()

    def test_empty_preprovisioned_workspace_can_be_claimed(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [{"id": 9}, {"total": 0}]
        cursor.lastrowid = 22
        with patch.object(workspace_service, "hash_password", return_value="hash"):
            user = workspace_service.create_workspace_with_admin(
                db,
                organization_name="Claimed Workspace",
                workspace_slug="claimed",
                admin_name="Admin",
                admin_email="admin@example.com",
                admin_password="password-value",
            )

        self.assertEqual(9, user["organization_id"])
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(any("UPDATE organizations" in sql for sql in statements))
        self.assertFalse(any("INSERT INTO organizations" in sql for sql in statements))

    def test_populated_workspace_conflict_rolls_back(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.side_effect = [{"id": 9}, {"total": 1}]
        with self.assertRaises(workspace_service.WorkspaceConflictError):
            workspace_service.create_workspace_with_admin(
                db,
                organization_name="Existing",
                workspace_slug="existing",
                admin_name="Admin",
                admin_email="admin@example.com",
                admin_password="password-value",
            )
        db.rollback.assert_called_once()
        db.commit.assert_not_called()

    def test_public_workspace_endpoint_does_not_require_operator_key(self):
        payload = WorkspaceInput(
            organization_name="Example Company",
            workspace_slug="example-company",
            full_name="First Admin",
            email="admin@example.com",
            password="long-password",
        )
        user = {
            "id": 7,
            "organization_id": 41,
            "organization_name": "Example Company",
            "workspace_slug": "example-company",
            "email": "admin@example.com",
            "full_name": "First Admin",
            "role_code": "admin",
        }
        with (
            patch.object(
                workspace_service, "create_workspace_with_admin", return_value=user
            ) as provision,
            patch("app.api.auth.issue_token", return_value="signed-token"),
            patch("app.api.auth._require_bootstrap_key") as require_key,
        ):
            response = create_workspace(payload, db=MagicMock())

        self.assertEqual("signed-token", response["token"])
        provision.assert_called_once()
        require_key.assert_not_called()

    def test_public_workspace_endpoint_returns_signed_admin_session(self):
        payload = WorkspaceInput(
            organization_name="Example Company",
            workspace_slug="example-company",
            full_name="First Admin",
            email="admin@example.com",
            password="long-password",
        )
        user = {
            "id": 7,
            "organization_id": 41,
            "organization_name": "Example Company",
            "workspace_slug": "example-company",
            "email": "admin@example.com",
            "full_name": "First Admin",
            "role_code": "admin",
        }
        with (
            patch.object(
                workspace_service, "create_workspace_with_admin", return_value=user
            ) as provision,
            patch("app.api.auth.issue_token", return_value="signed-token"),
        ):
            response = create_workspace(payload, db=MagicMock())

        self.assertEqual("signed-token", response["token"])
        self.assertEqual("example-company", response["user"]["workspace_slug"])
        provision.assert_called_once()


if __name__ == "__main__":
    unittest.main()
