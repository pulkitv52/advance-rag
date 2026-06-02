from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database import get_session
from src.models.review import DecisionReview

router = APIRouter(prefix="/api/review", tags=["Social Registry Review"])

ALLOWED_ACTIONS = {
    "APPROVE",
    "REJECT",
    "ESCALATE",
    "NEEDS_FIELD_VERIFICATION",
}


class ReviewRequest(BaseModel):
    action: str
    note: Optional[str] = None
    reviewer_id: Optional[str] = "field_officer"


@router.post("/decision/{decision_id}")
async def review_decision(
    decision_id: str,
    request: ReviewRequest,
    session: AsyncSession = Depends(get_session),
):
    action = (request.action or "").strip().upper()
    if action not in ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_REVIEW_ACTION",
                "message": f"Unsupported action '{request.action}'.",
                "action_hint": "Use APPROVE, REJECT, ESCALATE, or NEEDS_FIELD_VERIFICATION.",
                "request_id": f"review:{decision_id}",
            },
        )
    if action in {"REJECT", "ESCALATE"} and not (request.note or "").strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "REVIEW_NOTE_REQUIRED",
                "message": "A note is required for reject/escalate actions.",
                "action_hint": "Add a short reason in the note field and submit again.",
                "request_id": f"review:{decision_id}",
            },
        )

    row = DecisionReview(
        decision_id=decision_id,
        action=action,
        note=(request.note or "").strip() or None,
        reviewed_by=(request.reviewer_id or "field_officer").strip() or "field_officer",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "id": row.id,
        "decision_id": row.decision_id,
        "action": row.action,
        "note": row.note,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at,
    }


@router.get("/decision/{decision_id}/history")
async def review_history(
    decision_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    safe_limit = max(1, min(limit, 200))
    result = await session.exec(
        select(DecisionReview)
        .where(DecisionReview.decision_id == decision_id)
        .order_by(desc(DecisionReview.reviewed_at))
        .limit(safe_limit)
    )
    rows = result.all()
    return {
        "decision_id": decision_id,
        "total": len(rows),
        "history": [
            {
                "id": row.id,
                "action": row.action,
                "note": row.note,
                "reviewed_by": row.reviewed_by,
                "reviewed_at": row.reviewed_at,
            }
            for row in rows
        ],
    }
