from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models.user import User
from app.providers.location import get_location_provider

router = APIRouter(prefix="/navigation", tags=["navigation"])


@router.get("/link")
def get_navigation_link(
    dest_lat: float,
    dest_lng: float,
    origin_lat: float | None = None,
    origin_lng: float | None = None,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    provider = get_location_provider()
    origin = (origin_lat, origin_lng) if origin_lat is not None and origin_lng is not None else None
    link = provider.create_navigation_link((dest_lat, dest_lng), origin=origin)
    return {"url": link}
