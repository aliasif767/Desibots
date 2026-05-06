
import asyncio
import re

# Mock BOT_REGISTRY
BOT_REGISTRY = {
    "hisabbot": {"name": "HisabBot"},
    "sehatbot": {"name": "SehatBot"},
    "pakorderbot": {"name": "PakOrderBot"},
    "lawyerbot": {"name": "LawyerBot"},
}

def _switched_text(bot_key):
    return f"Switched to {BOT_REGISTRY[bot_key]['name']}"

async def mock_dispatch(text):
    text = text.strip()
    if text.startswith("/"):
        cmd = text[1:].lower().split()[0]
        print(f"DEBUG: Detected command: '{cmd}'")
        if cmd in BOT_REGISTRY:
            return _switched_text(cmd)
        return "Unknown command"
    return "Forwarding to bot"

async def test():
    print(await mock_dispatch("/pakorderbot"))
    print(await mock_dispatch("/lawyerbot"))
    print(await mock_dispatch("/hisabbot"))
    print(await mock_dispatch("/sehatbot"))
    print(await mock_dispatch("/pakorderbot ")) # trailing space
    print(await mock_dispatch(" /pakorderbot")) # leading space
    print(await mock_dispatch("/PakOrderBot"))  # casing

asyncio.run(test())
