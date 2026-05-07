import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class EligibilityRule(SQLModel, table=True):
    """Structured eligibility metadata extracted from policy documents."""

    __tablename__ = "eligibility_rules"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    document_id: Optional[str] = Field(default=None, foreign_key="documents.id", index=True)
    scheme_id: str = Field(index=True)
    rule_name: str
    rule_version: int = 1
    status: str = Field(default="ACTIVE", index=True)

    include_conditions: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    exclude_conditions: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    extracted_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    source_filename: Optional[str] = None
    source_excerpt: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EligibilityDecision(SQLModel, table=True):
    """Per-citizen decision generated using an active eligibility rule."""

    __tablename__ = "eligibility_decisions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    rule_id: str = Field(foreign_key="eligibility_rules.id", index=True)

    citizen_uid: str = Field(index=True)
    beneficiary_id: Optional[str] = Field(default=None, index=True)
    citizen_scheme_id: Optional[str] = Field(default=None, index=True)

    decision: str = Field(index=True)  # INCLUSION_ERROR | EXCLUSION_ERROR | VALID_ENROLLMENT | NOT_APPLICABLE
    reason: str
    evidence_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    identity_match_confidence: float = 1.0
    decision_confidence: float = 0.8

    created_at: datetime = Field(default_factory=datetime.utcnow)


class EligibilitySchemaSignal(SQLModel, table=True):
    """Self-learning registry of criteria fields discovered from policy documents."""

    __tablename__ = "eligibility_schema_signals"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    field_key: str = Field(index=True, unique=True)
    status: str = Field(default="CANDIDATE", index=True)  # CANDIDATE | ACTIVE | REJECTED
    executable: bool = Field(default=False, index=True)
    occurrence_count: int = 0
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    sample_quotes: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
