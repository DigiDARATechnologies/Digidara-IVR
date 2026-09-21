"""Read-only product analytics built from real application tables.

No demonstration rows are returned. Empty databases produce zero counts and
empty arrays so the frontend can show an honest empty state.
"""
import os

from fastapi import APIRouter, Depends
from app.database.db import get_db
from app.api.auth import current_admin
from app.services.usage_cost_service import provider_cost_summary
from app.services import runtime_readiness_service

router = APIRouter(tags=["Insights"], dependencies=[Depends(current_admin)])

def one(cursor, sql, args=()):
    cursor.execute(sql, args)
    return cursor.fetchone() or {}

@router.get("/dashboard/summary")
def dashboard_summary(admin=Depends(current_admin), db=Depends(get_db)):
    organization_id = admin["organization_id"]
    cur = db.cursor()
    customers = one(cur, "SELECT COUNT(*) total FROM customers WHERE organization_id=%s AND deleted_at IS NULL", (organization_id,))
    campaigns = one(cur, "SELECT COUNT(*) total FROM campaigns WHERE organization_id=%s", (organization_id,))
    calls = one(cur, """SELECT COUNT(*) total,
        SUM(CASE WHEN COALESCE(call_status,status) IN ('completed','answered','in-progress') THEN 1 ELSE 0 END) answered,
        SUM(CASE WHEN qualification IN ('hot','warm','qualified') OR lead_status IN ('hot','warm','qualified') THEN 1 ELSE 0 END) qualified,
        AVG(NULLIF(avg_response_latency_ms,0)) avg_latency,
        AVG(NULLIF(duration,0)) avg_duration,
        SUM(CASE WHEN LOWER(language)='tamil' THEN 1 ELSE 0 END) tamil_calls,
        SUM(CASE WHEN LOWER(language)='english' THEN 1 ELSE 0 END) english_calls,
        SUM(CASE WHEN COALESCE(call_status,status) IN ('initiated','ringing','in-progress','queued') AND created_at >= NOW()-INTERVAL 2 HOUR THEN 1 ELSE 0 END) live_calls,
        COALESCE(SUM(estimated_openai_cost_usd),0) openai_cost,
        COALESCE(SUM(estimated_telephony_cost_usd),0) telephony_cost
        FROM call_logs WHERE organization_id=%s""", (organization_id,))
    cur.execute("""SELECT c.id,c.campaign_name,COUNT(l.id) calls,
        SUM(CASE WHEN l.qualification IN ('hot','warm','qualified') THEN 1 ELSE 0 END) qualified
        FROM campaigns c LEFT JOIN call_logs l
          ON l.campaign_id=c.id AND l.organization_id=c.organization_id
        WHERE c.organization_id=%s
        GROUP BY c.id,c.campaign_name ORDER BY calls DESC LIMIT 10""", (organization_id,))
    performance = cur.fetchall()
    total = int(calls.get("total") or 0)
    answered = int(calls.get("answered") or 0)
    qualified = int(calls.get("qualified") or 0)
    costs = provider_cost_summary(calls.get("openai_cost"), calls.get("telephony_cost"))
    return {
        "customers": int(customers.get("total") or 0), "campaigns": int(campaigns.get("total") or 0),
        "total_calls": total, "answered_calls": answered, "qualified_leads": qualified,
        "answer_rate": round(answered * 100 / total, 2) if total else 0,
        "conversion_rate": round(qualified * 100 / total, 2) if total else 0,
        "avg_response_latency_ms": round(float(calls.get("avg_latency") or 0)),
        "avg_duration_seconds": round(float(calls.get("avg_duration") or 0)),
        "english_calls": int(calls.get("english_calls") or 0), "tamil_calls": int(calls.get("tamil_calls") or 0),
        "live_calls": int(calls.get("live_calls") or 0),
        "estimated_openai_cost_usd": float(calls.get("openai_cost") or 0),
        "estimated_telephony_cost_usd": float(calls.get("telephony_cost") or 0),
        **costs,
        "campaign_performance": performance,
    }

@router.get("/usage/summary")
def usage_summary(admin=Depends(current_admin), db=Depends(get_db)):
    """Provider-token credits and costs, grouped by the customer who consumed them."""
    cur = db.cursor()
    organization_id = admin["organization_id"]
    totals = one(cur, """SELECT COUNT(*) calls,COALESCE(SUM(duration),0) seconds,
        COALESCE(SUM(input_audio_tokens+output_audio_tokens+input_text_tokens+output_text_tokens),0) tokens,
        COALESCE(SUM(estimated_openai_cost_usd),0) openai_usd,
        COALESCE(SUM(estimated_telephony_cost_usd),0) telephony_usd
        FROM call_logs WHERE organization_id=%s""", (organization_id,))
    cur.execute("""SELECT c.id,c.name,COUNT(l.id) calls,COALESCE(SUM(l.duration),0) seconds,
        COALESCE(SUM(l.input_audio_tokens+l.output_audio_tokens+l.input_text_tokens+l.output_text_tokens),0) tokens,
        COALESCE(SUM(l.estimated_openai_cost_usd),0) openai_usd,
        COALESCE(SUM(l.estimated_telephony_cost_usd),0) telephony_usd
        FROM customers c LEFT JOIN call_logs l
          ON l.customer_id=c.id AND l.organization_id=c.organization_id
        WHERE c.organization_id=%s AND c.deleted_at IS NULL
        GROUP BY c.id,c.name ORDER BY openai_usd+telephony_usd DESC""", (organization_id,))
    customers = cur.fetchall()
    for row in customers:
        costs = provider_cost_summary(row.get("openai_usd"), row.get("telephony_usd"))
        row.update(costs)
        # Backward-compatible aliases for existing API consumers.
        row["total_usd"] = costs["openai_estimated_usd"] + costs["plivo_recorded_usd"]
        row["total_inr"] = costs["total_estimated_inr"]
    total_costs = provider_cost_summary(totals.get("openai_usd"), totals.get("telephony_usd"))
    return {
        **totals,
        **total_costs,
        "total_usd": total_costs["openai_estimated_usd"] + total_costs["plivo_recorded_usd"],
        "total_inr": total_costs["total_estimated_inr"],
        "usd_to_inr": total_costs["openai_usd_to_inr"],
        "customers": customers,
    }

