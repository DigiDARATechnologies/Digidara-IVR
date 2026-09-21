"""Tenant-scoped post-language IVR configuration and routing."""

from __future__ import annotations

import re
import secrets
from typing import Any, Optional


DEFAULT_ENGLISH = "Say {choices}, or press the matching number."
DEFAULT_TAMIL = "{choices} சொல்லுங்க, அல்லது சரியான எண்ணை அழுத்துங்க."

LANGUAGE_CODES = {"tamil": "ta-IN", "english": "en-US"}


def _normalize_words(value: str) -> str:
    return re.sub(r"[^a-z0-9஀-௿ ]+", " ", (value or "").lower()).strip()


def _settings(conn: Any, organization_id: int) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id,organization_id,is_active,timeout_seconds,prompt_english,prompt_tamil,audio_token
             FROM organization_ivr_settings WHERE organization_id=%s""",
        (organization_id,),
    )
    return cursor.fetchone()


def _options(conn: Any, settings_id: int, active_only: bool = False) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    sql = (
        "SELECT o.id,o.digit,o.label,o.campaign_id,o.destination_id,o.is_active,o.sort_order,"
        "d.name AS destination_name,d.phone_e164 AS destination_phone "
        "FROM organization_ivr_options o "
        "LEFT JOIN staff_destinations d ON d.id=o.destination_id "
        "WHERE o.settings_id=%s"
    )
    if active_only:
        sql += " AND o.is_active=TRUE"
    sql += " ORDER BY o.sort_order,o.digit"
    cursor.execute(sql, (settings_id,))
    return cursor.fetchall() or []


def get_settings(conn: Any, organization_id: int, *, active_only: bool = False) -> dict[str, Any]:
    settings = _settings(conn, organization_id)
    if not settings or (active_only and not settings.get("is_active")):
        return {"is_active": False, "timeout_seconds": 7, "prompt_english": "", "prompt_tamil": "", "options": []}
    return {
        "is_active": bool(settings["is_active"]), "timeout_seconds": int(settings["timeout_seconds"]),
        "prompt_english": settings.get("prompt_english") or "", "prompt_tamil": settings.get("prompt_tamil") or "",
        "options": _options(conn, int(settings["id"]), active_only),
    }


def _default_prompt(language: str, options: list[dict[str, Any]]) -> str:
    choices = ", ".join(f"{item['label']} ({item['digit']})" for item in options)
    return (DEFAULT_TAMIL if language == "tamil" else DEFAULT_ENGLISH).format(choices=choices)


def get_live_menu(conn: Any, organization_id: int, language: str) -> Optional[dict[str, Any]]:
    settings = _settings(conn, organization_id)
    if not settings or not settings.get("is_active"):
        return None
    options = _options(conn, int(settings["id"]), active_only=True)
    if not options:
        return None
    prompt = (settings.get("prompt_tamil") if language == "tamil" else settings.get("prompt_english")) or _default_prompt(language, options)
    speech_hints = ", ".join(item["label"] for item in options)
    return {
        "id": int(settings["id"]), "timeout_seconds": int(settings["timeout_seconds"]),
        "audio_token": settings["audio_token"], "prompt": prompt, "options": options,
        "speech_hints": speech_hints,
        "language_code": LANGUAGE_CODES.get(language, "en-US"),
    }


def update_settings(conn: Any, organization_id: int, values: dict[str, Any], actor_user_id: int) -> dict[str, Any]:
    cursor = conn.cursor()
    options = values["options"]
    campaign_ids = [item["campaign_id"] for item in options if item.get("campaign_id")]
    if campaign_ids:
        placeholders = ",".join(["%s"] * len(campaign_ids))
        cursor.execute(
            f"SELECT id FROM campaigns WHERE organization_id=%s AND id IN ({placeholders})",
            [organization_id, *campaign_ids],
        )
        if {int(row["id"]) for row in cursor.fetchall()} != set(campaign_ids):
            raise ValueError("Every AI-routed IVR option must use a campaign in this organization")
    destination_ids = [item["destination_id"] for item in options if item.get("destination_id")]
    if destination_ids:
        placeholders = ",".join(["%s"] * len(destination_ids))
        cursor.execute(
            f"SELECT id FROM staff_destinations WHERE organization_id=%s AND id IN ({placeholders})",
            [organization_id, *destination_ids],
        )
        if {int(row["id"]) for row in cursor.fetchall()} != set(destination_ids):
            raise ValueError("Every human-routed IVR option must use a transfer destination in this organization")
    token = secrets.token_urlsafe(32)
    cursor.execute(
        """INSERT INTO organization_ivr_settings
             (organization_id,is_active,timeout_seconds,prompt_english,prompt_tamil,audio_token)
           VALUES (%s,%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE is_active=VALUES(is_active),timeout_seconds=VALUES(timeout_seconds),
             prompt_english=VALUES(prompt_english),prompt_tamil=VALUES(prompt_tamil),audio_token=VALUES(audio_token),
             updated_at=CURRENT_TIMESTAMP""",
        (organization_id, values["is_active"], values["timeout_seconds"], values["prompt_english"].strip(), values["prompt_tamil"].strip(), token),
    )
    cursor.execute("SELECT id FROM organization_ivr_settings WHERE organization_id=%s", (organization_id,))
    settings_id = int(cursor.fetchone()["id"])
    cursor.execute("DELETE FROM organization_ivr_options WHERE settings_id=%s", (settings_id,))
    for item in options:
        cursor.execute(
            """INSERT INTO organization_ivr_options(settings_id,digit,label,campaign_id,destination_id,is_active,sort_order)
                 VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (
                settings_id, item["digit"], item["label"], item.get("campaign_id"),
                item.get("destination_id"), item["is_active"], item["sort_order"],
            ),
        )
    cursor.execute(
        """INSERT INTO audit_logs(organization_id,actor_user_id,action,resource_type,resource_id,result)
             VALUES (%s,%s,'ivr_settings_updated','organization_ivr_settings',%s,'success')""",
        (organization_id, actor_user_id, str(settings_id)),
    )
    conn.commit()
    return get_settings(conn, organization_id)


