import os
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, Request

from app.services.rate_limiter import (
    SlidingWindowRateLimiter,
    limiter,
)
from app.services.plivo_stream import (
    stream_token,
    validate_stream_token,
)


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.limiter = SlidingWindowRateLimiter(default_limit=3, window_seconds=2)

    def _mock_request(self, client_ip: str = "192.168.1.50") -> Request:
        req = MagicMock(spec=Request)
        req.client.host = client_ip
        req.headers = {}
        return req

    def test_requests_allowed_within_limit(self):
        req = self._mock_request()
        for _ in range(3):
            self.limiter.enforce(req, "test_action")

    def test_request_exceeding_limit_raises_429(self):
        req = self._mock_request()
        for _ in range(3):
            self.limiter.enforce(req, "test_action")

        with self.assertRaises(HTTPException) as raised:
            self.limiter.enforce(req, "test_action")

        self.assertEqual(429, raised.exception.status_code)
        self.assertEqual("rate_limit_exceeded", raised.exception.detail["code"])
        self.assertIn("Retry-After", raised.exception.headers)

    def test_different_ips_have_independent_quotas(self):
        req1 = self._mock_request("10.0.0.1")
        req2 = self._mock_request("10.0.0.2")

        for _ in range(3):
            self.limiter.enforce(req1, "test_action")

        # req1 is blocked
        with self.assertRaises(HTTPException):
            self.limiter.enforce(req1, "test_action")

        # req2 should still be allowed
        self.limiter.enforce(req2, "test_action")

    def test_sliding_window_resets_after_expiry(self):
        req = self._mock_request()
        for _ in range(3):
            self.limiter.enforce(req, "test_action")

        # Advance beyond window
        time.sleep(2.1)

        # Now should succeed again
        self.limiter.enforce(req, "test_action")


class StreamTokenSecurityTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {"PLIVO_STREAM_TOKEN_SECRET": "test-stream-secret-32-bytes-long"})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    def test_timestamped_token_validates_successfully(self):
        token = stream_token(customer_id=10, campaign_id=20, correlation_id="call-abc-123")
        self.assertIn(".", token)
        is_valid = validate_stream_token(token, customer_id=10, campaign_id=20, correlation_id="call-abc-123")
        self.assertTrue(is_valid)

    def test_tampered_token_signature_fails(self):
        token = stream_token(customer_id=10, campaign_id=20, correlation_id="call-abc-123")
        tampered = "a" + token[1:]
        is_valid = validate_stream_token(tampered, customer_id=10, campaign_id=20, correlation_id="call-abc-123")
        self.assertFalse(is_valid)

    def test_mismatched_params_fails(self):
        token = stream_token(customer_id=10, campaign_id=20, correlation_id="call-abc-123")
        # Different customer_id
        self.assertFalse(validate_stream_token(token, customer_id=11, campaign_id=20, correlation_id="call-abc-123"))
        # Different correlation_id
        self.assertFalse(validate_stream_token(token, customer_id=10, campaign_id=20, correlation_id="call-xyz-999"))

    def test_expired_timestamp_token_is_rejected(self):
        past_ts = int(time.time()) - 3600  # 1 hour ago
        old_token = stream_token(customer_id=10, campaign_id=20, correlation_id="call-abc-123", timestamp=past_ts)
        is_valid = validate_stream_token(
            old_token, customer_id=10, campaign_id=20, correlation_id="call-abc-123", max_age_seconds=1800
        )
        self.assertFalse(is_valid)

    def test_legacy_untimestamped_token_still_validates(self):
        import hashlib
        import hmac
        from app.services.plivo_stream import _stream_secret
        msg = f"{10}:{20}:{'call-abc-123'}".encode("utf-8")
        legacy_token = hmac.new(_stream_secret(), msg, hashlib.sha256).hexdigest()

        self.assertNotIn(".", legacy_token)
        is_valid = validate_stream_token(legacy_token, customer_id=10, campaign_id=20, correlation_id="call-abc-123")
        self.assertTrue(is_valid)


if __name__ == "__main__":
    unittest.main()
