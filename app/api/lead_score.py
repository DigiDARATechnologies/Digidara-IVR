from fastapi import APIRouter, Depends
from typing import List, Optional

from app.database.db import get_db
from app.api.auth import current_admin
from app.schemas.lead_score import LeadScoreRequest
from app.services.lead_scoring import calculate_preview_score

router = APIRouter(tags=["Lead Scoring"], dependencies=[Depends(current_admin)])


@router.post("/lead-score/preview", summary="Preview a non-persisted rule-based score")
def preview_score(data: LeadScoreRequest):
    return calculate_preview_score(
        interested=data.interested,
        budget=data.budget,
        decision_maker=data.decision_maker,
        callback_requested=data.callback_requested
    )


@router.post("/lead-score", deprecated=True, summary="Deprecated alias for score preview")
def generate_score(data: LeadScoreRequest):
    """Compatibility alias. Post-call LLM analysis remains the persisted source of truth."""
    return preview_score(data)


@router.get("/lead-qualifications", summary="List all structured lead qualification records")
def list_lead_qualifications(
    customer_id: Optional[int] = None,
    qualification: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    admin=Depends(current_admin),
    db=Depends(get_db)
):
    """
    Returns structured lead-extraction records (name, phone, company,
    requirement, budget, timeline, score) generated after each completed call.
    Filterable by customer_id and qualification tier.
    """
    cursor = db.cursor()
    conditions = ["c.organization_id = %s"]
    params = [admin["organization_id"]]
    if customer_id:
        conditions.append("lq.customer_id = %s")
        params.append(customer_id)
    if qualification:
        conditions.append("lq.qualification = %s")
        params.append(qualification)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    cursor.execute(
        f"""
        SELECT lq.*, c.name as customer_name, c.email as customer_email
        FROM lead_qualifications lq
        LEFT JOIN customers c ON lq.customer_id = c.id
        {where}
        ORDER BY lq.id DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit, skip],
    )
    rows = cursor.fetchall()
    return rows or []


@router.get("/customer-memory/{customer_id}", summary="Get structured memory for a customer")
def get_customer_memory(
    customer_id: int, admin=Depends(current_admin), db=Depends(get_db),
):
    """
    Returns the structured memory record for a customer: their confirmed
    name, stated intent, previously-asked questions, current lead status,
    and a running relationship summary updated after each call.
    """
    cursor = db.cursor()
    cursor.execute(
        """SELECT cm.* FROM customer_memory cm
           JOIN customers c ON c.id=cm.customer_id
           WHERE cm.customer_id=%s AND c.organization_id=%s""",
        (customer_id, admin["organization_id"]),
    )
    row = cursor.fetchone()
    if not row:
        return {"customer_id": customer_id, "message": "No memory recorded yet for this customer."}
    import json
    try:
        row["previous_questions"] = json.loads(row.get("previous_questions") or "[]")
    except Exception:
        row["previous_questions"] = []
    return row
