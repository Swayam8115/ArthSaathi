from agents.prompts.language_prompts import (
    DETECT_LANGUAGE,
    TRANSLATE_TO_ENGLISH,
    TRANSLATE_TO_USER_LANG,
)
from orchestrator.graph import AgentState
from utils.constants import SUPPORTED_LANGUAGES
from utils.gemini_client import generate_text, transcribe_audio


async def _detect_language(text: str) -> str:
    """
    Ask Gemini to identify the BCP-47 language code of the given text.
    Falls back to 'hi' (Hindi) if the response is unrecognised.
    """
    supported_codes = ", ".join(SUPPORTED_LANGUAGES.keys())
    prompt = DETECT_LANGUAGE.format(codes=supported_codes, text=text)
    raw = await generate_text(prompt)
    detected = raw.strip().lower().split()[0]  # take first token only
    return detected if detected in SUPPORTED_LANGUAGES else "hi"


async def _translate_to_english(text: str, lang_code: str) -> str:
    """Translate text from lang_code to English. Returns original if already English."""
    if lang_code == "en":
        return text
    lang_name = SUPPORTED_LANGUAGES.get(lang_code, "Hindi")
    prompt = TRANSLATE_TO_ENGLISH.format(lang_name=lang_name, text=text)
    return await generate_text(prompt)


async def _translate_from_english(text: str, lang_code: str) -> str:
    """Translate English text back to the user's language. No-op if English."""
    if lang_code == "en":
        return text
    lang_name = SUPPORTED_LANGUAGES.get(lang_code, "Hindi")
    prompt = TRANSLATE_TO_USER_LANG.format(lang_name=lang_name, text=text)
    return await generate_text(prompt)


async def run_incoming(state: AgentState) -> AgentState:
    """
    First-pass Language Agent node.

    Handles audio transcription, language detection, and translation to English.
    Updates state keys: raw_message, detected_language, translated_message.
    """
    raw_message = state["raw_message"]

    if state["message_type"] == "audio" and state.get("audio_bytes"):
        raw_message = await transcribe_audio(
            audio_bytes=state["audio_bytes"],
            mime_type=state.get("audio_mime_type", "audio/ogg"),
        )

    detected_language = await _detect_language(raw_message)
    translated_message = await _translate_to_english(raw_message, detected_language)

    return {
        **state,
        "raw_message": raw_message,
        "detected_language": detected_language,
        "translated_message": translated_message,
    }


async def run_outgoing(state: AgentState) -> AgentState:
    """
    Second-pass Language Agent node — last step in the pipeline.

    Translates the assembled English response back to the user's language.
    Updates state key: final_response_translated.
    """
    final_response = state.get("final_response", "")

    if not final_response:
        return {**state, "final_response_translated": ""}

    translated = await _translate_from_english(
        text=final_response,
        lang_code=state.get("detected_language", "hi"),
    )

    return {**state, "final_response_translated": translated}
