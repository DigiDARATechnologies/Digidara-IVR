"""
Twilio ConversationRelay WebSocket handler for English calls.

Why this is faster than Gather/Respond:
- OLD: Customer stops -> Twilio waits for silence (~600ms) -> HTTP POST -> process -> respond
- NEW: Customer speaks -> Twilio streams partial transcript in real time -> LLM
       starts generating before customer even finishes -> tokens stream back
- Eliminates the ~600ms VAD silence wait entirely.

Tamil calls do NOT use this handler -- they keep using the existing
Gather/Respond flow (Sarvam STT/TTS), which is the only production-ready
option for Tamil.
"""

import asyncio
import json
import os
import re
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

from app.database.db import get_db_connection
from app.services import call_log_service, campaign_service
from app.services.conversation_service import save_conversation
from app.services.groq_service import NO_HALLUCINATION_RULE, async_client, FAST_MODEL, _strip_function_tags
from app.services.memory_service import build_memory_context, get_memory
from app.livekit_agent.memory_kb import search as kb_search, is_simple_turn, get_full_context_for_system_prompt

load_dotenv(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
    override=True,
)

router = APIRouter(tags=["ConversationRelay"])

_KB_CONTEXT = get_full_context_for_system_prompt(lang="en")


def _build_relay_prompt(
    campaign_prompt: str,
    customer_name: str,
    investigated_course: Optional[str],
    internship_or_course: Optional[str],
    memory_context: str,
) -> str:
    for ph, val in [
        ("{customer_name}", customer_name),
        ("{name}", customer_name),
        ("{customer_language}", "english"),
        ("{language}", "english"),
    ]:
        campaign_prompt = campaign_prompt.replace(ph, str(val))

    course_ctx = ""
    if investigated_course:
        ioc = internship_or_course or "course"
        course_ctx = (
            f"\nThis customer previously enquired about {ioc} in {investigated_course}. "
            "Reference this naturally in the conversation.\n"
        )

    return f"""{campaign_prompt}
{course_ctx}
STYLE RULES:
- Speak naturally and warmly, like a real DigiDara advisor on a phone call.
- MAXIMUM 2 short sentences per reply. If customer says "I'm busy" or "quickly" -> ONE sentence only.
- No markdown, no bullet points, no lists. Plain spoken English only.
- Never say you are an AI. You are a DigiDara team member.
- If you don't have specific details (pricing, batch dates): say "I don't have that detail right now -- our team can call you back with the exact information."
- Never invent prices, dates, or policies.

{memory_context if memory_context else ""}

{NO_HALLUCINATION_RULE}

{_KB_CONTEXT}
"""


@router.websocket("/conversation-relay/{customer_id}/{campaign_id}")
async def conversation_relay(websocket: WebSocket, customer_id: int, campaign_id: int):
    """WebSocket endpoint for Twilio ConversationRelay (English calls only)."""
    await websocket.accept()
    await websocket.close(
        code=1008,
        reason="Legacy ConversationRelay disabled; use signed Plivo OpenAI Realtime",
    )
    return
    print(f"[ConversationRelay] Connected | customer={customer_id} campaign={campaign_id}")

    db = get_db_connection()
    call_sid: Optional[str] = None
    history: list = []
    transcript_lines: list = []
    call_start = time.time()
    current_response_task: Optional[asyncio.Task] = None

    try:
        cursor = db.cursor()
        cursor.execute(
            "SELECT name, investigated_course, internship_or_course FROM customers WHERE id = %s",
            (customer_id,)
        )
        cust = cursor.fetchone() or {}
        customer_name = (cust.get("name") or "Customer").strip()
        investigated_course = cust.get("investigated_course", "")
        internship_or_course = cust.get("internship_or_course", "")

        cursor.execute("DELETE FROM conversations WHERE customer_id = %s", (customer_id,))
        db.commit()

        campaign = campaign_service.get_campaign_by_id(db, campaign_id)
        campaign_prompt = campaign.get("ai_prompt", "You are a helpful DigiDara advisor.") if campaign else "You are a helpful DigiDara advisor."

        memory = get_memory(db, customer_id)
        memory_context = build_memory_context(memory)

        base_prompt = _build_relay_prompt(
            campaign_prompt, customer_name, investigated_course, internship_or_course, memory_context,
        )

        async for raw_message in websocket.iter_text():
            try:
                msg = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            event = msg.get("event", "")

            if event == "setup":
                call_sid = msg.get("callSid", "")
                print(f"[ConversationRelay] Call setup | callSid={call_sid}")

                try:
                    existing_log = call_log_service.get_call_log_by_sid(db, call_sid)
                    if existing_log:
                        call_log_service.update_call_log_status(db, call_sid, "in-progress")
                    else:
                        call_log_service.create_call_log(
                            conn=db, customer_id=customer_id, campaign_id=campaign_id,
                            call_sid=call_sid, status="in-progress", call_path="relay",
                        )
                except Exception as e:
                    print(f"[ConversationRelay] Failed to create call log: {e}")

                try:
                    audio_dir = os.path.join(os.getcwd(), "audio_cache")
                    txt_path = os.path.join(audio_dir, f"first_greeting_{customer_id}_{campaign_id}_english.txt")
                    if os.path.exists(txt_path):
                        with open(txt_path, "r", encoding="utf-8") as f:
                            greeting = f.read().strip()
                    else:
                        from app.services.groq_service import generate_response
                        greeting_prompt = (
                            f"{base_prompt}\n\nGREETING: Generate your opening line for this call with "
                            f"{customer_name}. Start with 'Hi {customer_name}, I'm calling from DigiDara "
                            f"Technologies.' then say what you're calling about per the campaign. 2 sentences max."
                        )
                        greeting = await asyncio.to_thread(
                            generate_response, greeting_prompt, "Hello, I'm listening.", []
                        )
                        greeting = (greeting or f"Hi {customer_name}, I'm calling from DigiDara Technologies.").strip()

                    await _stream_text(websocket, greeting)
                    history.append({"role": "assistant", "content": greeting})
                    transcript_lines.append(f"assistant: {greeting}")
                    save_conversation(db, customer_id, "assistant", greeting)

                except Exception as e:
                    print(f"[ConversationRelay] Greeting error: {e}")
                    fallback = f"Hi {customer_name}, I'm calling from DigiDara Technologies."
                    await _stream_text(websocket, fallback)

            elif event == "interrupt":
                if current_response_task and not current_response_task.done():
                    current_response_task.cancel()
                    print("[ConversationRelay] Response interrupted by customer")

            elif event == "prompt":
                customer_text = msg.get("voicePrompt", "").strip()
                if not customer_text:
                    continue

                print(f"[ConversationRelay] Customer: '{customer_text}'")
                transcript_lines.append(f"user: {customer_text}")
                history.append({"role": "user", "content": customer_text})
                save_conversation(db, customer_id, "user", customer_text)

                if current_response_task and not current_response_task.done():
                    current_response_task.cancel()

                current_response_task = asyncio.create_task(
                    _generate_and_stream(
                        websocket=websocket, base_prompt=base_prompt,
                        customer_message=customer_text, history=history[:-1],
                        db=db, customer_id=customer_id,
                        transcript_lines=transcript_lines, history_list=history,
                    )
                )

    except WebSocketDisconnect:
        print(f"[ConversationRelay] WebSocket disconnected | customer={customer_id}")
    except Exception as e:
        print(f"[ConversationRelay] Error: {e}")
    finally:
        if current_response_task and not current_response_task.done():
            current_response_task.cancel()

        duration_secs = int(time.time() - call_start)
        transcript = "\n".join(transcript_lines)

        if call_sid and transcript:
            try:
                call_log_service.finalize_call_log(
                    conn=db, call_sid=call_sid, status="completed",
                    duration=duration_secs, transcript=transcript, customer_id=customer_id,
                )
                print(f"[ConversationRelay] Call log finalized | duration={duration_secs}s")
            except Exception as e:
                print(f"[ConversationRelay] Failed to finalize call log: {e}")

        db.close()
        print(f"[ConversationRelay] Session closed | customer={customer_id}")