@router.get("/analytics/report")
def analytics_report(admin=Depends(current_admin), db=Depends(get_db)):
    cur = db.cursor()
    organization_id = admin["organization_id"]
    cur.execute("""SELECT c.id,c.campaign_name,COUNT(l.id) calls,
        SUM(CASE WHEN COALESCE(l.call_status,l.status)='completed' THEN 1 ELSE 0 END) completed,
        SUM(CASE WHEN l.qualification IN ('hot','warm','qualified') THEN 1 ELSE 0 END) qualified,
        COALESCE(SUM(l.duration),0) seconds,
        COALESCE(SUM(l.estimated_openai_cost_usd),0) openai_usd,
        COALESCE(SUM(l.estimated_telephony_cost_usd),0) telephony_usd
        FROM campaigns c LEFT JOIN call_logs l
          ON l.campaign_id=c.id AND l.organization_id=c.organization_id
        WHERE c.organization_id=%s
        GROUP BY c.id,c.campaign_name ORDER BY qualified DESC,calls DESC""", (organization_id,))
    campaigns = cur.fetchall()
    for row in campaigns:
        calls, qualified = int(row.get("calls") or 0), int(row.get("qualified") or 0)
        row["conversion_rate"] = round(qualified*100/calls,2) if calls else 0
        costs = provider_cost_summary(row.get("openai_usd"), row.get("telephony_usd"))
        row.update(costs)
        row["cost_usd"] = costs["openai_estimated_usd"] + costs["plivo_recorded_usd"]
        row["cost_per_qualified_usd"] = round(row["cost_usd"]/qualified,4) if qualified else 0
        row["cost_per_qualified_inr"] = round(costs["total_estimated_inr"]/qualified,2) if qualified else 0
    cur.execute("""SELECT c.id,c.name,c.language,COUNT(l.id) calls,
        MAX(l.qualification) latest_qualification,COALESCE(SUM(l.duration),0) seconds,
        COALESCE(SUM(l.estimated_openai_cost_usd),0) openai_usd,
        COALESCE(SUM(l.estimated_telephony_cost_usd),0) telephony_usd
        FROM customers c LEFT JOIN call_logs l
          ON l.customer_id=c.id AND l.organization_id=c.organization_id
        WHERE c.organization_id=%s AND c.deleted_at IS NULL
        GROUP BY c.id,c.name,c.language
        ORDER BY openai_usd+telephony_usd DESC""", (organization_id,))
    customer_rows = cur.fetchall()
    for row in customer_rows:
        costs = provider_cost_summary(row.get("openai_usd"), row.get("telephony_usd"))
        row.update(costs)
        row["cost_usd"] = costs["openai_estimated_usd"] + costs["plivo_recorded_usd"]
    return {"campaigns": campaigns, "customers": customer_rows}

@router.get("/system/integrations")
def integrations():
    # Reports configuration presence only; never returns secret values.
    checks = [("Plivo", "PLIVO_AUTH_ID"), ("OpenAI Realtime", "OPENAI_API_KEY"),
              ("Google Sheets", "GOOGLE_SERVICE_ACCOUNT_JSON"), ("ElevenLabs (legacy)", "ELEVENLABS_API_KEY")]
    return [{"name": name, "status": "configured" if bool(os.getenv(key)) else "not_configured"} for name,key in checks]

@router.get("/system/audit-logs")
def audit_logs(limit: int = 100, admin=Depends(current_admin), db=Depends(get_db)):
    cur=db.cursor(); cur.execute("SELECT id,action,resource_type,resource_id,result,created_at FROM audit_logs WHERE organization_id=%s ORDER BY created_at DESC LIMIT %s", (admin["organization_id"],min(max(limit,1),500))); return cur.fetchall()

@router.get("/system/team")
def team(admin=Depends(current_admin), db=Depends(get_db)):
    cur=db.cursor(); cur.execute("SELECT id,full_name,email,role_code,is_active,mfa_enabled,last_login_at FROM app_users WHERE organization_id=%s ORDER BY full_name", (admin["organization_id"],)); return cur.fetchall()

@router.get("/system/security")
def security_status(admin=Depends(current_admin), db=Depends(get_db)):
    del admin
    return runtime_readiness_service.configuration_checks() + [runtime_readiness_service.worker_check(db)]