def route_selection(
    conn: Any, *, organization_id: int, call_log_id: int,
    digit: str = "", speech_text: str = "",
) -> Optional[dict[str, Any]]:
    """Persist a single accepted IVR decision from a pressed digit or a
    spoken department name; callback retries return the first route.

    Each option routes to exactly one of an AI campaign or a human staff
    destination, so the result always carries a "route_type" of "ai" or
    "human" alongside whichever id/phone number applies.
    """
    cursor = conn.cursor()
    cursor.execute(
        """SELECT campaign_id,destination_id FROM call_ivr_selections
            WHERE organization_id=%s AND call_log_id=%s""",
        (organization_id, call_log_id),
    )
    previous = cursor.fetchone()
    if previous:
        return _selection_result(conn, previous, replayed=True)

    columns = "o.id,o.digit,o.label,o.campaign_id,o.destination_id"
    option = None
    if digit:
        cursor.execute(
            f"""SELECT {columns} FROM organization_ivr_options o
                 JOIN organization_ivr_settings s ON s.id=o.settings_id
                WHERE s.organization_id=%s AND s.is_active=TRUE AND o.is_active=TRUE AND o.digit=%s""",
            (organization_id, digit),
        )
        option = cursor.fetchone()
    if not option and speech_text:
        spoken = _normalize_words(speech_text)
        cursor.execute(
            f"""SELECT {columns} FROM organization_ivr_options o
                 JOIN organization_ivr_settings s ON s.id=o.settings_id
                WHERE s.organization_id=%s AND s.is_active=TRUE AND o.is_active=TRUE""",
            (organization_id,),
        )
        for candidate in cursor.fetchall() or []:
            label = _normalize_words(str(candidate["label"]))
            if label and label in spoken:
                option = candidate
                break
    if not option:
        return None
    cursor.execute(
        """INSERT INTO call_ivr_selections(organization_id,call_log_id,menu_option_id,digit,label,campaign_id,destination_id)
             VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (
            organization_id, call_log_id, option["id"], option["digit"], option["label"],
            option.get("campaign_id"), option.get("destination_id"),
        ),
    )
    if option.get("campaign_id"):
        cursor.execute(
            "UPDATE call_logs SET campaign_id=%s WHERE id=%s AND organization_id=%s",
            (option["campaign_id"], call_log_id, organization_id),
        )
    conn.commit()
    return _selection_result(conn, option, replayed=False, label=option.get("label"))


def _selection_result(
    conn: Any, row: dict[str, Any], *, replayed: bool, label: str | None = None,
) -> dict[str, Any]:
    if row.get("destination_id"):
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id,organization_id,name,phone_e164,department FROM staff_destinations WHERE id=%s",
            (row["destination_id"],),
        )
        destination = cursor.fetchone() or {}
        dest_org_id = destination.get("organization_id") or row.get("organization_id")
        phones = []
        if dest_org_id and row.get("destination_id"):
            from app.services import transfer_service
            phones = transfer_service.get_transfer_phone_numbers(
                conn, int(dest_org_id), int(row["destination_id"])
            )
        if not phones and destination.get("phone_e164"):
            phones = [str(destination["phone_e164"])]
        return {
            "route_type": "human", "destination_id": int(row["destination_id"]),
            "destination_phone": destination.get("phone_e164"),
            "destination_phones": phones,
            "destination_name": destination.get("name"),
            "department": destination.get("department"),
            "label": label, "replayed": replayed,
        }
    return {
        "route_type": "ai", "campaign_id": int(row["campaign_id"]),
        "label": label, "replayed": replayed,
    }


def validate_audio_token(conn: Any, settings_id: int, token: str) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT organization_id,audio_token FROM organization_ivr_settings WHERE id=%s AND is_active=TRUE",
        (settings_id,),
    )
    settings = cursor.fetchone()
    if not settings or not secrets.compare_digest(str(settings["audio_token"]), token):
        return None
    return settings
