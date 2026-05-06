"""
HisabBot — Shared config: LLM client, model, and prompt constants.
All other modules import from here — never instantiate groq_client elsewhere.

groq_client is initialised lazily on first use so a missing GROQ_API_KEY in
the environment does NOT crash the process at import time (e.g. during testing
or before dotenv is loaded).
"""

import os
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()   # picks up .env if present — safe no-op if already loaded

MODEL = "llama-3.3-70b-versatile"

_groq_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    """Return the shared AsyncGroq client, creating it on first call."""
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Add it to your .env file or set it as an environment variable."
            )
        _groq_client = AsyncGroq(api_key=api_key)
    return _groq_client


# Convenience alias — modules do: from .config import groq_client, MODEL
# This is a proxy object: calling groq_client.chat... triggers get_groq_client()
class _LazyGroqClient:
    """Thin proxy that initialises the real client on first attribute access."""
    def __getattr__(self, name):
        return getattr(get_groq_client(), name)


groq_client = _LazyGroqClient()

JSON_RULE = "Return ONLY a valid json object. No markdown. No explanation. IMPORTANT: Do NOT include arithmetic expressions (like 1+1) in any numeric fields; calculate the final value yourself."

DATE_RULES = """
=== DATE PLACEHOLDERS (Python resolves at runtime) ===
"__TODAY_START__"          = today 00:00 UTC
"__TODAY_END__"            = today 23:59 UTC
"__WEEK_START__"           = 7 days ago 00:00 UTC
"__MONTH_START__"          = 1st of current month
"__MONTH_END__"            = last moment of current month
"__YEAR_START__"           = 1st Jan current year
"__YEAR_END__"             = 31st Dec current year 23:59
"__PREV_MONTH_START__"     = 1st of last month
"__PREV_MONTH_END__"       = last moment of last month
"__PREV_YEAR_START__"      = 1st Jan last year
"__PREV_YEAR_END__"        = 31st Dec last year 23:59
"__MONTHS_AGO_N_START__"   = 1st of N months ago  (e.g. __MONTHS_AGO_2_START__)
"__MONTHS_AGO_N_END__"     = last moment of N months ago
"__DAYS_AGO_N__"           = N days ago  (e.g. __DAYS_AGO_30__)

RULES:
- "aaj" → $gte __TODAY_START__ AND $lte __TODAY_END__
- "is mahine" → $gte __MONTH_START__ AND $lte __MONTH_END__
- "pichle mahine" → $gte __PREV_MONTH_START__ AND $lte __PREV_MONTH_END__
- "pichle saal" → $gte __PREV_YEAR_START__ AND $lte __PREV_YEAR_END__
- "is saal" → $gte __YEAR_START__ AND $lte __YEAR_END__
- "abi tak" / "kabhi bhi" → NO date filter
- ALWAYS use BOTH $gte AND $lte. Never just one side.
"""