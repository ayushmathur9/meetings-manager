from fastapi import APIRouter, Depends, Query

from app.api.error_handling import translate_provider_errors
from app.core.deps import get_current_user
from app.models.user import User
from app.providers.location import get_location_provider
from app.schemas.location import LocationCandidatesOut

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/search", response_model=LocationCandidatesOut)
def search_locations(
    q: str = Query(min_length=2),
    current_user: User = Depends(get_current_user),
) -> LocationCandidatesOut:
    """Free-text place/address search — used anywhere a person needs to pick
    a real-world location (a start/end point, a saved location) instead of
    typing coordinates by hand. Tries a business/place name search first
    (so "Sam IT Solutions Office" resolves directly) and falls back to plain
    address geocoding when that finds nothing.
    """
    provider = get_location_provider()
    with translate_provider_errors():
        result = provider.search_business(q)
        if not result.candidates:
            result = provider.geocode_address(q)
    return LocationCandidatesOut(candidates=result.candidates)
