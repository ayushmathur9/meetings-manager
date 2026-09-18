import uuid

from sqlalchemy.orm import Session

from app.models.activity import Activity


class ActivityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def log(
        self,
        *,
        user_id: uuid.UUID | None,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        metadata: dict | None = None,
    ) -> Activity:
        activity = Activity(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            metadata_json=metadata,
        )
        self.db.add(activity)
        self.db.flush()
        return activity
