"""Admin "CRM Sync" screen + the Bigin instant-notification receiver."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import require_admin
from app.db.session import get_db
from app.models.company import Company
from app.models.contact import Contact
from app.models.crm_sync import BiginSyncRun, SyncTrigger
from app.models.location import Location, VerificationStatus
from app.models.user import User
from app.schemas.crm_sync import (
    ConnectionStatus,
    CrmSyncStatus,
    SyncCounts,
    SyncRunDetail,
    SyncRunOut,
    SyncRunRequest,
    WebhookStatus,
)
from app.services import background
from app.services.bigin import get_bigin_client
from app.services.bigin_sync import BiginSyncService, get_state, latest_running_run, run_sync_job

logger = logging.getLogger("app.bigin_sync")

router = APIRouter(prefix="/crm-sync", tags=["crm-sync"])
webhook_router = APIRouter(prefix="/integrations/bigin", tags=["crm-sync"])

CONNECTION_RECHECK = timedelta(minutes=15)


def _run_out(run: BiginSyncRun, cls=SyncRunOut):
    out = cls.model_validate(run)
    out.triggered_by_name = run.triggered_by.name if run.triggered_by else None
    return out


def _counts(db: Session) -> SyncCounts:
    synced = (Company.bigin_account_id.isnot(None), Company.crm_deleted_at.is_(None))
    primary = (Location.company_id == Company.id) & Location.is_primary.is_(True)
    location_rows = (
        db.query(Location.verification_status, Location.latitude.isnot(None), func.count())
        .join(Company, primary)
        .filter(*synced)
        .group_by(Location.verification_status, Location.latitude.isnot(None))
        .all()
    )
    locations = sum(n for vs, has_coords, n in location_rows if vs == VerificationStatus.VERIFIED and has_coords)
    needs_review = sum(
        n for vs, _, n in location_rows if vs in (VerificationStatus.NEEDS_REVIEW, VerificationStatus.FAILED)
    )
    return SyncCounts(
        companies=db.query(func.count(Company.id)).filter(*synced).scalar() or 0,
        contacts=db.query(func.count(Contact.id))
        .filter(Contact.bigin_contact_id.isnot(None), Contact.crm_deleted_at.is_(None))
        .scalar()
        or 0,
        locations=locations,
        needs_review=needs_review,
        archived=db.query(func.count(Company.id)).filter(Company.crm_deleted_at.isnot(None)).scalar() or 0,
    )


@router.get("/status", response_model=CrmSyncStatus)
def get_status(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> CrmSyncStatus:
    settings = get_settings()
    client = get_bigin_client()
    state = get_state(db)
    now = datetime.now(timezone.utc)

    # "Connected" is only ever reported from a real API call, re-checked
    # every 15 minutes at most (a successful sync also counts).
    if client.is_configured and (
        state.connection_checked_at is None or now - state.connection_checked_at > CONNECTION_RECHECK
    ):
        BiginSyncService(db, client).check_connection()
    running = latest_running_run(db)
    db.commit()

    interval = settings.bigin_sync_interval_minutes
    next_sync = None
    if client.is_configured and interval > 0:
        base = state.last_attempt_at or now
        next_sync = max(base + timedelta(minutes=interval), now)

    recent = db.query(BiginSyncRun).order_by(BiginSyncRun.started_at.desc()).limit(5).all()
    webhooks_enabled = settings.bigin_webhooks_enabled and bool(settings.public_api_base_url)
    return CrmSyncStatus(
        connection=ConnectionStatus(
            configured=client.is_configured,
            ok=client.is_configured and state.connection_ok,
            checked_at=state.connection_checked_at,
            error=None if not client.is_configured else state.connection_error,
        ),
        last_success_at=state.last_success_at,
        last_attempt_at=state.last_attempt_at,
        last_full_sync_at=state.last_full_sync_at,
        last_error=state.last_error,
        next_sync_at=next_sync,
        interval_minutes=interval,
        running=_run_out(running) if running else None,
        counts=_counts(db),
        webhooks=WebhookStatus(
            enabled=webhooks_enabled,
            active=bool(
                webhooks_enabled and state.channel_id and state.channel_expires_at and state.channel_expires_at > now
            ),
            expires_at=state.channel_expires_at,
            last_notification_at=state.last_notification_at,
            error=state.channel_error,
        ),
        recent_runs=[_run_out(r) for r in recent],
    )


@router.post("/run", response_model=SyncRunOut, status_code=status.HTTP_202_ACCEPTED)
def start_sync(
    payload: SyncRunRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SyncRunOut:
    if not get_bigin_client().is_configured:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {"code": "bigin_not_configured", "message": "Bigin is not connected. Set BIGIN_CLIENT_ID, "
             "BIGIN_CLIENT_SECRET and BIGIN_REFRESH_TOKEN on the backend."},
        )
    if latest_running_run(db) is not None:
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "sync_running", "message": "A sync is already running."})
    run = BiginSyncService(db).start_run(
        trigger=SyncTrigger.MANUAL, full=bool(payload and payload.full), user_id=current_user.id
    )
    db.commit()
    db.refresh(run)
    background.submit(run_sync_job, run.id)
    return _run_out(run)


@router.get("/runs", response_model=list[SyncRunOut])
def list_runs(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SyncRunOut]:
    runs = db.query(BiginSyncRun).order_by(BiginSyncRun.started_at.desc()).limit(limit).all()
    return [_run_out(r) for r in runs]


@router.get("/runs/{run_id}", response_model=SyncRunDetail)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> SyncRunDetail:
    run = db.get(BiginSyncRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sync run not found")
    return _run_out(run, SyncRunDetail)


@webhook_router.post("/notifications", include_in_schema=False)
async def bigin_notification(request: Request, db: Session = Depends(get_db)) -> dict:
    """Receiver for Bigin's Notification API. Authenticated by the channel
    id + secret token we registered (Bigin echoes both in every payload).
    Payloads carry record ids only; we mark deletions directly and run an
    incremental sync for everything else."""
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload")
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload")

    service = BiginSyncService(db)
    if not service.verify_notification(payload.get("channel_id"), payload.get("token")):
        logger.warning("Rejected Bigin notification with an unknown channel/token")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown channel")

    state = get_state(db)
    state.last_notification_at = datetime.now(timezone.utc)
    module = payload.get("module")
    ids = [str(i) for i in payload.get("ids") or []]
    if payload.get("operation") == "delete" and module in ("Accounts", "Contacts"):
        service.mark_deleted(module, ids)
        db.commit()
    else:
        db.commit()
        background.submit(run_sync_job, trigger=SyncTrigger.WEBHOOK)
    return {"status": "ok"}
