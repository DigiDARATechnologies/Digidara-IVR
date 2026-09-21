import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.api.auth import current_admin
from app.main import app


PUBLIC_HTTP_PATHS = {
    "/",
    "/health/live",
    "/health/ready",
    "/auth/status",
    "/auth/bootstrap-admin",
    "/auth/workspaces",
    "/auth/login",
    "/auth/google",
    "/voice/audio/{filename}",
    "/voice/welcome",
    "/voice/respond",
    "/api/plivo/language-prompt.mp3",
    "/api/plivo/language-prompt-v2.wav",
    "/api/plivo/inbound",
    "/api/plivo/answer",
    "/api/plivo/language-select",
    "/api/plivo/ivr-prompt.wav",
    "/api/plivo/ivr-select",
    "/api/plivo/transfer-confirm.wav",
    "/api/plivo/transfer-fallback.wav",
    "/api/plivo/inbound-unconfigured.wav",
    "/api/plivo/inbound-closed.wav",
    "/api/plivo/ring",
    "/api/plivo/hangup",
    "/api/plivo/recording",
    "/api/plivo/stream-status",
    "/api/plivo/fallback",
    "/api/plivo/compliance-webhook",
}


def _dependency_callables(route: APIRoute):
    return {dependency.call for dependency in route.dependant.dependencies}


class AuthenticationCoverageTests(unittest.TestCase):
    def test_current_admin_rejects_missing_bearer_token(self):
        with self.assertRaises(HTTPException) as raised:
            current_admin(authorization=None, db=MagicMock())
        self.assertEqual(401, raised.exception.status_code)

    def test_current_admin_rejects_invalid_bearer_token(self):
        with patch("app.api.auth.decode_token", side_effect=ValueError("bad token")):
            with self.assertRaises(HTTPException) as raised:
                current_admin(authorization="Bearer invalid", db=MagicMock())
        self.assertEqual(401, raised.exception.status_code)

    def test_every_application_http_route_is_authenticated_or_explicitly_public(self):
        uncovered = []
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if route.path in PUBLIC_HTTP_PATHS:
                continue
            if current_admin not in _dependency_callables(route):
                uncovered.append(f"{','.join(sorted(route.methods or []))} {route.path}")
        self.assertEqual([], uncovered, f"Routes missing authentication: {uncovered}")

    def test_public_provider_and_onboarding_routes_do_not_require_admin_token(self):
        protected_public_paths = []
        for route in app.routes:
            if not isinstance(route, APIRoute) or route.path not in PUBLIC_HTTP_PATHS:
                continue
            if current_admin in _dependency_callables(route):
                protected_public_paths.append(route.path)
        self.assertEqual([], protected_public_paths)


if __name__ == "__main__":
    unittest.main()
