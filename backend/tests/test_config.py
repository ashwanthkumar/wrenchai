"""Tests for app.config — Settings defaults and loading."""

from app.config import Settings


def test_settings_defaults():
    """Settings() loads with expected default values."""
    s = Settings()
    assert s.unsiloed_api_key == ""
    assert s.claude_model == "claude-sonnet-4-20250514"
    assert s.session_idle_timeout_minutes == 30
    assert s.session_cleanup_interval_minutes == 5
    assert s.sessions_dir == "data/sessions"
    assert s.admin_username == "admin"
    assert s.admin_password == "changeme"
    assert s.chromadb_path == "data/chromadb"
    assert s.upload_dir == "data/uploads"
    assert s.processed_dir == "data/processed"
    assert s.storage_secret == "wrenchai-secret"
    assert s.firebase_credentials_path == ""


def test_settings_database_url_default():
    """Default database_url contains sqlite+aiosqlite."""
    s = Settings()
    assert "sqlite+aiosqlite" in s.database_url
