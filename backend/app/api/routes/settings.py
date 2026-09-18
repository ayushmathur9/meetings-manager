from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.settings import OrgSettings
from app.models.user import User
from app.schemas.settings import OrgSettingsOut, OrgSettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_or_create(db: Session) -> OrgSettings:
    settings = db.query(OrgSettings).first()
    if settings is None:
        settings = OrgSettings(org_name="Sam IT Solutions")
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("", response_model=OrgSettingsOut)
def get_settings(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> OrgSettingsOut:
    return OrgSettingsOut.model_validate(_get_or_create(db))


@router.patch("", response_model=OrgSettingsOut)
def update_settings(
    payload: OrgSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> OrgSettingsOut:
    settings = _get_or_create(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return OrgSettingsOut.model_validate(settings)
