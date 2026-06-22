import logging
from datetime import datetime, timezone

from agents.prompts.nudge_prompts import NUDGE_ALL_IN_ONE
from agents.schemas.nudge_schemas import CombinedNudgeResponse
from db.supabase_client import AsyncSessionFactory
from db.user_profile import ProfileUpdate, update_profile
from orchestrator.state import AgentState
from utils.constants import NUDGE_DISCLAIMER
from utils.gemini_client import generate_json

logger = logging.getLogger(__name__)


def _hours_since_nudge(last_nudge_at: str | None) -> float:
    if not last_nudge_at:
        return 999.0
    try:
        last = datetime.fromisoformat(last_nudge_at)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last
        return delta.total_seconds() / 3600
    except Exception:
        return 999.0


def _assemble_response(
    nudge_content: str | None,
    seekho_content: str | None,
    query_answer: str | None,
) -> str:
    parts: list[str] = []
    if query_answer:
        parts.append(query_answer)
    if nudge_content and not query_answer:
        parts.append(nudge_content)
    if seekho_content:
        parts.append(f"\nSeekho:\n{seekho_content}")
    return "\n\n".join(p.strip() for p in parts if p.strip())


async def run(state: AgentState) -> AgentState:
    user_id = state["user_id"]
    profile = state.get("profile", {})
    risk_flags = state.get("risk_flags", [])
    message = state.get("translated_message", "")
    logger.info("[nudge] started for user=%s", user_id)

    hours_since = _hours_since_nudge(profile.get("last_nudge_at"))

    # Single Gemini call: decide + generate nudge + seekho + query answer
    prompt = NUDGE_ALL_IN_ONE.format(
        message=message,
        persona_type=profile.get("persona_type") or "unknown",
        monthly_income=profile.get("monthly_income", 0),
        monthly_expense=profile.get("monthly_expense", 0),
        savings=profile.get("savings", 0),
        loan_count=len(profile.get("loans", []) or []),
        hours_since_nudge=round(hours_since, 1),
        risk_flags=", ".join(risk_flags) or "none",
        event_types=", ".join(
            e.get("event_type", "") for e in state.get("extracted_events", [])
        ) or "none",
        seekho_level=profile.get("seekho_level", 0),
        disclaimer=NUDGE_DISCLAIMER,
    )

    try:
        result = await generate_json(prompt, response_schema=CombinedNudgeResponse)
    except Exception:
        result = {}

    should_nudge = result.get("should_nudge", False)
    nudge_type = result.get("nudge_type")
    is_query = result.get("is_query", False)
    nudge_content = result.get("nudge_content")
    seekho_content = result.get("seekho_content")
    query_answer = result.get("query_answer")

    logger.info("[nudge] decision: nudge=%s type=%s query=%s user=%s",
                should_nudge, nudge_type, is_query, user_id)

    final_response = _assemble_response(nudge_content, seekho_content, query_answer)

    if should_nudge and nudge_type:
        async with AsyncSessionFactory() as session:
            await update_profile(
                session,
                user_id,
                ProfileUpdate(
                    last_nudge_at=datetime.now(timezone.utc),
                    seekho_level=min((profile.get("seekho_level") or 0) + 1, 10),
                ),
            )

    logger.info("[nudge] done for user=%s", user_id)
    return {
        **state,
        "nudge_type": nudge_type,
        "nudge_content": nudge_content,
        "seekho_content": seekho_content,
        "final_response": final_response,
    }
