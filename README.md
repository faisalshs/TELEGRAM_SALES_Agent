# Jatri Bookseller Bot (Telegram + Gemini)

A production-ready Telegram bot for a small bookstore campaign. It speaks **English, Bengali, Hindi, and Arabic**, recommends books from a curated list, and keeps responses in the user's detected language. Built with **python-telegram-bot (webhooks)** and **Google Gemini**; deployable on **Render (free tier)**.

## Features
- Webhook-based Telegram bot (no polling; works on Render free web service).
- Multi-language detection (en/bn/hi/ar) with strict language output.
- Campaign-aware recommendations loaded from a markdown file.
- Simple per-user conversation memory.
- Health check endpoint (`GET /`) for uptime checks.

> Voice TTS/transcription is **disabled** in this minimal free setup. See "Enable voice later" below if you want it.

---

## Quick Start (Local)
1. **Python 3.11+** recommended.
2. Create a Telegram bot with [@BotFather](https://t.me/BotFather) and get the **bot token**.
3. Get a **Google Gemini API key** from https://aistudio.google.com/app/apikey
4. Create and fill a `.env` (or set environment variables):
   ```env
   TELEGRAM_TOKEN=123456:ABC...
   GEMINI_API_KEY=your_gemini_key
   ```
5. Install dependencies and run locally with a public tunnel (optional if you just want local testing):
   ```bash
   pip install -r requirements.txt
   python -m app.main
   ```
   The app starts a webhook server on `PORT` (defaults to 10000). For Telegram to reach your bot, expose it (e.g. with `ngrok http 10000`) and set `RENDER_EXTERNAL_URL` to the public URL (or export `PUBLIC_BASE_URL`).

---

## Deploy on Render (Free)
1. Push this repo to **GitHub**.
2. Create a **new Web Service** on Render:
   - Select your GitHub repo.
   - Choose **Free** plan.
   - It will read `render.yaml` and auto-configure.
3. In Render, add two **Environment Variables**:
   - `TELEGRAM_TOKEN` — your bot token
   - `GEMINI_API_KEY` — your Gemini key
4. Deploy. Render sets `RENDER_EXTERNAL_URL` automatically (e.g., `https://your-service.onrender.com`).
5. On first boot, the app sets the Telegram webhook to:  
   `https://<RENDER_EXTERNAL_URL>/<TELEGRAM_TOKEN>`

**That’s all.** Your bot is live 🎉

---

## Configuration
- `product_data/jatri_books_info.md`: your campaign books and copy.
- `app/config.py`: environment variables.
- `app/bot.py`: handlers, prompt, and model.
- `app/main.py`: webhook server bootstrap.

> To change the system prompt or persona, edit `AGENT_PERSONA_PROMPT` in `app/bot.py`.

---

## Health Check
- `GET /` returns `"ok"` JSON; useful for uptime monitoring.

---

## Enable Voice Later (Optional)
Render free web services don't include **ffmpeg** out of the box (needed to convert Telegram OGG voice to supported formats for Gemini). If you need voice:
- Switch to a **Docker** service on Render and install `ffmpeg` in the image, or
- Vendor a static ffmpeg binary (large) and configure `pydub` to use it, or
- Use a managed service that supports ffmpeg on free tier.

Then you can port the voice logic from your Colab code into `handle_voice_message` similarly to the text path.

---

## Security Notes
- Never commit real tokens/keys.
- Consider adding a `SECRET_PATH` and using `/<SECRET_PATH>/<TOKEN>` as the webhook URL for extra obscurity.
- Limit logs; avoid logging PII or secrets.

---

## License
MIT


---

## Voice Support (Free Tier Friendly)
- **Incoming**: Telegram voice notes (OGG/Opus) are downloaded and uploaded directly to Gemini for transcription (no ffmpeg needed).
- **Outgoing**: Bot replies with **MP3 audio** generated via `gTTS` and sent with `send_audio` (Telegram accepts MP3 as audio files).  
  > Note: This shows as an audio file, not a voice-note bubble, because converting MP3→OGG/Opus would require ffmpeg.

### What works
- Users can send voice notes; bot transcribes + understands them.
- Bot replies with a spoken MP3 of its answer.

### What’s omitted
- No server-side audio transcoding (keeps it free and simple).
- If you prefer voice-bubble style replies, add ffmpeg in a Docker image then switch to `send_voice(oga_file)`.


---

## Deploy on Render (Docker, Voice-Notes Enabled)
This project includes a `Dockerfile` that installs **ffmpeg**, so we can convert TTS MP3 → OGG/Opus and reply with real **voice notes** via `send_voice`.

### Steps
1. Push to GitHub.
2. On Render → **New** → **Web Service** → choose your repo.
3. Render reads `render.yaml` (env: docker) and builds the image.
4. Set env vars in Render:
   - `TELEGRAM_TOKEN`
   - `GEMINI_API_KEY`
5. Deploy. Webhook auto-configures to: `https://<RENDER_EXTERNAL_URL>/<TELEGRAM_TOKEN>`

### Notes
- ffmpeg is installed in the container (see `Dockerfile`), so no extra setup.
- If you ever face large audio or long replies, Telegram limits may apply.
- Health route is `/` returning `{"status":"ok"}`.
