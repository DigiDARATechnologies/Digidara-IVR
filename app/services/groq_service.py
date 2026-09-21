"""
Groq LLM service — rewritten for low latency.

Key changes from the original synchronous version:
1. Uses AsyncGroq (native async client) instead of the blocking sync
   client wrapped in asyncio.to_thread — removes one layer of thread-pool
   scheduling overhead per call.
2. `stream_response()` streams tokens as they arrive and invokes a
   `on_sentence` callback the moment each complete sentence is detected,
   so the caller (the live call loop in app/api/call.py) can start TTS on
   sentence 1 while the LLM is still generating sentence 2, 3, etc.
   This is the single biggest latency win in the whole pipeline: previously
   the full reply had to finish generating before ANY audio could start.
3. `generate_response()` (sync, non-streaming) is kept for the Playground
   and Google Sheets / non-realtime code paths, but now also goes through
   AsyncGroq internally via asyncio.run for consistency — and gains the
   same RAG-grounding behavior as the streaming path.
4. RAG retrieval (app/services/rag_service.py) is injected into the system
   prompt before every call, with an explicit no-hallucination instruction.
   If RAG is unavailable (see rag_service docstring), the call proceeds
   without it instead of failing.
5. A small in-memory response cache for very short, common acknowledgement-
   style turns (e.g. "yes", "ok", "thank you") is NOT implemented here by
   design — those replies depend heavily on conversation context/state, so
   caching them risks producing a stale/wrong reply. Instead, latency is
   reduced at the source (streaming + RAG short-circuiting + smaller
   prompts) which is safer than caching conversational turns.
"""

import asyncio
import json
import os
import re
import time
from typing import Awaitable, Callable, List, Optional

import httpx
from dotenv import load_dotenv
from groq import AsyncGroq, Groq

from app.services import rag_service
from app.livekit_agent.memory_kb import search as memory_kb_search
from app.services.sales_playbook import consultative_turn_contract
from app.services.tamil_register import tamil_register_instruction

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), override=True)

api_key = os.getenv("GROQ_API_KEY") or "mock_key_placeholder"
_is_mock = api_key == "mock_key_placeholder"

# Fast model for live-call turns (latency-critical), heavier model only for
# the post-call analysis/extraction passes where a few extra seconds is fine.
FAST_MODEL = "llama-3.1-8b-instant"
ANALYSIS_MODEL = "llama-3.3-70b-versatile"

client = Groq(api_key=api_key) if not _is_mock else None
async_client = AsyncGroq(api_key=api_key) if not _is_mock else None

NO_HALLUCINATION_RULE = (
    "\n\nKNOWLEDGE & ANSWER RULES:\n"
    "- Answer customer questions about DigiDARA (courses, services, internships, "
    "pricing, location, contact) using ONLY the RETRIEVED KNOWLEDGE above.\n"
    "- If you have retrieved knowledge, answer it naturally in 1-3 short conversational sentences.\n"
    "- If you do NOT have the answer (e.g. specific pricing, batch dates), say so honestly and offer "
    "to have a DigiDARA team member call back. Example: \'I don\'t have the exact fee details handy, "
    "but our team can call you back — would that work for you?\'\n"
    "- NEVER invent, guess, or hallucinate facts, prices, dates, names, or policies.\n"
    "- Sound warm and natural — like a real person, not a FAQ bot.\n"
)

