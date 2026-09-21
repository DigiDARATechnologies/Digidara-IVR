from typing import Dict, Any

VALID_SPEAKERS = {"user", "assistant"}


def _normalize_speaker(speaker: str) -> str:
    if speaker == "customer":
        speaker = "user"
    if speaker not in VALID_SPEAKERS:
        raise ValueError("conversation speaker must be 'user' or 'assistant'")
    return speaker


def save_message(
    conn: Any,
    customer_id: int,
    speaker: str,
    message: str
) -> Dict[str, Any]:
    """Inserts a conversation message into MySQL and returns the message dict."""
    speaker = _normalize_speaker(speaker)
    message = (message or "").strip()
    if not message:
        return {"id": None, "customer_id": customer_id, "speaker": speaker, "message": message}

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id FROM conversations
        WHERE customer_id = %s AND speaker = %s AND message = %s
        ORDER BY id DESC LIMIT 1
        """,
        (customer_id, speaker, message),
    )
    existing = cursor.fetchone()
    if existing:
        return {
            "id": existing.get("id") if isinstance(existing, dict) else existing[0],
            "customer_id": customer_id,
            "speaker": speaker,
            "message": message,
        }

    cursor.execute(
        "INSERT INTO conversations (customer_id, speaker, message) VALUES (%s, %s, %s)",
        (customer_id, speaker, message)
    )
    conn.commit()
    new_id = cursor.lastrowid
    
    return {
        "id": new_id,
        "customer_id": customer_id,
        "speaker": speaker,
        "message": message
    }


def save_conversation(
    conn,
    customer_id,
    speaker,
    message,
    call_sid=None,
    event_id=None,
):
    speaker = _normalize_speaker(speaker)
    message = (message or "").strip()
    if not message:
        return

    cursor = conn.cursor()
    # Realtime can retry a server event. Deduplicate by its stable event id,
    # never by message text: callers legitimately say short phrases such as
    # "yes" more than once in the same call.
    if event_id:
        cursor.execute(
            "SELECT id FROM conversations WHERE event_id = %s LIMIT 1",
            (event_id,),
        )
        if cursor.fetchone():
            return

    cursor.execute(
        """
        INSERT INTO conversations
        (customer_id, call_sid, event_id, speaker, message)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (
            customer_id,
            call_sid,
            event_id,
            speaker,
            message
        )
    )
    conn.commit()
