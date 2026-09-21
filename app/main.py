import asyncio
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from app.database.db import get_db_connection, init_db
from app.api import customer, campaign, lead_score
from app.api.call import router as call_router
from app.api.chat import router as chat_router
from app.api.rag import router as rag_router
from app.api.openai_realtime import router as openai_realtime_router
from app.api.plivo import router as plivo_router
from app.api.insights import router as insights_router
from app.api.auth import router as auth_router
from app.api.integrations import router as integrations_router
from app.api.provisioning import router as provisioning_router
from app.api.organization_knowledge import router as organization_knowledge_router
from app.api.facility import router as facility_router
from app.api.phone_numbers import router as phone_numbers_router
from app.api.business_hours import router as business_hours_router
from app.api.callbacks import router as callbacks_router
from app.api.crm import router as crm_router
from app.api.transfers import router as transfers_router
from app.api.ivr import router as ivr_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize MySQL database, tables, and auto-migrate any new columns.
    init_db()

    # 2. Bootstrap the RAG knowledge base in a background thread so a slow
    #    embedding-model download on first run doesn't block the server from
    #    accepting requests. If the download fails (e.g. restricted network),
    #    rag_service.is_available() will return False and all RAG calls will
    #    degrade gracefully instead of crashing the live call loop.
    def _init_rag():
        try:
            from app.services import rag_service
            rag_service.ensure_seeded()
            if rag_service.is_available():
                print("[Startup] RAG knowledge base ready.")
            else:
                print(
                    f"[Startup] RAG unavailable — assistant will run without "
                    f"retrieved context. Error: {rag_service.last_error()}"
                )
        except Exception as e:
            print(f"[Startup] RAG init failed: {e}")

    import threading
    threading.Thread(target=_init_rag, daemon=True).start()

    # 3. Pre-cache legacy Tamil fallback phrases only when a legacy engine is
    #    selected. GPT-Realtime streams its own audio and needs no WAV cache.
    def _cache_tamil_fallbacks():
        try:
            from app.api.call import ensure_tamil_fallback_audio_cache
            cached = ensure_tamil_fallback_audio_cache()
            print(f"[Startup] Tamil fallback audio cache ready ({len(cached)} files).")
        except Exception as e:
            print(f"[Startup] Tamil fallback audio cache failed: {e}")

    # GPT-Realtime is the only active call engine; legacy Gemini fallback WAVs
    # must never be generated during startup.

    # 4. Pre-load in-memory knowledge base and build BM25 index (~3ms).
    # English ConversationRelay calls use this — no ChromaDB, no network.
    def _init_memory_kb():
        try:
            from app.livekit_agent.memory_kb import get_index
            get_index(lang="en")
            get_index(lang="ta")
            print("[Startup] In-memory knowledge base ready (BM25 index built).")
        except Exception as e:
            print(f"[Startup] In-memory KB init failed: {e}")

    threading.Thread(target=_init_memory_kb, daemon=True).start()

    yield


app = FastAPI(
    title="DigiDara AI Voice Assistant API",
    version="2.0.0",
    description=(
        "FastAPI backend for the DigiDara AI Voice Calling Agent. "
        "Includes Plivo calling, OpenAI Realtime audio, RAG-grounded "
        "conversation, structured lead extraction, and persistent customer memory."
    ),
    lifespan=lifespan,
)

# Browser API access is explicitly allow-listed. Plivo server-to-server
# webhooks do not require CORS.
cors_origins = [x.strip() for x in os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
)

@app.middleware("http")
async def production_security_headers(request: Request, call_next):
    """Baseline browser hardening and request correlation.

    Authentication, tenant authorization and rate limiting must also be
    enforced at the route/service layer in multi-instance production.
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def bypass_localtunnel(request: Request, call_next):
    """Add bypass-tunnel-reminder header so localtunnel never shows its
    interstitial warning page (which breaks provider webhooks)."""
    try:
        response = await call_next(request)
    except Exception as e:
        if request.url.path in {"/voice/welcome", "/voice/respond"}:
            print(f"[Voice middleware] Recovered from route error on {request.url.path}: {e}")
            import html
            redirect_url = html.escape(str(request.url), quote=True)
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi" language="en-IN">Sorry, I had a small issue. Could you please repeat that?</Say>
    <Redirect method="POST">{redirect_url}</Redirect>
</Response>"""
            response = Response(content=twiml, media_type="application/xml")
            response.headers["bypass-tunnel-reminder"] = "digidara"
            return response
        raise
    response.headers["bypass-tunnel-reminder"] = "digidara"
    return response


# Register routers
app.include_router(customer.router, tags=["Customers"])
app.include_router(campaign.router, tags=["Campaigns"])
app.include_router(chat_router)
app.include_router(lead_score.router)
app.include_router(call_router)
app.include_router(rag_router)
app.include_router(openai_realtime_router)
app.include_router(plivo_router)
app.include_router(insights_router)
app.include_router(auth_router)
app.include_router(integrations_router)
app.include_router(provisioning_router)
app.include_router(organization_knowledge_router)
app.include_router(facility_router)
app.include_router(phone_numbers_router, tags=["Phone Numbers"])
app.include_router(business_hours_router, tags=["Business Hours"])
app.include_router(callbacks_router)
app.include_router(crm_router)
app.include_router(transfers_router)
app.include_router(ivr_router)


@app.get("/")
def read_root():
    return {
        "message": "DigiDara AI Voice Assistant API is running",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health/live", tags=["Health"])
def liveness():
    """Process-level probe; does not disclose configuration or dependencies."""
    return {"status": "live"}


@app.get("/health/ready", tags=["Health"])
def readiness():
    """Dependency probe for deployment orchestration; checks MySQL only."""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 AS ready")
            if not cursor.fetchone():
                raise RuntimeError("database returned no readiness row")
        finally:
            conn.close()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="not ready") from exc
    return {"status": "ready"}
