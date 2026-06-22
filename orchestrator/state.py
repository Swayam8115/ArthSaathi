from typing import Any
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """
    Shared state object passed through every node in the LangGraph pipeline.

    Agents read from this dict and return an updated copy.
    Only the keys a particular agent cares about need to be touched.
    """

    # Incoming message
    user_id: str                   # WhatsApp phone number (E.164)
    raw_message: str               # original text from user (or empty if voice)
    message_type: str              # "text" | "audio"
    audio_bytes: bytes | None      # raw OGG bytes for voice messages
    audio_mime_type: str           # default "audio/ogg"

    # Language Agent (first pass)
    detected_language: str         # BCP-47 code e.g. "hi", "mr", "kn"
    translated_message: str        # English translation of the user's message

    # Profile Agent
    profile: dict[str, Any]        # serialised UserProfile snapshot
    extracted_events: list[dict]   # financial events parsed from this message

    # Pattern Agent
    risk_flags: list[str]          # e.g. ["overspending", "predatory_loan"]
    interrupt: bool                # True → Pattern Agent bypasses Nudge Agent

    # Nudge Agent
    nudge_type: str | None         # e.g. "savings_nudge", "loan_warning"
    nudge_content: str | None      # English nudge text
    seekho_content: str | None     # English micro-lesson text

    # Language Agent (second pass)
    final_response: str            # assembled English response (nudge + seekho)
    final_response_translated: str # response in user's language → sent to WhatsApp
