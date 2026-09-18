from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.user import User


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.db.query(User).filter(User.email == email.lower()).first()
        if user is None or not user.active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user
