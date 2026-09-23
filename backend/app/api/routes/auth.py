from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, TokenResponse, UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    auth_service = AuthService(db)
    user = auth_service.authenticate(payload.email, payload.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    settings = get_settings()
    token = create_access_token(str(user.id), extra_claims={"role": user.role.value})
    # Frontend and backend are deployed on different subdomains in production,
    # so the cookie must be SameSite=None to be sent on cross-site requests;
    # SameSite=None requires Secure, which only makes sense outside local dev.
    is_cross_site = settings.environment != "development"
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="none" if is_cross_site else "lax",
        secure=is_cross_site,
        max_age=settings.access_token_expire_minutes * 60,
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("access_token")
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
