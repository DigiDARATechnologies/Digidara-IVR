from fastapi import APIRouter, Depends
import os
import httpx
from pydantic import BaseModel

from app.services.groq_service import generate_response
from app.services.campaign_service import get_campaign_prompt
from app.services.conversation_service import save_conversation
from app.database.db import get_db
from app.api.auth import current_admin
from app.services import customer_service
from app.livekit_agent.memory_kb import search as search_memory_kb

router = APIRouter(tags=["AI"], dependencies=[Depends(current_admin)])

class ChatRequest(BaseModel):
    message: str
    page: str | None = None

def _dashboard_reply(prompt: str, question: str) -> str:
    if os.getenv("GROQ_API_KEY"):
        return generate_response(prompt, question)
    api_key=os.getenv("OPENAI_API_KEY","")
    if not api_key: return "The dashboard assistant needs OPENAI_API_KEY or GROQ_API_KEY to answer questions."
    knowledge=search_memory_kb(question,lang="ta" if any("\u0b80" <= c <= "\u0bff" for c in question) else "en",top_k=4)
    payload={"model":os.getenv("OPENAI_CHAT_MODEL","gpt-4.1-mini"),"instructions":prompt+"\n\nAPPROVED KNOWLEDGE:\n"+knowledge,"input":question,"max_output_tokens":300}
    try:
        response=httpx.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {api_key}"},json=payload,timeout=25)
        response.raise_for_status(); data=response.json()
        if data.get("output_text"): return data["output_text"].strip()
        return "".join(part.get("text","") for item in data.get("output",[]) for part in item.get("content",[]) if part.get("type")=="output_text").strip() or "No answer was returned."
    except Exception as exc:
        print(f"[Dashboard assistant] provider request failed: {exc}")
        return "I could not reach the configured AI provider. Please check the API key and model settings."

@router.post("/assistant/chat")
def website_assistant(data: ChatRequest, admin=Depends(current_admin), db=Depends(get_db)):
    """Ground the floating dashboard assistant in live aggregate data + RAG.

    It intentionally excludes phone numbers, emails and transcript bodies.
    """
    cur=db.cursor()
    organization_id = admin["organization_id"]
    cur.execute("SELECT COUNT(*) customers FROM customers WHERE organization_id=%s AND deleted_at IS NULL", (organization_id,))
    customers=(cur.fetchone() or {}).get("customers",0)
    cur.execute("SELECT COUNT(*) campaigns FROM campaigns WHERE organization_id=%s", (organization_id,))
    campaigns=(cur.fetchone() or {}).get("campaigns",0)
    cur.execute("""SELECT COUNT(*) calls,
      SUM(CASE WHEN qualification IN ('hot','warm','qualified') THEN 1 ELSE 0 END) qualified,
      AVG(NULLIF(avg_response_latency_ms,0)) latency,
      SUM(CASE WHEN LOWER(language)='tamil' THEN 1 ELSE 0 END) tamil,
      SUM(CASE WHEN LOWER(language)='english' THEN 1 ELSE 0 END) english
      FROM call_logs WHERE organization_id=%s""", (organization_id,))
    calls=cur.fetchone() or {}
    cur.execute("SELECT campaign_name FROM campaigns WHERE organization_id=%s ORDER BY id DESC LIMIT 20", (organization_id,))
    campaign_rows=cur.fetchall()
    live_context={"customers":customers,"campaigns":campaigns,"calls":calls.get("calls") or 0,
      "qualified_leads":calls.get("qualified") or 0,"average_latency_ms":round(float(calls.get("latency") or 0)),
      "english_calls":calls.get("english") or 0,"tamil_calls":calls.get("tamil") or 0,
      "campaign_list":campaign_rows,"current_page":data.page or "dashboard"}
    prompt=("You are the DigiDara dashboard assistant. Answer only questions about this DigiDara application, "
      "its live business metrics, campaigns, AI voice-agent operation, courses/services in retrieved knowledge, "
      "and how to use the current page. Never expose secrets or personal customer data. If live data or approved "
      "knowledge does not contain the answer, say that clearly. Keep replies concise.\n\nLIVE DASHBOARD DATA:\n"+str(live_context))
    reply=_dashboard_reply(prompt,data.message)
    cur.execute("INSERT INTO assistant_chat_messages (organization_id,user_id,role,message,page_path) VALUES (%s,%s,'user',%s,%s)",(organization_id,admin["id"],data.message,data.page))
    cur.execute("INSERT INTO assistant_chat_messages (organization_id,user_id,role,message,page_path) VALUES (%s,%s,'assistant',%s,%s)",(organization_id,admin["id"],reply,data.page)); db.commit()
    return {"reply":reply}


@router.post("/ai/chat/{campaign_id}")
def chat(
    campaign_id: int, data: ChatRequest, admin=Depends(current_admin),
    db=Depends(get_db),
):
    prompt = get_campaign_prompt(
        db, campaign_id, admin["organization_id"]
    )

    if not prompt:
        return {
            "error": "Campaign not found"
        }

    reply = generate_response(
        prompt,
        data.message
    )

    return {
        "reply": reply
    }


@router.post("/ai/chat/{campaign_id}/{customer_id}")
def chat_with_customer(
    campaign_id: int, customer_id: int, data: ChatRequest,
    admin=Depends(current_admin), db=Depends(get_db),
):
    organization_id = admin["organization_id"]
    prompt = get_campaign_prompt(
        db, campaign_id, organization_id
    )

    if not prompt:
        return {
            "error": "Campaign not found"
        }

    if not customer_service.get_customer_by_id(db, customer_id, organization_id):
        return {"error": "Customer not found"}

    # Save user's message to conversation history
    save_conversation(db, customer_id, "user", data.message)

    # Generate response
    reply = generate_response(
        prompt,
        data.message
    )

    # Save AI response to conversation history
    save_conversation(db, customer_id, "assistant", reply)

    return {
        "reply": reply
    }
