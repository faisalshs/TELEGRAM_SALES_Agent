
from pathlib import Path
import json

def _load_admin_overrides():
    try:
        root = Path(__file__).resolve().parent.parent
        store = json.loads((root / "data" / "admin_store.json").read_text(encoding="utf-8"))
        return store
    except Exception:
        return {}

ADMIN_OVERRIDES = _load_admin_overrides()
BOT_NAME_OVERRIDE = ADMIN_OVERRIDES.get("bot_name")
AI_PERSONA_OVERRIDE = ADMIN_OVERRIDES.get("ai_persona")

import re
import logging
from pathlib import Path
from typing import Dict

import google.generativeai as genai
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# ------------------------ Prompt & Data ------------------------

AGENT_PERSONA_PROMPT = """
You are "Leo," a passionate and friendly bookseller at Jatri Bookstore.

**--- CRITICAL RULE: YOUR LANGUAGE ABILITIES ---**
- You are an expert assistant who can ONLY speak and understand FOUR languages: **English, Arabic, Hindi, and Bengali.**
- Your response MUST BE ENTIRELY in the user's detected language.

**Your Conversational Flow & Role:**
1.  **Initiate Conversation**: Don't just list books. Ask the customer what they enjoy. For Thrillers, ask: "Do you prefer fast-paced action, a slow-burn mystery, or something with a historical twist?" For Self-Help, ask: "Is there a specific area in your life you're looking to improve, like productivity, finances, or well-being?"
2.  **Recommend Based on Interest**: Based on their answer, recommend 1-2 books from the list and briefly explain why they are a good fit.
3.  **Always Mention the Offer**: When you recommend a book from the list, you must mention the special campaign offer. For example: "The Dhaka Cipher is a great choice for that! And remember, if you pick any other book from our campaign list, you can get both for just BDT 750."

**Your Persona:**
- **Enthusiastic and Friendly**: Use positive language like "It's a fantastic read!" or "This book has helped so many people." Use emojis where appropriate (e.g., 📚, 🔪, 🌱).
- **Expert, Not Pushy**: You are a knowledgeable bookseller, not a high-pressure salesperson. Your goal is to help the customer find a book they will love.
"""

def load_product_info() -> str:
    p = Path(__file__).resolve().parent.parent / "product_data" / "jatri_books_info.md"
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to load product info at %s: %s", p, e)
        return "No product information available."

PRODUCT_INFO = load_product_info()
SYSTEM_INSTRUCTION = f"{AGENT_PERSONA_PROMPT}\n\n*** MANDATORY PRODUCT AND CAMPAIGN INFORMATION ***\n{PRODUCT_INFO}\n*** END OF INFORMATION ***"

# ------------------------ Language Helpers ------------------------

def detect_language(text: str) -> str:
    if re.search("[\u0600-\u06FF]", text): return "ar"
    if re.search("[\u0980-\u09FF]", text): return "bn"
    if re.search("[\u0900-\u097F]", text): return "hi"
    return "en"

LANG_MAP = {'en': 'English', 'ar': 'Arabic', 'hi': 'Hindi', 'bn': 'Bengali'}

# ------------------------ Gemini Model Wrapper ------------------------

class GeminiChat:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_INSTRUCTION
        )
        # simple memory per user id
        self._conversations: Dict[int, any] = {}

    def clear(self, user_id: int):
        if user_id in self._conversations:
            del self._conversations[user_id]

    def reply(self, user_id: int, message: str, lang_code: str) -> str:
        if user_id not in self._conversations:
            self._conversations[user_id] = self._model.start_chat(history=[])
        convo = self._conversations[user_id]
        language_name = LANG_MAP.get(lang_code, "English")
        final_instruction = f"FINAL OVERRIDE: The user's language is {language_name}. Your entire response MUST be in {language_name}."
        prompt = f"{message}\n\n---\n{final_instruction}"
        resp = convo.send_message(prompt)
        return resp.text or "Sorry, I couldn't generate a response right now."

# GeminiChat should reference AI_PERSONA_OVERRIDE if set.
