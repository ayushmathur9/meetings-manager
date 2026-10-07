"""Zoho Bigin REST API v2 client — the ONLY module that talks to Bigin.

Auth is a Zoho OAuth "self client": a long-lived refresh token (generated
once in the Zoho API console with the scopes below) is exchanged for a
one-hour access token, cached in memory and refreshed on expiry or on a 401.

Required scopes when generating the refresh token:
    ZohoBigin.modules.accounts.READ, ZohoBigin.modules.contacts.READ
    ZohoBigin.notifications.ALL   (instant change notifications; optional)

Data centers: BIGIN_ACCOUNTS_URL / BIGIN_API_DOMAIN must both point at the
org's DC (e.g. accounts.zoho.eu + www.zohoapis.eu).

Docs: https://www.bigin.com/developer/docs/apis/v2/
  get-records.html, get-deleted-records.html, refresh.html,
  notifications/enable.html, status-codes.html

Credentials are never logged, returned to callers or put in exception text.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings

logger = logging.getLogger("app.bigin")

PER_PAGE = 200  # Bigin maximum
_PLACEHOLDERS = {"", "your_bigin_client_id", "your_bigin_client_secret", "your_bigin_refresh_token"}


class BiginError(Exception):
    """A Bigin call failed. ``user_message`` is safe to show to admins."""

    def __init__(self, code: str, user_message: str, *, status: int | None = None) -> None:
        super().__init__(f"{code}: {user_message}")
        self.code = code
        self.user_message = user_message
        self.status = status


def parse_bigin_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class BiginClient:
    def __init__(self, http: httpx.Client | None = None) -> None:
        settings = get_settings()
        self.client_id = settings.bigin_client_id.strip()
        self.client_secret = settings.bigin_client_secret.strip()
        self.refresh_token = settings.bigin_refresh_token.strip()
        self.accounts_url = settings.bigin_accounts_url.rstrip("/")
        self.api_domain = settings.bigin_api_domain.rstrip("/")
        self._http = http or httpx.Client(timeout=settings.bigin_timeout_seconds)
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._lock = threading.Lock()

    @property
    def is_configured(self) -> bool:
        return all(v not in _PLACEHOLDERS for v in (self.client_id, self.client_secret, self.refresh_token))

    # ------------------------------------------------------------------ auth
    def _access_token(self, *, force: bool = False) -> str:
        if not self.is_configured:
            raise BiginError("not_configured", "Bigin credentials are not configured on the server.")
        with self._lock:
            if not force and self._token and time.monotonic() < self._token_expires_at - 60:
                return self._token
            try:
                res = self._http.post(
                    f"{self.accounts_url}/oauth/v2/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": self.refresh_token,
                    },
                )
            except httpx.HTTPError as exc:
                raise BiginError("network_error", f"Could not reach Zoho accounts ({type(exc).__name__}).") from exc
            body = _json_or_empty(res)
            # Zoho answers a bad refresh token with HTTP 200 + {"error": ...}.
            if res.status_code != 200 or "access_token" not in body:
                error = body.get("error") or f"HTTP {res.status_code}"
                logger.warning("Bigin token refresh failed: %s", error)
                raise BiginError(
                    "auth_failed",
                    f"Zoho rejected the Bigin credentials ({error}). Check the client id/secret, "
                    "refresh token and data-center URLs.",
                    status=res.status_code,
                )
            self._token = body["access_token"]
            self._token_expires_at = time.monotonic() + float(body.get("expires_in", 3600))
            return self._token

    # --------------------------------------------------------------- requests
    def _request(self, method: str, path: str, *, params=None, json=None) -> dict | None:
        url = f"{self.api_domain}/bigin/v2/{path.lstrip('/')}"
        for attempt in (1, 2):
            token = self._access_token(force=attempt == 2)
            started = time.monotonic()
            try:
                res = self._http.request(
                    method, url, params=params, json=json, headers={"Authorization": f"Zoho-oauthtoken {token}"}
                )
            except httpx.HTTPError as exc:
                raise BiginError("network_error", f"Could not reach Bigin ({type(exc).__name__}).") from exc
            logger.info("bigin %s /%s -> %s (%.0f ms)", method, path, res.status_code, (time.monotonic() - started) * 1000)
            if res.status_code == 401 and attempt == 1:
                continue  # access token expired/revoked early — refresh once
            break

        if res.status_code in (204, 304):
            return None
        body = _json_or_empty(res)
        if res.status_code < 400:
            return body
        code = str(body.get("code") or f"http_{res.status_code}")
        message = str(body.get("message") or res.reason_phrase)
        logger.warning("Bigin error on %s /%s: %s %s", method, path, code, message)
        if res.status_code == 401:
            raise BiginError("auth_failed", f"Bigin rejected the access token ({code}).", status=401)
        if res.status_code == 429:
            raise BiginError("rate_limited", "Bigin API limit reached — the next sync will retry.", status=429)
        if code in ("OAUTH_SCOPE_MISMATCH", "NO_PERMISSION"):
            raise BiginError("permission_denied", f"The Bigin token lacks a required scope ({code}).", status=res.status_code)
        raise BiginError("api_error", f"Bigin returned {code}: {message}", status=res.status_code)

    # ---------------------------------------------------------------- records
    def iter_records(
        self, module: str, fields: list[str], *, modified_after: datetime | None = None
    ) -> Iterator[dict]:
        """All records of a module, or — with ``modified_after`` — those
        modified after it. Incremental mode reads newest-first and stops at
        the watermark, so it costs one call per 200 changed records."""
        params: dict = {"fields": ",".join(fields), "per_page": PER_PAGE}
        if modified_after is not None:
            params.update(sort_by="Modified_Time", sort_order="desc")
        page = 1
        page_token: str | None = None
        while True:
            query = dict(params)
            if page_token:
                query["page_token"] = page_token
            else:
                query["page"] = page
            body = self._request("GET", module, params=query)
            if not body:
                return
            for record in body.get("data") or []:
                if modified_after is not None:
                    modified = parse_bigin_datetime(record.get("Modified_Time"))
                    if modified is not None and modified <= modified_after:
                        return
                yield record
            info = body.get("info") or {}
            if not info.get("more_records"):
                return
            # page/per_page reach 2,000 records; beyond that Bigin requires
            # the page token.
            page_token = info.get("next_page_token") or None
            page += 1

    def iter_deleted(self, module: str, *, max_pages: int = 10) -> Iterator[dict]:
        """Recently deleted records: ``{id, deleted_time, type, ...}``."""
        for page in range(1, max_pages + 1):
            body = self._request("GET", f"{module}/deleted", params={"type": "all", "page": page, "per_page": PER_PAGE})
            if not body:
                return
            yield from body.get("data") or []
            if not (body.get("info") or {}).get("more_records"):
                return

    def check_connection(self) -> None:
        """Raises BiginError unless a real authenticated API call succeeds."""
        self._request("GET", "Accounts", params={"fields": "Account_Name", "per_page": 1})

    # ---------------------------------------------------------- notifications
    def enable_notifications(
        self, *, channel_id: str, token: str, notify_url: str, expires_at: datetime, events: list[str]
    ) -> None:
        body = self._request(
            "POST",
            "actions/watch",
            json={
                "watch": [
                    {
                        "channel_id": channel_id,
                        "events": events,
                        "notify_url": notify_url,
                        "token": token,
                        "channel_expiry": expires_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
                    }
                ]
            },
        )
        result = ((body or {}).get("watch") or [{}])[0]
        if str(result.get("status", "success")).lower() != "success":
            raise BiginError("watch_failed", f"Bigin refused the notification channel: {result.get('message') or result.get('code')}")

    def disable_notifications(self, channel_id: str) -> None:
        self._request("DELETE", "actions/watch", params={"channel_ids": channel_id})


def _json_or_empty(res: httpx.Response) -> dict:
    try:
        data = res.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


_client: BiginClient | None = None


def get_bigin_client() -> BiginClient:
    global _client
    if _client is None:
        _client = BiginClient()
    return _client


def set_bigin_client(client) -> None:
    """Test hook."""
    global _client
    _client = client
