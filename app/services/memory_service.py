"""
Structured conversation memory.

The original `conversation_service.py` only logged raw (speaker, message)
rows — there was no structured memory of WHO the customer is, WHAT they
want, or what's already been asked, which meant every call started from a
blank slate even for a returning customer.

This module adds a `customer_memory` table (one row per customer, upserted
across calls) that tracks:
    - name              (confirmed name, may differ from the CRM record)
    - intent            (what the customer is trying to do/learn/buy)
    - previous_questions (JSON list of distinct questions asked across all calls)
    - lead_status        (latest qualification tier: hot/warm/cold/unqualified)
    - summary             (a running, continuously-updated summary of the
                            relationship so far, rewritten after each call)

It is read at the start of every call (to give the assistant continuity
with a returning customer) and updated at the end of every call.
"""

import json
from typing import Any, Dict, List, Optional


def get_memory(conn: Any, customer_id: int) -> Optional[Dict[str, Any]]:
    """Fetches the structured memory row for a customer, or None if absent."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customer_memory WHERE customer_id = %s", (customer_id,))
    row = cursor.fetchone()
    if not row:
        return None
    try:
        row["previous_questions"] = json.loads(row.get("previous_questions") or "[]")
    except (json.JSONDecodeError, TypeError):
        row["previous_questions"] = []
    return row


def upsert_memory(
    conn: Any,
    customer_id: int,
    name: Optional[str] = None,
    intent: Optional[str] = None,
    new_questions: Optional[List[str]] = None,
    lead_status: Optional[str] = None,
    summary: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates or updates a customer's structured memory. Only the fields
    passed (non-None) are changed; `new_questions` are appended to the
    existing list (deduplicated) rather than replacing it, so memory
    accumulates across multiple calls instead of resetting each time.
    """
    existing = get_memory(conn, customer_id)
    cursor = conn.cursor()

    merged_questions = list(existing["previous_questions"]) if existing else []
    if new_questions:
        for q in new_questions:
            q = q.strip()
            if q and q not in merged_questions:
                merged_questions.append(q)
    # Cap stored history so the table doesn't grow unbounded for very
    # long-running customer relationships.
    merged_questions = merged_questions[-50:]

    final_name = name if name is not None else (existing.get("name") if existing else None)
    final_intent = intent if intent is not None else (existing.get("intent") if existing else None)
    final_lead_status = lead_status if lead_status is not None else (existing.get("lead_status") if existing else None)
    final_summary = summary if summary is not None else (existing.get("summary") if existing else None)

    if existing:
        cursor.execute(
            """
            UPDATE customer_memory
            SET name = %s, intent = %s, previous_questions = %s,
                lead_status = %s, summary = %s, updated_at = CURRENT_TIMESTAMP
            WHERE customer_id = %s
            """,
            (
                final_name,
                final_intent,
                json.dumps(merged_questions),
                final_lead_status,
                final_summary,
                customer_id,
            ),
        )
    else:
        cursor.execute(
            """
            INSERT INTO customer_memory
            (customer_id, name, intent, previous_questions, lead_status, summary)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                customer_id,
                final_name,
                final_intent,
                json.dumps(merged_questions),
                final_lead_status,
                final_summary,
            ),
        )
    conn.commit()
    return get_memory(conn, customer_id) or {}


def build_memory_context(memory: Optional[Dict[str, Any]]) -> str:
    """
    Formats a customer's stored memory into a short system-prompt-ready
    block, giving the assistant continuity with returning customers. Returns
    an empty string if there's no prior memory (first-time caller).
    """
    if not memory:
        return ""

    lines = ["CUSTOMER MEMORY (from previous interactions):"]
    if memory.get("name"):
        lines.append(f"- Known as: {memory['name']}")
    if memory.get("intent"):
        lines.append(f"- Stated intent: {memory['intent']}")
    if memory.get("lead_status"):
        lines.append(f"- Last known lead status: {memory['lead_status']}")
    if memory.get("summary"):
        lines.append(f"- Summary of relationship so far: {memory['summary']}")
    if memory.get("previous_questions"):
        recent = memory["previous_questions"][-5:]
        lines.append(f"- Previously asked: {'; '.join(recent)}")

    if len(lines) == 1:
        return ""  # nothing useful was actually stored
    return "\n".join(lines)


def extract_questions_from_transcript(transcript: str) -> List[str]:
    """
    Pulls customer-asked questions out of a raw transcript (lines starting
    with 'user:' or 'customer:' that end in a question mark), so they can be
    appended to that customer's long-term memory.
    """
    if not transcript:
        return []
    questions = []
    for line in transcript.split("\n"):
        line = line.strip()
        lower = line.lower()
        if lower.startswith("user:") or lower.startswith("customer:"):
            content = line.split(":", 1)[1].strip() if ":" in line else line
            if content.endswith("?"):
                questions.append(content)
    return questions
