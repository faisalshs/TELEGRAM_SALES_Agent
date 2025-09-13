import os
import json
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    telegram_token: str
    gemini_api_key: str
    public_base_url: str
    port: int
    mode: str  # 'webhook' (Render) or 'polling' (local)

def load_settings() -> Settings:
    # Overlay store if present
    root = Path(__file__).resolve().parent.parent
    store_path = root / 'data' / 'admin_store.json'
    store = {}
    if store_path.exists():
        try:
            store = json.loads(store_path.read_text(encoding='utf-8'))
        except Exception:
            store = {}

    telegram_token = (store.get('TELEGRAM_TOKEN') or os.getenv('TELEGRAM_TOKEN', '')).strip()
    gemini_api_key = (store.get('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY', '')).strip()
    public_base_url = (store.get('PUBLIC_BASE_URL') or os.getenv('PUBLIC_BASE_URL', os.getenv('RENDER_EXTERNAL_URL', ''))).strip()

    port = int(os.getenv('PORT', '10000'))
    mode = (store.get('MODE') or os.getenv('MODE', 'webhook')).strip() or 'webhook'

    if not telegram_token:
        raise RuntimeError('TELEGRAM_TOKEN env var is required')
    if not gemini_api_key:
        raise RuntimeError('GEMINI_API_KEY env var is required')
    if not public_base_url and mode == 'webhook':
        print('[WARN] PUBLIC_BASE_URL/RENDER_EXTERNAL_URL is not set yet. Webhook setup may fail until it is available.')

    return Settings(
        telegram_token=telegram_token,
        gemini_api_key=gemini_api_key,
        public_base_url=public_base_url,
        port=port,
        mode=mode,
    )
