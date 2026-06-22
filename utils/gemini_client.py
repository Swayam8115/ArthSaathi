import asyncio
import base64
from pathlib import Path
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from utils.config import settings

# Initialise SDK once at import time 

genai.configure(api_key=settings.gemini_api_key)

# Model names
_TEXT_MODEL = "gemini-2.5-flash"          # fast, multilingual, strong reasoning
_EMBEDDING_MODEL = "models/text-embedding-004"
_AUDIO_MODEL = "gemini-2.5-flash"         # supports inline audio blobs


# Singleton model instances 

_text_model: genai.GenerativeModel | None = None
_audio_model: genai.GenerativeModel | None = None


def _get_text_model() -> genai.GenerativeModel:
    """Return the singleton text generation model."""
    global _text_model
    if _text_model is None:
        _text_model = genai.GenerativeModel(
            model_name=_TEXT_MODEL,
            generation_config=GenerationConfig(
                temperature=0.3,   # low temp — factual financial context
                max_output_tokens=1024,
            ),
        )
    return _text_model


def _get_audio_model() -> genai.GenerativeModel:
    """Return the singleton audio-understanding model."""
    global _audio_model
    if _audio_model is None:
        _audio_model = genai.GenerativeModel(model_name=_AUDIO_MODEL)
    return _audio_model


# Public async API


async def generate_text(prompt: str, system_instruction: str | None = None) -> str:
    """
    Generate a text response from Gemini.

    Args:
        prompt: The user/agent prompt (always in English internally).
        system_instruction: Optional system-level instruction prepended to the prompt.

    Returns:
        The model's text response as a plain string.
    """
    model = _get_text_model()

    def _call() -> str:
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"
        else:
            full_prompt = prompt
        response = model.generate_content(full_prompt)
        return response.text.strip()

    return await asyncio.to_thread(_call)


async def get_embedding(text: str) -> list[float]:
    """
    Generate a 768-dimensional embedding vector using text-embedding-004.

    Used by the Profile Agent to embed financial context summaries
    for later RAG retrieval.

    Args:
        text: The text to embed (always English).

    Returns:
        A list of 768 floats representing the embedding vector.
    """
    def _call() -> list[float]:
        result = genai.embed_content(
            model=_EMBEDDING_MODEL,
            content=text,
            task_type="retrieval_document",
        )
        return result["embedding"]

    return await asyncio.to_thread(_call)


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """
    Transcribe a WhatsApp voice message to text using Gemini Audio Understanding.

    WhatsApp voice notes arrive as OGG/Opus audio. The bytes are sent inline
    as a base64-encoded blob — no file upload required.

    Args:
        audio_bytes: Raw audio bytes downloaded from the WhatsApp media endpoint.
        mime_type:   MIME type of the audio (default: audio/ogg for WhatsApp voice notes).

    Returns:
        Transcribed text in the user's original language.
        Language detection + translation is handled separately by the Language Agent.
    """
    model = _get_audio_model()

    def _call() -> str:
        audio_part = {
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(audio_bytes).decode("utf-8"),
            }
        }
        response = model.generate_content(
            [
                audio_part,
                "Transcribe this audio message exactly as spoken. "
                "Do not translate — output the original spoken language.",
            ]
        )
        return response.text.strip()

    return await asyncio.to_thread(_call)
