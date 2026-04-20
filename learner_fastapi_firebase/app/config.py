from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_host: str
    app_port: int
    app_secret_key: str
    app_cors_origins: list[str]

    firebase_project_id: str
    firebase_web_api_key: str
    firebase_auth_domain: str
    firebase_credentials_path: str
    firebase_service_account_json: str
    firebase_service_account_json_b64: str
    firebase_use_memory: bool

    resend_api_key: str
    resend_from: str
    resend_base_url: str
    resend_timeout_seconds: float

    market_data_cache_seconds: int
    nvidia_api_key: str
    nvidia_base_url: str
    nvidia_model: str
    ai_request_timeout_seconds: float
    ai_cache_seconds: int


def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=int(os.getenv("APP_PORT", "8010")),
        app_secret_key=os.getenv("APP_SECRET_KEY", "change_me"),
        app_cors_origins=_env_list(
            "APP_CORS_ORIGINS",
            "http://127.0.0.1:8010,http://localhost:8010",
        ),
        firebase_project_id=os.getenv("FIREBASE_PROJECT_ID", "").strip(),
        firebase_web_api_key=os.getenv("FIREBASE_WEB_API_KEY", "").strip(),
        firebase_auth_domain=os.getenv("FIREBASE_AUTH_DOMAIN", "").strip(),
        firebase_credentials_path=os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip(),
        firebase_service_account_json=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip(),
        firebase_service_account_json_b64=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON_B64", "").strip(),
        firebase_use_memory=_env_bool("FIREBASE_USE_MEMORY", False),
        resend_api_key=os.getenv("RESEND_API_KEY", "").strip(),
        resend_from=os.getenv("RESEND_FROM", "").strip(),
        resend_base_url=os.getenv("RESEND_BASE_URL", "https://api.resend.com").strip().rstrip("/"),
        resend_timeout_seconds=float(os.getenv("RESEND_TIMEOUT_SECONDS", "12")),
        market_data_cache_seconds=int(os.getenv("MARKET_DATA_CACHE_SECONDS", "900")),
        nvidia_api_key=os.getenv("NVIDIA_API_KEY", "").strip(),
        nvidia_base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip(),
        nvidia_model=os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v3.2").strip(),
        ai_request_timeout_seconds=float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "8")),
        ai_cache_seconds=int(os.getenv("AI_CACHE_SECONDS", "1200")),
    )
