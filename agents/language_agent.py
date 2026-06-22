import logging

from agents.prompts.language_prompts import DETECT_AND_TRANSLATE, TRANSLATE_TO_USER_LANG
from agents.schemas.language_schemas import LanguageAndTranslationResponse
from orchestrator.state import AgentState
from utils.constants import SUPPORTED_LANGUAGES
from utils.gemini_client import generate_json, generate_text, transcribe_audio

logger = logging.getLogger(__name__)


async def _detect_and_translate(text: str) -> tuple[str, str]:
    codes = ", ".join(SUPPORTED_LANGUAGES.keys())
    prompt = DETECT_AND_TRANSLATE.format(codes=codes, text=text)
    try:
        result = await generate_json(prompt, response_schema=LanguageAndTranslationResponse)
        lang = result.get("language_code", "hi")
        english = result.get("english_text", text)
        return lang, english
    except Exception:
        return "hi", text


async def _translate_from_english(text: str, lang_code: str) -> str:
    if lang_code == "en":
        return text
    lang_name = SUPPORTED_LANGUAGES.get(lang_code, "Hindi")
    prompt = TRANSLATE_TO_USER_LANG.format(lang_name=lang_name, text=text)
    return await generate_text(prompt)


async def run_incoming(state: AgentState) -> AgentState:
    logger.info("[language_in] started for user=%s", state["user_id"])
    raw_message = state["raw_message"]

    if state["message_type"] == "audio" and state.get("audio_bytes"):
        raw_message = await transcribe_audio(
            audio_bytes=state["audio_bytes"],
            mime_type=state.get("audio_mime_type", "audio/ogg"),
        )

    detected_language, translated_message = await _detect_and_translate(raw_message)

    logger.info("[language_in] done  lang=%s user=%s", detected_language, state["user_id"])
    return {
        **state,
        "raw_message": raw_message,
        "detected_language": detected_language,
        "translated_message": translated_message,
    }


async def run_outgoing(state: AgentState) -> AgentState:
    logger.info("[language_out] started for user=%s", state["user_id"])
    final_response = state.get("final_response", "")

    if not final_response:
        logger.warning("[language_out] no final_response to translate for user=%s", state["user_id"])
        return {**state, "final_response_translated": ""}

    translated = await _translate_from_english(
        text=final_response,
        lang_code=state.get("detected_language", "hi"),
    )

    logger.info("[language_out] done for user=%s", state["user_id"])
    return {**state, "final_response_translated": translated}
