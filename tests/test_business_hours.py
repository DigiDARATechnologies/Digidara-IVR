import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError

from app.api import business_hours as business_hours_api
from app.api import plivo as plivo_api
from app.schemas.business_hours import BusinessHoursSet, DaySchedule
from app.services import business_hours_service

TUESDAY_10_30_IST = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)  # 2026-09-15 is a Tuesday
MON_FRI_9_TO_6 = [
    DaySchedule(day_of_week=day, is_closed=False, open_time="09:00", close_time="18:00")
    for day in range(5)
] + [
    DaySchedule(day_of_week=5, is_closed=True),
    DaySchedule(day_of_week=6, is_closed=True),
]


class DayScheduleValidationTests(unittest.TestCase):
    def test_open_day_requires_open_and_close_time(self):
        with self.assertRaises(ValidationError):
            DaySchedule(day_of_week=0, is_closed=False)

    def test_rejects_open_time_not_before_close_time(self):
        with self.assertRaises(ValidationError):
            DaySchedule(day_of_week=0, is_closed=False, open_time="18:00", close_time="09:00")

    def test_rejects_malformed_time(self):
        with self.assertRaises(ValidationError):
            DaySchedule(day_of_week=0, is_closed=False, open_time="9:00", close_time="18:00")

    def test_closed_day_needs_no_times(self):
        day = DaySchedule(day_of_week=6, is_closed=True)
        self.assertIsNone(day.open_time)


class BusinessHoursSetValidationTests(unittest.TestCase):
    def test_requires_all_seven_days_exactly_once(self):
        with self.assertRaises(ValidationError):
            BusinessHoursSet(timezone="Asia/Kolkata", days=MON_FRI_9_TO_6[:6])

    def test_rejects_unknown_timezone(self):
        with self.assertRaises(ValidationError):
            BusinessHoursSet(timezone="Mars/Olympus_Mons", days=MON_FRI_9_TO_6)

    def test_accepts_a_valid_full_week(self):
        schedule = BusinessHoursSet(timezone="Asia/Kolkata", days=MON_FRI_9_TO_6)
        self.assertEqual(7, len(schedule.days))


class IsOpenNowTests(unittest.TestCase):
    def test_unconfigured_organization_is_always_open(self):
        db = MagicMock()
        db.cursor.return_value.fetchall.return_value = []
        db.cursor.return_value.fetchone.return_value = {"timezone": "Asia/Kolkata"}
        status = business_hours_service.is_open_now(db, 42, now=TUESDAY_10_30_IST)
        self.assertTrue(status["is_open"])
        self.assertFalse(status["configured"])

    def test_open_during_configured_hours(self):
        db = MagicMock()
        db.cursor.return_value.fetchall.return_value = [
            {"day_of_week": 1, "is_closed": False, "open_time": "09:00", "close_time": "18:00"},
        ]
        db.cursor.return_value.fetchone.return_value = {"timezone": "Asia/Kolkata"}
        status = business_hours_service.is_open_now(db, 42, now=TUESDAY_10_30_IST)
        self.assertTrue(status["is_open"])
        self.assertTrue(status["configured"])
        self.assertEqual(1, status["day_of_week"])

    def test_closed_outside_configured_hours(self):
        db = MagicMock()
        db.cursor.return_value.fetchall.return_value = [
            {"day_of_week": 1, "is_closed": False, "open_time": "20:00", "close_time": "22:00"},
        ]
        db.cursor.return_value.fetchone.return_value = {"timezone": "Asia/Kolkata"}
        status = business_hours_service.is_open_now(db, 42, now=TUESDAY_10_30_IST)
        self.assertFalse(status["is_open"])

    def test_closed_on_a_day_explicitly_marked_closed(self):
        db = MagicMock()
        db.cursor.return_value.fetchall.return_value = [
            {"day_of_week": 1, "is_closed": True, "open_time": None, "close_time": None},
        ]
        db.cursor.return_value.fetchone.return_value = {"timezone": "Asia/Kolkata"}
        status = business_hours_service.is_open_now(db, 42, now=TUESDAY_10_30_IST)
        self.assertFalse(status["is_open"])

    def test_closed_on_a_day_with_no_row_at_all(self):
        db = MagicMock()
        # Only Monday configured; Tuesday (day_of_week=1) has no row.
        db.cursor.return_value.fetchall.return_value = [
            {"day_of_week": 0, "is_closed": False, "open_time": "09:00", "close_time": "18:00"},
        ]
        db.cursor.return_value.fetchone.return_value = {"timezone": "Asia/Kolkata"}
        status = business_hours_service.is_open_now(db, 42, now=TUESDAY_10_30_IST)
        self.assertFalse(status["is_open"])

    def test_falls_back_to_default_timezone_for_unknown_zone(self):
        db = MagicMock()
        db.cursor.return_value.fetchall.return_value = []
        db.cursor.return_value.fetchone.return_value = {"timezone": "Not/AZone"}
        status = business_hours_service.is_open_now(db, 42, now=TUESDAY_10_30_IST)
        self.assertEqual(business_hours_service.DEFAULT_TIMEZONE, status["organization_timezone"])


