import os
import unittest
import uuid

from app.database.db import get_db_connection
from app.schemas.campaign import CampaignCreate
from app.schemas.customer import CustomerCreate
from app.services import campaign_service, customer_service, workspace_service
from app.services.auth_service import WorkspaceRequiredError, authenticate_user


@unittest.skipUnless(
    os.getenv("RUN_DB_INTEGRATION_TESTS") == "1",
    "Set RUN_DB_INTEGRATION_TESTS=1 to run against the configured local MySQL database",
)
class TenantDatabaseIntegrationTests(unittest.TestCase):
    def test_two_workspaces_with_same_email_remain_isolated(self):
        suffix = uuid.uuid4().hex[:10]
        slug_a = f"isolation-a-{suffix}"
        slug_b = f"isolation-b-{suffix}"
        shared_email = f"isolation-{suffix}@example.invalid"
        db = get_db_connection()
        organization_ids = []
        try:
            user_a = workspace_service.create_workspace_with_admin(
                db,
                organization_name="Isolation Test A",
                workspace_slug=slug_a,
                admin_name="Test Admin A",
                admin_email=shared_email,
                admin_password="test-password-a",
            )
            organization_ids.append(user_a["organization_id"])
            user_b = workspace_service.create_workspace_with_admin(
                db,
                organization_name="Isolation Test B",
                workspace_slug=slug_b,
                admin_name="Test Admin B",
                admin_email=shared_email,
                admin_password="test-password-b",
            )
            organization_ids.append(user_b["organization_id"])

            authenticated_a = authenticate_user(
                db, shared_email, "test-password-a", slug_a
            )
            authenticated_b = authenticate_user(
                db, shared_email, "test-password-b", slug_b
            )
            self.assertEqual(user_a["organization_id"], authenticated_a["organization_id"])
            self.assertEqual(user_b["organization_id"], authenticated_b["organization_id"])
            with self.assertRaises(WorkspaceRequiredError):
                authenticate_user(db, shared_email, "test-password-a")

            customer_a = customer_service.create_customer(
                db,
                user_a["organization_id"],
                CustomerCreate(
                    name="Customer A",
                    email=f"customer-a-{suffix}@example.invalid",
                    phone="0000000001",
                    language="english",
                ),
            )
            customer_b = customer_service.create_customer(
                db,
                user_b["organization_id"],
                CustomerCreate(
                    name="Customer B",
                    email=f"customer-b-{suffix}@example.invalid",
                    phone="0000000002",
                    language="english",
                ),
            )
            campaign_a = campaign_service.create_campaign(
                db,
                user_a["organization_id"],
                CampaignCreate(
                    campaign_name="Campaign A", objective="Test", ai_prompt="Test"
                ),
            )
            campaign_b = campaign_service.create_campaign(
                db,
                user_b["organization_id"],
                CampaignCreate(
                    campaign_name="Campaign B", objective="Test", ai_prompt="Test"
                ),
            )

            self.assertIsNone(
                customer_service.get_customer_by_id(
                    db, customer_b["id"], user_a["organization_id"]
                )
            )
            self.assertIsNone(
                campaign_service.get_campaign_by_id(
                    db, campaign_b["id"], user_a["organization_id"]
                )
            )
            self.assertEqual(
                [customer_a["id"]],
                [row["id"] for row in customer_service.get_all_customers(
                    db, user_a["organization_id"]
                )],
            )
            self.assertEqual(
                [campaign_a["id"]],
                [row["id"] for row in campaign_service.get_all_campaigns(
                    db, user_a["organization_id"]
                )],
            )
        finally:
            cursor = db.cursor()
            for organization_id in organization_ids:
                cursor.execute(
                    "DELETE FROM audit_logs WHERE organization_id=%s",
                    (organization_id,),
                )
                cursor.execute(
                    "DELETE FROM customers WHERE organization_id=%s",
                    (organization_id,),
                )
                cursor.execute(
                    "DELETE FROM campaigns WHERE organization_id=%s",
                    (organization_id,),
                )
                cursor.execute(
                    "DELETE FROM app_users WHERE organization_id=%s",
                    (organization_id,),
                )
                cursor.execute(
                    "DELETE FROM organizations WHERE id=%s",
                    (organization_id,),
                )
            db.commit()
            db.close()


if __name__ == "__main__":
    unittest.main()
