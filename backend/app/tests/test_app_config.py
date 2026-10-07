"""Quote Builder link: served from backend config, never hard-coded."""

from app.core.config import get_settings


def test_quote_builder_url_configured(sales_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "quote_builder_url", "https://quotes.example.com/new")
    assert sales_client.get("/app-config").json() == {"quote_builder_url": "https://quotes.example.com/new"}


def test_quote_builder_url_missing_or_unsafe(admin_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "quote_builder_url", "")
    assert admin_client.get("/app-config").json()["quote_builder_url"] is None
    monkeypatch.setattr(get_settings(), "quote_builder_url", "javascript:alert(1)")
    assert admin_client.get("/app-config").json()["quote_builder_url"] is None


def test_app_config_requires_auth(anon_client):
    assert anon_client.get("/app-config").status_code == 401