async def _generate_and_stream(
    websocket: WebSocket, base_prompt: str, customer_message: str, history: list,
    db, customer_id: int, transcript_lines: list, history_list: list,
) -> None:
    """Streams a Groq response to Twilio ConversationRelay using smart in-memory RAG routing."""
    try:
        prompt = base_prompt
        if not is_simple_turn(customer_message):
            kb_result = kb_search(customer_message, lang="en", top_k=3)
            if kb_result:
                prompt = f"{base_prompt}\n\nRELEVANT KNOWLEDGE FOR THIS QUESTION:\n{kb_result}"

        full_reply = ""
        t_start = time.time()

        messages = [{"role": "system", "content": prompt}]
        for msg in (history or []):
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        messages.append({"role": "user", "content": customer_message})

        if async_client is None:
            from app.services.groq_service import generate_response
            reply = await asyncio.to_thread(generate_response, prompt, customer_message, history)
            reply = (reply or "").strip()
            await _stream_text(websocket, reply)
            full_reply = reply
        else:
            stream = await async_client.chat.completions.create(
                model=FAST_MODEL, messages=messages, stream=True, max_tokens=100,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if not delta:
                    continue
                full_reply += delta
                cleaned = _strip_function_tags(delta)
                if cleaned:
                    await websocket.send_text(json.dumps({"type": "text", "token": cleaned, "last": False}))

            await websocket.send_text(json.dumps({"type": "text", "token": "", "last": True}))

            latency_ms = int((time.time() - t_start) * 1000)
            print(f"[ConversationRelay] Response in {latency_ms}ms: '{full_reply[:80]}'")

        full_reply = _strip_function_tags(full_reply).strip()

        parts = re.split(r'(?<=[.!?।])\s+', full_reply)
        if len(parts) > 2:
            full_reply = " ".join(parts[:2])

        if full_reply:
            history_list.append({"role": "assistant", "content": full_reply})
            transcript_lines.append(f"assistant: {full_reply}")
            save_conversation(db, customer_id, "assistant", full_reply)

        goodbye_words = [
            "goodbye", "bye", "take care", "have a great day",
            "have a nice day", "see you", "thank you for your time",
        ]
        if any(w in full_reply.lower() for w in goodbye_words):
            await asyncio.sleep(2.0)
            await websocket.send_text(json.dumps({"type": "end"}))

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[ConversationRelay] Generation error: {e}")
        try:
            await _stream_text(websocket, "I'm sorry, could you repeat that?")
        except Exception:
            pass


async def _stream_text(websocket: WebSocket, text: str) -> None:
    """Streams text word-by-word to Twilio (Twilio converts to speech natively)."""
    if not text:
        return
    words = text.split()
    for i, word in enumerate(words):
        is_last = (i == len(words) - 1)
        token = word if is_last else f"{word} "
        await websocket.send_text(json.dumps({"type": "text", "token": token, "last": is_last}))
        await asyncio.sleep(0)
