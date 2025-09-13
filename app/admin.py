
import os
import json
import base64
import secrets
from pathlib import Path
from datetime import datetime
from aiohttp import web
from pypdf import PdfReader

# Paths
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UPLOADS_DIR = ROOT / "product_data" / "uploads"
STORE_PATH = DATA_DIR / "admin_store.json"

DATA_DIR.mkdir(exist_ok=True, parents=True)
UPLOADS_DIR.mkdir(exist_ok=True, parents=True)

# --- Auth helpers (HTTP Basic) ---
ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "")  # must be set in env on Render
def _unauthorized():
    return web.Response(
        text="Unauthorized",
        status=401,
        headers={"WWW-Authenticate": 'Basic realm="Admin Area"'}
    )

def require_basic_auth(handler):
    async def wrapper(request: web.Request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return _unauthorized()
        try:
            userpass = base64.b64decode(auth.split(" ",1)[1]).decode("utf-8")
        except Exception:
            return _unauthorized()
        if ":" not in userpass:
            return _unauthorized()
        user, pwd = userpass.split(":",1)
        if user != ADMIN_USER or pwd != ADMIN_PASS or not ADMIN_PASS:
            return _unauthorized()
        return await handler(request)
    return wrapper

# --- Store helpers ---
DEFAULT_STORE = {
    "bot_name": "Jatri Bookseller Bot",
    "ai_persona": "You are a helpful, friendly sales assistant for our bookstore campaign. Speak concisely and persuasively.",
    "catalog_file": "product_data/jatri_books_info.md",
    # The following can be managed here if ADMIN_ALLOW_SET_SECRETS=true
    "TELEGRAM_TOKEN": "",
    "GEMINI_API_KEY": "",
    "PUBLIC_BASE_URL": "",
    "MODE": "webhook"  # or "polling" for local testing
}

def load_store():
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_STORE.copy()

def save_store(d: dict):
    STORE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")

# --- Simple HTML templates (no external deps) ---
def _html_page(body: str) -> str:
    return f"""<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bot Admin</title>
<style>
body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; color: #e5e7eb; background:#0b1220; }}
h1, h2 {{ color: #fff; }}
input, textarea, select {{ width: 100%; padding: .5rem; margin-top: .25rem; background:#0f172a; color:#e5e7eb; border:1px solid #334155; border-radius:.5rem; }}
button {{ background:#3b82f6; color:white; border:none; padding:.6rem 1rem; border-radius:.5rem; cursor:pointer; }}
button:hover {{ background:#2563eb; }}
.card {{ background:#0f172a; border:1px solid #1f2937; border-radius:1rem; padding:1rem; margin-bottom:1rem; }}
label {{ font-weight:600; }}
small, code {{ color:#9ca3af; }}
a {{ color:#93c5fd; }}
.grid {{ display:grid; gap:1rem; grid-template-columns: 1fr; }}
@media(min-width:900px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} }}
</style>
</head><body>
<h1>Telegram Sales Bot — Admin</h1>
{body}
</body></html>"""

def admin_home_form(store: dict, allow_secrets: bool) -> str:
    secrets_block = ""
    if allow_secrets:
        secrets_block = f"""
        <div class="card">
            <h2>Secrets & API Keys</h2>
            <p><small>These are stored on disk for convenience. Prefer environment variables for security. Protect this panel with strong Basic Auth.</small></p>
            <label>Telegram API Token</label>
            <input type="password" name="TELEGRAM_TOKEN" value="{store.get('TELEGRAM_TOKEN','')}" />
            <label style="margin-top:.5rem">Gemini API Key</label>
            <input type="password" name="GEMINI_API_KEY" value="{store.get('GEMINI_API_KEY','')}" />
            <label style="margin-top:.5rem">PUBLIC_BASE_URL</label>
            <input type="text" name="PUBLIC_BASE_URL" value="{store.get('PUBLIC_BASE_URL','')}" />
        </div>
        """

    return _html_page(f"""
    <div class="grid">
      <div class="card">
        <h2>General Settings</h2>
        <form action="/admin/save" method="post">
          <label>Bot Name</label>
          <input type="text" name="bot_name" value="{store.get('bot_name','')}" />
          <label style="margin-top:.5rem">AI Persona (System Prompt)</label>
          <textarea name="ai_persona" rows="6">{store.get('ai_persona','')}</textarea>
          <label style="margin-top:.5rem">Mode</label>
          <select name="MODE">
            <option value="webhook" {"selected" if store.get("MODE")=="webhook" else ""}>webhook (Render)</option>
            <option value="polling" {"selected" if store.get("MODE")=="polling" else ""}>polling (local)</option>
          </select>
          <p style="margin:.75rem 0 0 0"><small>Current catalog: <code>{store.get('catalog_file')}</code></small></p>
          <button type="submit" style="margin-top:.75rem">Save Settings</button>
        </form>
      </div>
      <div class="card">
        <h2>Upload Knowledge Base</h2>
        <form action="/admin/upload" method="post" enctype="multipart/form-data">
          <label>Upload .md or .pdf</label>
          <input type="file" name="file" accept=".md,.pdf" />
          <button type="submit" style="margin-top:.75rem">Upload & Use</button>
        </form>
        <p style="margin-top:.5rem"><small>Uploaded files are stored in <code>product_data/uploads/</code>. PDFs are converted to Markdown text.</small></p>
      </div>
      {secrets_block}
      <div class="card">
        <h2>Webhook Info</h2>
        <p><small>If using Render, this app runs in webhook mode. Your webhook URL will be <code>{{PUBLIC_BASE_URL or RENDER_EXTERNAL_URL}}/{{TELEGRAM_TOKEN}}</code>. Make sure PUBLIC_BASE_URL (or Render's RENDER_EXTERNAL_URL) is set.</small></p>
        <p><a href="/">Health Check</a></p>
      </div>
    </div>
    """)

# --- Routes ---
@require_basic_auth
async def admin_home(request: web.Request):
    store = load_store()
    allow_secrets = os.getenv("ADMIN_ALLOW_SET_SECRETS", "false").lower() == "true"
    return web.Response(text=admin_home_form(store, allow_secrets), content_type="text/html")

@require_basic_auth
async def admin_save(request: web.Request):
    store = load_store()
    allow_secrets = os.getenv("ADMIN_ALLOW_SET_SECRETS", "false").lower() == "true"
    data = await request.post()
    store["bot_name"] = data.get("bot_name", store.get("bot_name","")).strip()
    store["ai_persona"] = data.get("ai_persona", store.get("ai_persona","")).strip()
    store["MODE"] = data.get("MODE", store.get("MODE","webhook")).strip() or "webhook"

    if allow_secrets:
        for key in ["TELEGRAM_TOKEN", "GEMINI_API_KEY", "PUBLIC_BASE_URL"]:
            if key in data:
                store[key] = data.get(key, "").strip()

    save_store(store)
    return web.Response(text=_html_page("<p>Saved. <a href=\"/admin\">Back</a></p>"), content_type="text/html")

@require_basic_auth
async def admin_upload(request: web.Request):
    reader = await request.multipart()
    part = await reader.next()
    if not part or part.name != "file":
        return web.Response(text="No file field named 'file'", status=400)

    filename = part.filename or "upload"
    raw = await part.read()
    # Save original
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    ext = ".md" if filename.lower().endswith(".md") else ".pdf" if filename.lower().endswith(".pdf") else ""
    if not ext:
        return web.Response(text="Only .md or .pdf supported", status=400)

    save_path = UPLOADS_DIR / f"{ts}-{filename}"
    save_path.write_bytes(raw)

    # If PDF, extract text to a .md alongside
    final_catalog = str(save_path.relative_to(ROOT))
    if ext == ".pdf":
        try:
            text_chunks = []
            with open(save_path, "rb") as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    text_chunks.append(page.extract_text() or "")
            md_text = "\n\n".join(text_chunks).strip()
            md_path = save_path.with_suffix(".md")
            md_path.write_text(md_text, encoding="utf-8")
            final_catalog = str(md_path.relative_to(ROOT))
        except Exception as e:
            # If conversion fails, still register PDF path; handlers should handle reading or show error.
            final_catalog = str(save_path.relative_to(ROOT))

    store = load_store()
    store["catalog_file"] = final_catalog
    save_store(store)

    return web.Response(text=_html_page(f"<p>Uploaded and set catalog to <code>{final_catalog}</code>. <a href=\"/admin\">Back</a></p>"), content_type="text/html")

def mount_admin_routes(app: web.Application):
    app.add_routes([
        web.get("/admin", admin_home),
        web.post("/admin/save", admin_save),
        web.post("/admin/upload", admin_upload),
    ])
    return app
