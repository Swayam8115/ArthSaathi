import asyncio
import base64
import json
import logging
import re
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from google.api_core.exceptions import ResourceExhausted

from utils.config import settings

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.gemini_api_key)

_TEXT_MODEL = "gemini-2.5-flash"
_EMBEDDING_MODEL = "models/text-embedding-004"
_AUDIO_MODEL = "gemini-2.5-flash"

_MAX_RETRIES = 1
_DEFAULT_RETRY_DELAY = 20.0
_REQUEST_TIMEOUT = 30  # seconds — Gemini SDK per-call timeout


def _parse_retry_delay(exc: ResourceExhausted) -> float:
    match = re.search(r"retry in ([\d.]+)s", str(exc))
    return float(match.group(1)) + 1.0 if match else _DEFAULT_RETRY_DELAY


async def _with_retry(coro_fn):
    await asyncio.sleep(14)  # pace calls to stay within free-tier rate limits
    for attempt in range(_MAX_RETRIES):
        try:
            logger.debug("Gemini call attempt %d/%d", attempt + 1, _MAX_RETRIES)
            return await coro_fn()
        except ResourceExhausted as exc:
            if attempt == _MAX_RETRIES - 1:
                logger.error("Gemini rate limit — all %d retries exhausted", _MAX_RETRIES)
                raise
            delay = _parse_retry_delay(exc)
            logger.warning("Gemini rate limit hit — waiting %.0fs before retry %d/%d",
                           delay, attempt + 2, _MAX_RETRIES)
            await asyncio.sleep(delay)


_text_model: genai.GenerativeModel | None = None
_audio_model: genai.GenerativeModel | None = None


def _get_text_model() -> genai.GenerativeModel:
    global _text_model
    if _text_model is None:
        _text_model = genai.GenerativeModel(
            model_name=_TEXT_MODEL,
            generation_config=GenerationConfig(temperature=0.3, max_output_tokens=1024),
        )
    return _text_model


def _get_audio_model() -> genai.GenerativeModel:
    global _audio_model
    if _audio_model is None:
        _audio_model = genai.GenerativeModel(model_name=_AUDIO_MODEL)
    return _audio_model


async def generate_text(prompt: str, system_instruction: str | None = None) -> str:
    model = _get_text_model()
    full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt

    async def _attempt():
        def _call() -> str:
            response = model.generate_content(
                full_prompt,
                request_options={"timeout": _REQUEST_TIMEOUT},
            )
            return response.text.strip()
        return await asyncio.to_thread(_call)

    return await _with_retry(_attempt)


async def get_embedding(text: str) -> list[float]:
    async def _attempt():
        def _call() -> list[float]:
            result = genai.embed_content(
                model=_EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_document",
                request_options={"timeout": _REQUEST_TIMEOUT},
            )
            return result["embedding"]
        return await asyncio.to_thread(_call)

    return await _with_retry(_attempt)


async def generate_json(
    prompt: str,
    system_instruction: str | None = None,
    response_schema=None,
) -> dict | list:
    model = _get_text_model()
    full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt

    async def _attempt():
        def _call() -> dict | list:
            config_kwargs: dict = {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": 1024,
            }
            if response_schema is not None:
                config_kwargs["response_schema"] = response_schema
            response = model.generate_content(
                full_prompt,
                generation_config=GenerationConfig(**config_kwargs),
                request_options={"timeout": _REQUEST_TIMEOUT},
            )
            return json.loads(response.text)
        return await asyncio.to_thread(_call)

    return await _with_retry(_attempt)


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    model = _get_audio_model()
    audio_part = {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.b64encode(audio_bytes).decode("utf-8"),
        }
    }

    async def _attempt():
        def _call() -> str:
            response = model.generate_content(
                [
                    audio_part,
                    "Transcribe this audio message exactly as spoken. "
                    "Do not translate — output the original spoken language.",
                ],
                request_options={"timeout": _REQUEST_TIMEOUT},
            )
            return response.text.strip()
        return await asyncio.to_thread(_call)

    return await _with_retry(_attempt)
