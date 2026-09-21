"""
Structured lead extraction and scoring.

Extends the existing call-analysis step (app/services/groq_service.py ->
analyze_conversation) with a dedicated extraction pass that pulls out the
specific structured fields requested for lead qualification:
    name, phone, company, requirement, budget, timeline
The score and tier are intentionally excluded: call analysis owns the single
persisted lead-score decision and this pass only extracts descriptive fields.

This is intentionally a SEPARATE function (not merged into
analyze_conversation) so it can be called independently — e.g. from the
text-chat Playground, or re-run later on an existing transcript — without
re-running the full call summary/follow-up-date analysis.
"""

import json
import re
from typing import Any, Dict, Optional

from groq import Groq

from app.services.groq_service import api_key

client = Groq(api_key=api_key) if api_key and api_key != "mock_key_placeholder" else None

EXTRACTION_PROMPT = """
You are a lead-qualification assistant. Read the phone call transcript below
and extract ONLY information that was explicitly stated by the customer.
Never guess, infer, or invent a value that wasn't actually said.

Return ONLY a raw JSON object (no markdown, no code fences) with exactly
these fields:

{
  "name": "Customer's name if mentioned, else null",
  "phone": "Phone number if mentioned in the conversation, else null",
  "company": "Company or organization name if mentioned, else null",
  "requirement": "A short phrase describing what the customer is interested in (course, service, internship, etc.), else null",
  "budget": "Any budget or pricing constraint the customer mentioned, else null",
  "timeline": "When the customer wants to start/join/be contacted, else null"
}

Rules:
- If a field was never mentioned, use null (not an empty string, not a guess).
- Do not fabricate a phone number, company, or budget that wasn't said.
"""


def _strip_json_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return cleaned


def extract_lead_fields(conversation_text: str) -> Dict[str, Any]:
    """
    Runs structured lead-field extraction over a conversation transcript.
    Returns a dict matching the schema above. On any failure (missing API
    key, malformed JSON, API error), returns a safe all-null/zero default
    instead of raising — this must never crash call finalization.
    """
    default: Dict[str, Any] = {
        "name": None,
        "phone": None,
        "company": None,
        "requirement": None,
        "budget": None,
        "timeline": None,
    }

    if client is None or not conversation_text or not conversation_text.strip():
        return default

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": conversation_text},
            ],
            temperature=0.1,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(_strip_json_fences(raw))

        result = {**default, **{k: v for k, v in parsed.items() if k in default}}

        return result
    except Exception as e:
        print(f"[LeadExtraction] Failed to extract lead fields: {e}")
        return default
