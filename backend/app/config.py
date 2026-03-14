"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Unsiloed.ai
    unsiloed_api_key: str = ""

    # Claude Agent SDK
    claude_model: str = "claude-sonnet-4-20250514"
    session_idle_timeout_minutes: int = 30
    session_cleanup_interval_minutes: int = 5
    sessions_dir: str = "data/sessions"

    # Admin credentials
    admin_username: str = "admin"
    admin_password: str = "changeme"

    # Database
    database_url: str = "sqlite+aiosqlite:///data/wrenchai.db"

    # ChromaDB
    chromadb_path: str = "data/chromadb"

    # File paths
    upload_dir: str = "data/uploads"
    processed_dir: str = "data/processed"

    # NiceGUI
    storage_secret: str = "wrenchai-secret"

    # Firebase
    firebase_credentials_path: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
