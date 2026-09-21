"""Confirmation-gated service-request actions for Facility Operations."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.facility.domain.contracts import ServiceRequestDraftInput
from app.facility.infrastructure.repository import FacilityRepository


class FacilityActionError(Exception):
    """Raised when an action is unavailable, expired, or already used."""


class FacilityActionValidationError(FacilityActionError):
    """Raised when a requested site or asset is not owned by this tenant."""


class FacilityActionService:
    def __init__(self, repository: FacilityRepository, organization_id: int, actor_user_id: int):
        self._repository = repository
        self._organization_id = organization_id
        self._actor_user_id = actor_user_id

    def prepare_service_request(self, draft: ServiceRequestDraftInput) -> dict[str, Any]:
        site = self._repository.get_site_by_code(self._organization_id, draft.site_code)
        if not site:
            raise FacilityActionValidationError("The requested facility site was not found.")
        asset_id = None
        if draft.asset_code:
            asset = self._repository.get_asset_by_code(site["id"], draft.asset_code)
            if not asset:
                raise FacilityActionValidationError("The requested facility asset was not found at that site.")
            asset_id = asset["id"]
        confirmation_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        payload = {
            "site_id": site["id"], "asset_id": asset_id, "title": draft.title,
            "description": draft.description, "priority": draft.priority,
        }
        self._repository.create_action_confirmation(
            confirmation_id, self._organization_id, self._actor_user_id,
            "create_service_request", payload, expires_at,
        )
        self._repository.commit()
        target = draft.asset_code or site["code"]
        return {
            "id": confirmation_id,
            "action_type": "create_service_request",
            "status": "pending",
            "expires_at": expires_at,
            "summary": f"Create a {draft.priority}-priority maintenance request for {target}: {draft.title}",
        }

    def confirm_and_create_service_request(self, confirmation_id: str) -> dict[str, Any]:
        confirmation = self._repository.get_action_confirmation_for_update(
            confirmation_id, self._organization_id, self._actor_user_id,
        )
        if not confirmation:
            raise FacilityActionError("The confirmation was not found for this user.")
        if confirmation["status"] != "pending":
            raise FacilityActionError("This confirmation is no longer available for use.")
        expires_at = confirmation["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            self._repository.set_action_confirmation_status(confirmation_id, "expired")
            self._repository.commit()
            raise FacilityActionError("This confirmation has expired. Prepare a new request.")
        try:
            payload = json.loads(confirmation["payload_json"])
            request_number = f"SR-{uuid.uuid4().hex[:12].upper()}"
            request = self._repository.create_service_request(
                request_number, payload, self._actor_user_id,
            )
            self._repository.set_action_confirmation_status(confirmation_id, "consumed")
            self._repository.record_action_audit(
                self._organization_id, self._actor_user_id, "facility_service_request_created",
                "facility_service_request", str(request["id"]),
                {"confirmation_id": confirmation_id, "request_number": request_number},
            )
            self._repository.commit()
            return request
        except FacilityActionError:
            raise
        except Exception:
            self._repository.rollback()
            raise
