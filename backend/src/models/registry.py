from typing import Literal, Optional

from pydantic import BaseModel, Field


class RegistryBuildRequest(BaseModel):
    district_code: Optional[int] = Field(
        default=None,
        description="Optional district filter for pilot builds. Omit to target all districts.",
    )
    include_schema: bool = Field(
        default=True,
        description="Create or verify the registry tables and view before loading data.",
    )
    include_person_detail: bool = Field(
        default=True,
        description="Populate the person detail registry table.",
    )
    include_person_scheme_enrollment: bool = Field(
        default=True,
        description="Populate the person-scheme enrollment registry table.",
    )
    include_validation_queries: bool = Field(
        default=False,
        description="Include generated validation SQL in the response payload.",
    )


class RegistrySqlPreviewRequest(BaseModel):
    district_code: Optional[int] = Field(
        default=None,
        description="Optional district filter for pilot SQL previews.",
    )
    include_schema: bool = True
    include_person_detail: bool = True
    include_person_scheme_enrollment: bool = True


class RegistryStatementResult(BaseModel):
    key: str
    kind: Literal["ddl", "dml", "view", "validation"]
    statement: str


class RegistryExecutionResult(BaseModel):
    key: str
    kind: Literal["ddl", "dml", "view"]
    success: bool
    rowcount: Optional[int] = None

