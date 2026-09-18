import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.models.import_job import ImportRowStatus, ImportStatus


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    column_mapping: dict | None
    row_count: int
    success_count: int
    error_count: int
    duplicate_count: int
    status: ImportStatus
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ImportLocationSummary(BaseModel):
    """Location-verification breakdown for the companies a completed import
    created — lets the admin immediately see whether the imported companies
    can actually be mapped/routed, not just whether the spreadsheet rows parsed."""

    verified: int = 0
    needs_review: int = 0
    unverified: int = 0
    failed: int = 0

    @computed_field
    @property
    def total(self) -> int:
        return self.verified + self.needs_review + self.unverified + self.failed


class ImportPreview(BaseModel):
    import_id: uuid.UUID
    columns: list[str]
    suggested_mapping: dict[str, str | None]
    sample_rows: list[dict]
    row_count: int


class ColumnMappingRequest(BaseModel):
    mapping: dict[str, str]


class ImportRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    row_number: int
    raw_data: dict
    mapped_data: dict | None
    status: ImportRowStatus
    error_reason: str | None
    duplicate_of_company_id: uuid.UUID | None
    created_company_id: uuid.UUID | None


class ValidationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_job: ImportOut
    rows: list[ImportRowOut]


class ConfirmImportRequest(BaseModel):
    verify_locations: bool = True


class ConfirmImportResult(BaseModel):
    import_job: ImportOut
    locations: ImportLocationSummary
