import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, selectinload

from app.core.deps import require_admin
from app.db.session import get_db
from app.models.company import Company
from app.models.import_job import Import
from app.models.location import Location, VerificationStatus
from app.models.user import User
from app.providers.location import get_location_provider
from app.schemas.import_job import (
    ColumnMappingRequest,
    ConfirmImportRequest,
    ConfirmImportResult,
    ImportLocationSummary,
    ImportOut,
    ImportPreview,
    ValidationSummary,
)
from app.services.import_service import ImportService, parse_spreadsheet, suggest_column_mapping

router = APIRouter(prefix="/imports", tags=["imports"])


def _get_import_or_404(db: Session, import_id: uuid.UUID) -> Import:
    import_job = (
        db.query(Import)
        .options(selectinload(Import.rows))
        .filter(Import.id == import_id)
        .first()
    )
    if import_job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    return import_job


@router.get("", response_model=list[ImportOut])
def list_imports(
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> list[ImportOut]:
    imports = db.query(Import).order_by(Import.created_at.desc()).all()
    return [ImportOut.model_validate(i) for i in imports]


@router.post("", response_model=ImportPreview, status_code=status.HTTP_201_CREATED)
async def upload_import(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ImportPreview:
    content = await file.read()
    try:
        df = parse_spreadsheet(file.filename or "upload.csv", content)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    if df.empty:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file has no data rows")

    service = ImportService(db, get_location_provider())
    import_job = service.create_import(
        filename=file.filename or "upload.csv",
        imported_by_id=current_user.id,
        row_count=len(df),
    )
    service.store_raw_rows(import_job, df)
    db.commit()

    columns = list(df.columns)
    return ImportPreview(
        import_id=import_job.id,
        columns=columns,
        suggested_mapping=suggest_column_mapping(columns),
        sample_rows=df.head(10).to_dict(orient="records"),
        row_count=len(df),
    )


@router.post("/{import_id}/mapping", response_model=ValidationSummary)
def apply_mapping(
    import_id: uuid.UUID,
    payload: ColumnMappingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ValidationSummary:
    import_job = _get_import_or_404(db, import_id)
    service = ImportService(db, get_location_provider())
    service.apply_mapping_and_validate(import_job, payload.mapping)
    service.check_existing_company_duplicates(import_job)
    db.commit()
    db.refresh(import_job)
    return ValidationSummary(
        import_job=ImportOut.model_validate(import_job),
        rows=[r for r in import_job.rows],
    )


@router.get("/{import_id}", response_model=ValidationSummary)
def get_import(
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ValidationSummary:
    import_job = _get_import_or_404(db, import_id)
    return ValidationSummary(
        import_job=ImportOut.model_validate(import_job),
        rows=[r for r in import_job.rows],
    )


@router.post("/{import_id}/confirm", response_model=ConfirmImportResult)
def confirm_import(
    import_id: uuid.UUID,
    payload: ConfirmImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ConfirmImportResult:
    import_job = _get_import_or_404(db, import_id)
    service = ImportService(db, get_location_provider())
    service.confirm_import(import_job, verify_locations=payload.verify_locations)
    db.commit()
    db.refresh(import_job)

    created_company_ids = [r.created_company_id for r in import_job.rows if r.created_company_id]
    summary = ImportLocationSummary()
    if created_company_ids:
        rows = (
            db.query(Location.verification_status)
            .join(Company, Company.id == Location.company_id)
            .filter(Company.id.in_(created_company_ids), Location.is_primary.is_(True))
            .all()
        )
        for (status,) in rows:
            if status == VerificationStatus.VERIFIED:
                summary.verified += 1
            elif status == VerificationStatus.NEEDS_REVIEW:
                summary.needs_review += 1
            elif status == VerificationStatus.FAILED:
                summary.failed += 1
            else:
                summary.unverified += 1
        # A company with no Location row at all (e.g. no address columns
        # were mapped) counts as missing location data too.
        summary.unverified += len(created_company_ids) - len(rows)

    return ConfirmImportResult(import_job=ImportOut.model_validate(import_job), locations=summary)


@router.get("/{import_id}/error-report")
def download_error_report(
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[dict]:
    import_job = _get_import_or_404(db, import_id)
    return [
        {
            "row_number": r.row_number,
            "status": r.status.value,
            "reason": r.error_reason,
            "raw_data": r.raw_data,
        }
        for r in import_job.rows
        if r.status.value in ("error", "duplicate")
    ]
