import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.core.deps import require_admin
from app.db.session import get_db
from app.models.activity import Activity
from app.models.user import User

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
def list_activity(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[dict]:
    query = db.query(Activity).options(joinedload(Activity.user))
    if entity_type:
        query = query.filter(Activity.entity_type == entity_type)
    if entity_id:
        query = query.filter(Activity.entity_id == entity_id)
    activities = query.order_by(Activity.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": a.id,
            "user_name": a.user.name if a.user else "System",
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "action": a.action,
            "metadata": a.metadata_json,
            "timestamp": a.timestamp,
        }
        for a in activities
    ]
