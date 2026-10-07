from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"

    database_url: str = (
        "postgresql+psycopg://meetings_manager:meetings_manager@localhost:5432/meetings_manager"
    )

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        # Railway (and most managed Postgres providers) hand out plain
        # postgresql:// URLs, but the app is built on the psycopg3 driver.
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    google_maps_api_key: str = ""
    mapbox_access_token: str = ""
    map_provider: str = "mapbox"  # "mapbox" | "google" | "geoapify"

    # Geoapify powers road-network routing, travel-time matrices, stop-order
    # optimization and (when map_provider="geoapify") geocoding. Server-side
    # only — never expose this to the browser.
    geoapify_api_key: str = ""
    geoapify_timeout_seconds: float = 15.0
    geoapify_cache_ttl_seconds: int = 6 * 3600
    # When enabled, Geoapify's Route Planner API proposes a stop order that
    # competes against the in-app optimizer; the app keeps whichever scores
    # better under its own business rules.
    geoapify_route_planner_enabled: bool = True
    route_max_stops: int = 25

    # Background re-verification of unverified company addresses
    # (services/location_sweep.py). 0 disables the sweep.
    location_sweep_interval_minutes: int = 360
    location_sweep_batch_size: int = 200
    location_retry_max_attempts: int = 5
    location_retry_base_hours: int = 6

    backend_cors_origins: str = "http://localhost:3000"

    # Public URL of this API (e.g. https://api.example.com). Needed only for
    # inbound callbacks — the Bigin instant-notification webhook.
    public_api_base_url: str = ""

    # ---------------------------------------------------------------- Bigin CRM
    # Zoho OAuth "self client" credentials (services/bigin.py). Backend only.
    bigin_client_id: str = ""
    bigin_client_secret: str = ""
    bigin_refresh_token: str = ""
    # Zoho data-center accounts host and API domain — they must match the DC
    # the Bigin org lives in (.com, .eu, .in, .com.au, .jp, .ca, .sa, .uk).
    bigin_accounts_url: str = "https://accounts.zoho.com"
    bigin_api_domain: str = "https://www.zohoapis.com"
    bigin_timeout_seconds: float = 30.0
    # Periodic reconciliation (incremental by Modified_Time). 0 disables.
    bigin_sync_interval_minutes: int = 30
    # Addresses changed by a sync are geocoded right after it, up to this many
    # per run; the rest are picked up by the location sweep.
    bigin_geocode_batch_size: int = 200
    # Instant change notifications (Bigin Notification API). Needs
    # PUBLIC_API_BASE_URL; the reconciliation sync still runs either way.
    bigin_webhooks_enabled: bool = True
    # Bigin Companies have no standard status field. If the org tracks one in
    # a custom field, put its API name here (e.g. "Account_Status") and it is
    # synced into crm_status; otherwise crm_status stays empty.
    bigin_account_status_field: str = ""

    # ------------------------------------------------------ Business summaries
    # Research is gathered from public sources (company website) + CRM data;
    # the LLM only synthesizes it (services/business_summary.py).
    summary_provider: str = "anthropic"  # "anthropic" | "none"
    anthropic_api_key: str = ""
    summary_model: str = "claude-opus-5"
    summary_effort: str = "medium"
    research_timeout_seconds: float = 10.0
    research_max_pages: int = 6
    research_stale_days: int = 90
    # Generate a summary automatically the first time a company is opened.
    research_auto_generate: bool = True

    # ------------------------------------------------- Recording/transcription
    # "assemblyai" (default) | "deepgram" | "openai" | "none". Only the
    # selected provider's key is required.
    transcription_provider: str = "assemblyai"
    assemblyai_api_key: str = ""
    deepgram_api_key: str = ""
    openai_api_key: str = ""
    transcription_poll_interval_seconds: int = 20
    # Delete the transcript from AssemblyAI once it is stored here.
    assemblyai_delete_after_complete: bool = True
    recording_max_upload_mb: int = 500

    # Recording storage: "s3" (any S3-compatible bucket — Railway Buckets,
    # AWS S3, Cloudflare R2) or "local" (a directory; development only).
    storage_backend: str = "local"
    storage_local_dir: str = "./storage"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    # Lifetime of presigned recording URLs (browser playback, transcription
    # provider fetch).
    s3_presign_seconds: int = 900
    s3_force_path_style: bool = False

    # ----------------------------------------------------------- Quote Builder
    # External tool linked from the sidebar. Not a secret — served to
    # signed-in users through /app-config.
    quote_builder_url: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
