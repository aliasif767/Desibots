"""
HisabBot Voice Module
=====================
Two endpoints:

  POST /voice/transcribe
    Receives a WAV/WebM audio blob from the browser microphone.
    Transcribes it with Groq Whisper and returns the text.

  POST /voice/speak
    Receives a text string.
    Converts it to MP3 audio with edge-tts (Urdu voice) and returns the file.

Dependencies (add to requirements.txt):
  edge-tts
  groq          (already present)
"""

import os
import io
import asyncio
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Groq client (reuse from graph config if available, else create fresh) ────
try:
    from app.graph.config import get_groq_client
    def _groq():
        return get_groq_client()
except ImportError:
    from groq import AsyncGroq
    _client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    def _groq():
        return _client

# ── edge-tts voice for Roman Urdu / Hindi-Urdu mix ──────────────────────────
# Best available voice for Pakistani Urdu on edge-tts:
#   ur-PK-AsadNeural   → male,   Pakistani Urdu
#   ur-PK-UzmaNeural   → female, Pakistani Urdu
# Fallback to Hindi if Urdu not installed:
#   hi-IN-MadhurNeural → male Hindi (sounds natural for Roman Urdu)
TTS_VOICE   = "ur-PK-AsadNeural"
TTS_RATE    = "+0%"     # speaking speed: "-10%" slower, "+10%" faster
TTS_VOLUME  = "+0%"

router = APIRouter(prefix="/voice", tags=["voice"])


# ─────────────────────────────────────────────────────────────────────────────
#  ENDPOINT 1 — Speech → Text  (Groq Whisper)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Accept a browser audio blob (webm/wav) and return transcribed Roman Urdu text.

    The browser records via MediaRecorder API and POSTs the blob here.
    Groq Whisper handles Roman Urdu / mixed Urdu-English well with
    language="ur" hint.
    """
    try:
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file received.")

        # Write to a temp file — Groq SDK needs a file-like with a name
        suffix = ".webm" if "webm" in (audio.content_type or "") else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            client = _groq()
            with open(tmp_path, "rb") as f:
                transcription = await client.audio.transcriptions.create(
                    model    = "whisper-large-v3",
                    file     = (audio.filename or f"recording{suffix}", f),
                    language = "ur",          # Urdu — handles Roman Urdu well
                    response_format = "text",
                )
        finally:
            os.unlink(tmp_path)   # always clean up

        text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        if not text:
            return {"text": "", "error": "Koi awaz nahi suni. Dobara bolen."}

        return {"text": text}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
#  ENDPOINT 2 — Text → Speech  (edge-tts)
# ─────────────────────────────────────────────────────────────────────────────

class SpeakRequest(BaseModel):
    text: str
    voice:  str = TTS_VOICE
    rate:   str = TTS_RATE
    volume: str = TTS_VOLUME


@router.post("/speak")
async def speak(req: SpeakRequest):
    """
    Convert text to speech using edge-tts (Microsoft neural voices, free).
    Returns an MP3 audio stream the browser can play directly.

    Roman Urdu text is handled well by ur-PK-AsadNeural.
    Numbers like "Rs 50,000" are read naturally.
    """
    try:
        import edge_tts   # imported here so missing package gives a clear error

        text = req.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="No text provided.")

        # Truncate very long responses — don't read a 2000-word report aloud
        if len(text) > 800:
            text = text[:800] + "..."

        communicate = edge_tts.Communicate(
            text   = text,
            voice  = req.voice,
            rate   = req.rate,
            volume = req.volume,
        )

        # Stream audio into memory buffer
        audio_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])

        audio_buffer.seek(0)
        if audio_buffer.getbuffer().nbytes == 0:
            raise HTTPException(status_code=500, detail="TTS produced no audio.")

        return StreamingResponse(
            audio_buffer,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=response.mp3"},
        )

    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="edge-tts not installed. Run: pip install edge-tts"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
#  ENDPOINT 3 — Combined: voice in → text → agent → audio out
#  (convenience endpoint Streamlit can call in one round-trip)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/chat")
async def voice_chat(audio: UploadFile = File(...)):
    """
    Full pipeline: audio → Whisper → text (returned so UI can display it).
    The caller then sends the text to /chat normally and calls /voice/speak
    on the reply. This keeps the voice pipeline decoupled from the chat logic.
    """
    result = await transcribe(audio)
    return result