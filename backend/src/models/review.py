import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class DecisionReview(SQLModel, table=True):
    """Human-in-the-loop review action for a social-registry decision/alert row."""

    __tablename__ = "decision_reviews"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    decision_id: str = Field(index=True)
    action: str = Field(index=True)  # APPROVE | REJECT | ESCALATE | NEEDS_FIELD_VERIFICATION
    note: Optional[str] = None
    reviewed_by: str = Field(default="field_officer", index=True)
    reviewed_at: datetime = Field(default_factory=datetime.utcnow, index=True)
