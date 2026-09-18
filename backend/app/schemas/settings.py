from pydantic import BaseModel, ConfigDict


class OrgSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    org_name: str
    logo_url: str | None
    default_meeting_duration_minutes: int
    default_travel_buffer_minutes: int
    working_hours_start: str
    working_hours_end: str
    default_start_location: dict | None
    saved_locations: list | None


class OrgSettingsUpdate(BaseModel):
    org_name: str | None = None
    default_meeting_duration_minutes: int | None = None
    default_travel_buffer_minutes: int | None = None
    working_hours_start: str | None = None
    working_hours_end: str | None = None
    default_start_location: dict | None = None
    saved_locations: list | None = None
