import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.location import LocationSource, VerificationStatus


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    latitude: float | None
    longitude: float | None
    formatted_address: str | None
    source: LocationSource
    provider: str | None
    provider_place_id: str | None
    confidence: str | None
    verification_status: VerificationStatus
    verification_notes: str | None
    verified_at: datetime | None


class LocationCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    formatted_address: str
    latitude: float
    longitude: float
    place_id: str | None
    name: str | None
    confidence: str
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


class LocationCandidatesOut(BaseModel):
    candidates: list[LocationCandidateOut]


class LocationResolveRequest(BaseModel):
    candidate: LocationCandidateOut
