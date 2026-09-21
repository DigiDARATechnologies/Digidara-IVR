import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.call_reconciliation_service import (
    reconcile_unstarted_provider_calls,
)


class CallReconciliationServiceTests(unittest.TestCase):
    def test_terminal_provider_error_recovers_stale_live_call(self):
        connection = MagicMock()
        connection.cursor.return_value.fetchall.return_value = [{
            "id": 45,
            "call_sid": "call-45",
            "provider_call_id": "call-45",
        }]
        provider = MagicMock()
        provider.get_call.return_value = SimpleNamespace(
            status="ANSWER",
            duration_seconds=6,
            billed_duration_seconds=60,
            cost_usd=0.0075,
            metadata={"hangup_cause": "Error Reaching Answer URL"},
        )

        with patch(
            "app.services.call_reconciliation_service.call_log_service.finalize_call_log"
        ) as finalize:
            count = reconcile_unstarted_provider_calls(
                connection, 7, provider=provider, minimum_age_seconds=45
            )

        self.assertEqual(count, 1)
        provider.get_call.assert_called_once_with("call-45")
        update_sql, update_values = connection.cursor.return_value.execute.call_args_list[1].args
        self.assertIn("organization_id=%s", update_sql)
        self.assertEqual(update_values, ("failed", "Error Reaching Answer URL", 0.0075, 60, 45, 7))
        finalize.assert_called_once_with(connection, "call-45", "failed", 6)

    def test_active_provider_call_is_not_finalized(self):
        connection = MagicMock()
        connection.cursor.return_value.fetchall.return_value = [{
            "id": 46,
            "call_sid": "call-46",
            "provider_call_id": "call-46",
        }]
        provider = MagicMock()
        provider.get_call.return_value = SimpleNamespace(
            status="ANSWER",
            duration_seconds=0,
            billed_duration_seconds=0,
            cost_usd=0,
            metadata={},
        )

        with patch(
            "app.services.call_reconciliation_service.call_log_service.finalize_call_log"
        ) as finalize:
            count = reconcile_unstarted_provider_calls(
                connection, 7, provider=provider, minimum_age_seconds=45
            )

        self.assertEqual(count, 0)
        finalize.assert_not_called()
        connection.commit.assert_not_called()

    def test_no_candidate_avoids_provider_lookup(self):
        connection = MagicMock()
        connection.cursor.return_value.fetchall.return_value = []
        provider = MagicMock()

        count = reconcile_unstarted_provider_calls(connection, 7, provider=provider)

        self.assertEqual(count, 0)
        provider.get_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