class SetScheduleTests(unittest.TestCase):
    def test_replaces_existing_rows_and_updates_timezone_then_commits(self):
        db = MagicMock()
        with patch.object(business_hours_service, "get_schedule", return_value=[]):
            business_hours_service.set_schedule(
                db, 42, BusinessHoursSet(timezone="Asia/Kolkata", days=MON_FRI_9_TO_6),
            )
        calls = db.cursor.return_value.execute.call_args_list
        self.assertIn("UPDATE organizations SET timezone=%s", calls[0].args[0])
        self.assertEqual(("Asia/Kolkata", 42), calls[0].args[1])
        self.assertIn("DELETE FROM business_hours", calls[1].args[0])
        self.assertEqual(9, len(calls))  # 1 update + 1 delete + 7 inserts
        db.commit.assert_called_once()


class BusinessHoursApiTests(unittest.TestCase):
    def test_read_reports_unconfigured_when_no_schedule_exists(self):
        db = MagicMock()
        with patch.object(business_hours_service, "get_schedule", return_value=[]):
            with patch.object(business_hours_service, "get_organization_timezone", return_value="Asia/Kolkata"):
                response = business_hours_api.read_business_hours(admin={"organization_id": 42}, db=db)
        self.assertFalse(response.configured)
        self.assertEqual([], response.days)

    def test_status_endpoint_delegates_to_service_scoped_to_the_caller_org(self):
        db = MagicMock()
        with patch.object(
            business_hours_service, "is_open_now",
            return_value={
                "is_open": True, "configured": True, "organization_timezone": "Asia/Kolkata",
                "local_time": "2026-09-15T10:30:00+05:30", "day_of_week": 1,
            },
        ) as is_open_now:
            business_hours_api.read_business_hours_status(admin={"organization_id": 42}, db=db)
        is_open_now.assert_called_once_with(db, 42)


class InboundBusinessHoursGateTests(unittest.IsolatedAsyncioTestCase):
    """/api/plivo/inbound must decline calls outside business hours before
    ever creating a customer/call-log row."""

    def _request(self, form: dict) -> MagicMock:
        request = MagicMock()
        request.method = "POST"
        request.base_url = "https://voice.example.com/"
        request.url.query = ""
        self._form = form
        return request

    async def test_closed_organization_gets_a_closed_message_and_no_call_log(self):
        db = MagicMock()
        request = self._request({"To": "918041234567", "From": "911234567890"})
        route = {"organization_id": 42, "campaign_id": 7}
        with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=self._form)):
            with patch("app.api.plivo.phone_number_service.get_active_route_for_number", return_value=route):
                with patch(
                    "app.api.plivo.business_hours_service.is_open_now",
                    return_value={"is_open": False, "configured": True},
                ):
                    with patch("app.api.plivo.call_log_service.create_call_log") as create_call_log:
                        response = await plivo_api.inbound(request, db)
        self.assertEqual(200, response.status_code)
        self.assertIn(b"inbound-closed.wav", response.body)
        self.assertNotIn(b"<Speak>", response.body)
        create_call_log.assert_not_called()

    async def test_open_organization_proceeds_past_the_gate(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None
        db.cursor.return_value.lastrowid = 501
        request = self._request({
            "To": "918041234567", "From": "911234567890", "CallUUID": "call-uuid-2",
        })
        route = {"organization_id": 42, "campaign_id": 7}
        with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=self._form)):
            with patch("app.api.plivo.phone_number_service.get_active_route_for_number", return_value=route):
                with patch(
                    "app.api.plivo.business_hours_service.is_open_now",
                    return_value={"is_open": True, "configured": True},
                ):
                    with patch("app.api.plivo.call_log_service.get_call_log_by_sid", return_value=None):
                        with patch(
                            "app.api.plivo.call_log_service.create_call_log",
                            return_value={"id": 1001},
                        ) as create_call_log:
                            response = await plivo_api.inbound(request, db)
        self.assertEqual(200, response.status_code)
        self.assertIn(b"Redirect", response.body)
        create_call_log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