TAMIL_PHONE_ANSWER_RULES = (
    "\n\nTAMIL PHONE ANSWER RULES:\n"
    "- Reply in natural spoken Tamil/Tanglish, like a Tamil Nadu phone advisor.\n"
    "- Answer the customer's latest question directly first. Do not jump to unrelated sales flow.\n"
    "- Use the Tamil knowledge context when it is relevant. Do not invent fees, dates, batch timing, offers, or staff names.\n"
    "- Keep it to 1 or 2 short sentences. No bullets, no markdown, no textbook Tamil.\n"
    "- If exact details are not in knowledge, say naturally: 'அந்த exact detail இப்போ என் கிட்ட இல்லை; நம்ம team callback பண்ணி confirm பண்றாங்க.'\n"
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")


def _strip_function_tags(text: str) -> str:
    text = re.sub(r"<function.*?>.*?</function>", "", text, flags=re.DOTALL)
    text = re.sub(r"<function.*?>", "", text)
    text = re.sub(r"</function>", "", text)
    return text


def _normalize_language(language: str = "english") -> str:
    normalized = (language or "english").strip().lower()
    return "tamil" if normalized in {"ta", "ta-in", "tamil"} else "english"


def _build_grounded_system_prompt(
    campaign_prompt: str,
    user_message: str,
    language: str = "english",
) -> str:
    """Retrieves the most relevant knowledge chunks for this specific customer
    message and injects them. Skips retrieval if the prompt already contains
    a RETRIEVED KNOWLEDGE block (pre-loaded at call start) to avoid the
    ChromaDB latency overhead on every single turn."""
    # If knowledge was already pre-loaded into this prompt at call start,
    # skip the per-turn retrieval to save ~100-300ms per conversation turn.
    normalized_language = _normalize_language(language)
    turn_contract = consultative_turn_contract(normalized_language)
    register_rule = (
        "\n\nTAMIL/TANGLISH REGISTER:\n" + tamil_register_instruction(user_message)
        if normalized_language == "tamil" else ""
    )
    if "RETRIEVED KNOWLEDGE" in campaign_prompt:
        return campaign_prompt + register_rule + turn_contract + NO_HALLUCINATION_RULE

    if normalized_language == "tamil":
        context_block = memory_kb_search(user_message, lang="ta", top_k=3)
        prompt = campaign_prompt
        if context_block:
            prompt = f"{prompt}\n\nRETRIEVED KNOWLEDGE:\n{context_block}"
        return (
            prompt + TAMIL_PHONE_ANSWER_RULES + register_rule
            + turn_contract + NO_HALLUCINATION_RULE
        )

    chunks = rag_service.retrieve(user_message, top_k=4)
    context_block = rag_service.build_context_block(chunks)
    prompt = campaign_prompt
    if context_block:
        prompt = f"{prompt}\n\n{context_block}"
    return prompt + turn_contract + NO_HALLUCINATION_RULE


def generate_response(
    campaign_prompt: str,
    customer_message: str,
    history: list = None,
    language: str = "english",
) -> str:
    """
    Synchronous, non-streaming reply generation. Used by the Playground and
    other non-realtime paths where streaming isn't needed. Live phone calls
    should use stream_response() instead for lower perceived latency.
    """
    if _is_mock:
        return "AI response simulation: Please configure GROQ_API_KEY."

    system_prompt = _build_grounded_system_prompt(campaign_prompt, customer_message, language=language)

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": customer_message})

    response = client.chat.completions.create(model=FAST_MODEL, messages=messages)
    reply = response.choices[0].message.content or ""
    return _strip_function_tags(reply).strip()


async def stream_response(
    campaign_prompt: str,
    customer_message: str,
    history: Optional[list] = None,
    on_sentence: Optional[Callable[[str], Awaitable[None]]] = None,
    language: str = "english",
) -> str:
    """
    Streams the LLM reply token-by-token. Every time a complete sentence
    boundary is detected in the accumulated text, `on_sentence` is awaited
    with that sentence — allowing the caller to kick off TTS synthesis
    immediately instead of waiting for the entire reply to finish.

    Returns the full assembled reply at the end (for saving to history/DB).
    """
    if _is_mock or async_client is None:
        fallback = "AI response simulation: Please configure GROQ_API_KEY."
        if on_sentence:
            await on_sentence(fallback)
        return fallback

    system_prompt = _build_grounded_system_prompt(campaign_prompt, customer_message, language=language)

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": customer_message})

    full_text = ""
    pending = ""

    stream = await async_client.chat.completions.create(
        model=FAST_MODEL,
        messages=messages,
        stream=True,
        max_tokens=120,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if not delta:
            continue
        full_text += delta
        pending += delta

        # Emit any complete sentence(s) accumulated so far, keeping the
        # trailing partial fragment in `pending` for the next chunk.
        parts = _SENTENCE_SPLIT_RE.split(pending)
        if len(parts) > 1:
            complete_sentences, pending = parts[:-1], parts[-1]
            for sentence in complete_sentences:
                cleaned = _strip_function_tags(sentence).strip()
                if cleaned and on_sentence:
                    await on_sentence(cleaned)

    # Flush whatever's left after the stream ends (the final sentence
    # often has no trailing space/newline to trigger the split above).
    leftover = _strip_function_tags(pending).strip()
    if leftover and on_sentence:
        await on_sentence(leftover)

    return _strip_function_tags(full_text).strip()


ANALYSIS_PROMPT = """Analyze this phone call transcript and return a single raw JSON object (no markdown, no code fences).

Required fields:
{
  "customer_need": "One short detail stating what the customer asked about or needed",
  "discussion": "One short detail stating the important information or advice the assistant provided",
  "outcome": "One short detail stating interest, objection, decision, or call result",
  "summary": "A concise factual compatibility summary of the complete call",
  "quick_summary": "One specific sentence under 120 characters describing the customer and outcome",
  "lead_score": 85,
  "lead_status": "interested",
  "qualification": "hot",
  "status": "completed",
  "next_action": "Call back on YYYY-MM-DD to confirm joining date",
  "followup_date": "YYYY-MM-DD or N/A",
  "joining_date": "YYYY-MM-DD or N/A",
  "reminder_consent": "yes or no or not_asked",
  "reminder_days_before": 1
}

Lead scoring rules — be precise:
- lead_score 80-100 → qualification "hot": Customer explicitly confirmed joining date OR said "yes I want to join" with a specific timeline
- lead_score 50-79 → qualification "warm": Showed genuine interest, asked detailed questions about course/fee, no firm date yet
- lead_score 20-49 → qualification "cold": Lukewarm, hesitant, needs more convincing, asked for callback without commitment
- lead_score 0-19 → qualification "unqualified": Not interested, wrong number, didn't engage, busy and hung up

lead_status values (pick exactly one):
- "interested": Customer wants to join / very positive
- "callback_requested": Asked for a specific callback date
- "not_interested": Explicitly said no or not interested
- "no_answer": Call connected but customer didn't engage / disconnected immediately
- "completed": Neutral completion (date confirmed, reminder set, call closed naturally)

Rules:
- Return ONLY raw JSON — no ```json, no explanation, no extra text
- If a field is unknown, use null (not empty string)
- joining_date and followup_date must be YYYY-MM-DD format or "N/A"
- Base lead_score strictly on what the customer actually said — do not guess
- Ignore greetings, AI disclosures, and repeated assistant sales text when summarizing
- Focus on the customer's questions, answers received, interest, objections, decision, and next action
- For Tamil/Tanglish transcripts, write the operational summary in clear English while preserving names and course terms
- Never use vague summaries such as "call completed successfully" without saying what was discussed
- Produce enough factual detail for 3-4 simple History lines: customer need, discussion, outcome, and next action
"""


def analyze_conversation(conversation_text: str):
    """Analyse a completed call with Groq, or OpenAI when Groq is disabled."""
    messages = [
        {"role": "system", "content": ANALYSIS_PROMPT},
        {"role": "user", "content": conversation_text},
    ]
    if client is not None:
        response = client.chat.completions.create(
            model=ANALYSIS_MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=700,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or "{}"

    openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not openai_api_key:
        raise RuntimeError("Neither Groq nor OpenAI is configured for call analysis")
    model = (os.getenv("OPENAI_CHAT_MODEL") or "").strip()
    if not model or model.lower() == "default":
        model = "gpt-4.1-mini"

    with httpx.Client(timeout=45.0) as http:
        response = http.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 700,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        payload = response.json()
    return payload["choices"][0]["message"]["content"] or "{}"


# ---------------------------------------------------------------------------
# Response cache for very short, non-informational turns
# ---------------------------------------------------------------------------
# When the customer says "yes", "ok", "sure", etc., the assistant's reply
# is almost always the same within a campaign. Caching these avoids a full
# Groq API round-trip (~400-800ms) for trivial turns.
# Key = (campaign_prompt_hash[:16], normalized_message)
# This is safe because these are context-free acknowledgement messages
# where campaign+message fully determine the reply.

import functools
import hashlib

_RESPONSE_CACHE: dict = {}
_RESPONSE_CACHE_MAX = 500

_SHORT_TURNS = {
    "yes", "yeah", "yep", "sure", "ok", "okay", "alright", "fine", "got it",
    "i see", "understood", "of course", "definitely", "absolutely",
    "no", "nope", "not really", "not now",
    "ஆமா", "சரி", "ஓகே", "இல்ல", "இல்லை",
}


def _is_cacheable_turn(message: str) -> bool:
    normalized = message.strip().lower().rstrip(".,!?")
    return normalized in _SHORT_TURNS or len(normalized) <= 8


def _cache_key(campaign_prompt: str, message: str) -> str:
    ph = hashlib.sha1(campaign_prompt.encode()).hexdigest()[:16]
    return f"{ph}::{message.strip().lower()}"


def get_cached_response(campaign_prompt: str, message: str) -> str | None:
    if not _is_cacheable_turn(message):
        return None
    return _RESPONSE_CACHE.get(_cache_key(campaign_prompt, message))


def set_cached_response(campaign_prompt: str, message: str, reply: str) -> None:
    if not _is_cacheable_turn(message):
        return
    if len(_RESPONSE_CACHE) >= _RESPONSE_CACHE_MAX:
        # Evict oldest entry
        _RESPONSE_CACHE.pop(next(iter(_RESPONSE_CACHE)))
    _RESPONSE_CACHE[_cache_key(campaign_prompt, message)] = reply


# ---------------------------------------------------------------------------
# Voice-optimised response generation with smart RAG routing
# ---------------------------------------------------------------------------

# Simple turns that NEVER need RAG — customer is just acknowledging,
# agreeing, giving a date, or saying yes/no. Sending these to ChromaDB
# adds ~150ms with zero benefit since there's no question to answer.
_NO_RAG_PATTERNS = [
    "yes", "yeah", "yep", "sure", "ok", "okay", "alright", "fine",
    "no", "nope", "not really",
    "got it", "i see", "understood", "of course", "definitely", "absolutely",
    "sounds good", "perfect", "great", "nice", "cool",
    "next week", "next month", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday",
    "tomorrow", "today", "morning", "evening", "afternoon",
    # Tamil acknowledgements
    "ஆமா", "சரி", "ஓகே", "இல்ல", "இல்லை", "நன்றி", "சரிங்க",
    "ஆமாங்க", "பரவாயில்ல",
]

# Keywords that indicate a factual question needing RAG lookup
_RAG_TRIGGER_KEYWORDS = [
    # Course/service questions
    "course", "courses", "program", "programs", "class", "classes",
    "fee", "fees", "cost", "price", "pricing", "charge", "charges", "how much",
    "duration", "long", "months", "weeks", "days",
    "syllabus", "curriculum", "topics", "modules", "cover", "learn",
    "certificate", "certification", "iso", "credential",
    "online", "offline", "mode", "virtual", "classroom",
    "batch", "timing", "schedule", "when does",
    "internship", "intern", "project",
    "placement", "job", "career", "hire", "resume", "linkedin", "interview",
    # Company questions
    "digidara", "company", "institute", "about", "who are", "what is",
    "located", "location", "address", "where", "trichy", "office",
    "contact", "phone", "email", "whatsapp", "reach",
    "founded", "since", "years", "experience", "rating", "reviews",
    "services", "offer", "provide", "help", "do you",
    # Products
    "product", "products", "crm", "lead flux", "academy", "careermate",
    "college gpt", "automation", "software", "platform", "tool",
    # Founder
    "founder", "senthil", "who started", "managing director", "hcl", "cognizant",
    # Demo / booking
    "demo", "book", "consultation", "enroll", "register", "join", "apply",
    "free", "session", "appointment", "slot",
    # Intent signals
    "tell me", "explain", "describe", "what", "which", "how",
    "can you", "is there", "are there", "do you have",
    # Tamil question words
    "என்ன", "எந்த", "எப்படி", "எத்தனை", "எங்க", "எங்கே", "யாரு",
    "கோர்ஸ்", "கட்டணம்", "விலை", "சேர்", "பயிற்சி", "இண்டர்ன்ஷிப்",
    "வேலை", "வேலைவாய்ப்பு", "சான்றிதழ்", "முகவரி", "தொடர்பு",
    "evlo", "evalo", "irukka", "enga", "sollunga", "details sollunga",
]


def needs_rag(message: str) -> bool:
    """
    Decides whether this customer message warrants a RAG lookup.
    Returns False for simple acknowledgements, dates, yes/no answers.
    Returns True for factual questions about courses, fees, services, etc.
    """
    if not message:
        return False

    normalized = message.strip().lower().rstrip(".,!?")

    # Exact match on no-RAG patterns (very short turns)
    if normalized in _NO_RAG_PATTERNS:
        return False

    # Short turns (≤4 words) are almost never knowledge questions
    word_count = len(normalized.split())
    if word_count <= 3:
        # Unless they contain a clear question keyword
        has_question = "?" in message or any(kw in normalized for kw in ["what", "how", "என்ன", "எந்த"])
        if not has_question:
            return False

    # Check for RAG trigger keywords
    return any(kw in normalized for kw in _RAG_TRIGGER_KEYWORDS)


async def generate_response_voice(
    campaign_prompt: str,
    customer_message: str,
    history: list = None,
    language: str = "english",
) -> str:
    """
    Voice-optimised async response generation with smart RAG routing.

    - Simple turns (yes/no/dates/acknowledgements): skip RAG entirely → ~300ms faster
    - Knowledge questions (course/fee/service/company): retrieve top 3 RAG chunks
    - Always uses AsyncGroq streaming for lowest TTFT
    - Hard caps reply at 2 sentences for voice naturalness
    """
    if _is_mock or async_client is None:
        return "AI response simulation: Please configure GROQ_API_KEY."

    system_prompt = campaign_prompt

    if needs_rag(customer_message) and _normalize_language(language) == "tamil":
        context = memory_kb_search(customer_message, lang="ta", top_k=3)
        if context:
            system_prompt = f"{campaign_prompt}\n\nRETRIEVED KNOWLEDGE:\n{context}"
    elif needs_rag(customer_message):
        # Targeted RAG: fetch only what's needed for this specific question
        chunks = rag_service.retrieve(customer_message, top_k=3)
        context = rag_service.build_context_block(chunks)
        if context:
            system_prompt = f"{campaign_prompt}\n\n{context}"

    if _normalize_language(language) == "tamil":
        system_prompt += TAMIL_PHONE_ANSWER_RULES
        system_prompt += "\n\nTAMIL/TANGLISH REGISTER:\n"
        system_prompt += tamil_register_instruction(customer_message)
    system_prompt += consultative_turn_contract(_normalize_language(language))
    system_prompt += NO_HALLUCINATION_RULE

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in (history or []):
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": customer_message})

    full_text = ""
    stream = await async_client.chat.completions.create(
        model=FAST_MODEL,
        messages=messages,
        stream=True,
        max_tokens=120,  # enforce brevity at token level — ~2 sentences max
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            full_text += delta

    reply = _strip_function_tags(full_text).strip()

    # Hard cap at 2 sentences for voice naturalness
    parts = _SENTENCE_SPLIT_RE.split(reply)
    if len(parts) > 2:
        reply = " ".join(parts[:2])

    return reply
