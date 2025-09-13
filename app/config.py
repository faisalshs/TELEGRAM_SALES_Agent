import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    telegram_token: str
    gemini_api_key: str
    public_base_url: str
    port: int

def load_settings() -> Settings:
    telegram_token = os.getenv("TELEGRAM_TOKEN", "").strip()
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

    # On Render, this is set automatically. Else, users can set PUBLIC_BASE_URL.
    public_base_url = os.getenv("RENDER_EXTERNAL_URL", os.getenv("PUBLIC_BASE_URL", "")).rstrip("/")

    port = int(os.getenv("PORT", "10000"))

    if not telegram_token:
        raise RuntimeError("TELEGRAM_TOKEN env var is required")
    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY env var is required")
    if not public_base_url:
        # Not fatal (we can still boot and try to set later), but recommended
        print("[WARN] PUBLIC_BASE_URL/RENDER_EXTERNAL_URL is not set yet. Webhook setup may fail until it is available.")

    return Settings(
        telegram_token=telegram_token,
        gemini_api_key=gemini_api_key,
        public_base_url=public_base_url,
        port=port,
    )
