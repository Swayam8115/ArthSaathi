import asyncio
from datetime import datetime, timezone

from agents.prompts.nudge_prompts import (
    ANSWER_QUERY,
    GENERATE_NUDGE,
    NUDGE_DECISION,
    NUDGE_TO_CONCEPT,
    SEEKHO_LESSON,
)
from agents.schemas.nudge_schemas import NudgeDecisionResponse
from db.supabase_client import AsyncSessionFactory
from db.user_profile import ProfileUpdate, update_profile
from orchestrator.graph import AgentState
from utils.constants import NUDGE_DISCLAIMER
from utils.gemini_client import generate_json, generate_text


# Internal helpers 


def _hours_since_nudge(last_nudge_at: str | None) -> float:
    """Return hours elapsed since the last nudge. Returns 999 if never nudged."""
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


async def _decide_nudge(state: AgentState, hours_since: float) -> NudgeDecisionResponse:
    """Ask Gemini to decide if and what nudge to send."""
    profile = state.get("profile", {})
    prompt = NUDGE_DECISION.format(
        message=state.get("translated_message", ""),
        persona_type=profile.get("persona_type") or "unknown",
        monthly_income=profile.get("monthly_income", 0),
        monthly_expense=profile.get("monthly_expense", 0),
        savings=profile.get("savings", 0),
        loan_count=len(profile.get("loans", []) or []),
        seekho_level=profile.get("seekho_level", 0),
        hours_since_nudge=round(hours_since, 1),
        risk_flags=", ".join(state.get("risk_flags", [])) or "none",
        event_types=", ".join(
            e.get("event_type", "") for e in state.get("extracted_events", [])
        ) or "none",
    )
    try:
        result = await generate_json(prompt, response_schema=NudgeDecisionResponse)
        return NudgeDecisionResponse(**result) if isinstance(result, dict) else NudgeDecisionResponse(
            should_nudge=False, nudge_type=None, is_query=False, reasoning="parse error"
        )
    except Exception:
        return NudgeDecisionResponse(
            should_nudge=False, nudge_type=None, is_query=False, reasoning="decision error"
        )


async def _generate_nudge_content(nudge_type: str, profile: dict, risk_flags: list[str]) -> str:
    """Generate the nudge text for the chosen nudge type."""
    prompt = GENERATE_NUDGE.format(
        nudge_type=nudge_type,
        persona_type=profile.get("persona_type") or "unknown",
        monthly_income=profile.get("monthly_income", 0),
        monthly_expense=profile.get("monthly_expense", 0),
        savings=profile.get("savings", 0),
        risk_flags=", ".join(risk_flags) or "none",
        disclaimer=NUDGE_DISCLAIMER,
    )
    return await generate_text(prompt)


async def _generate_seekho(nudge_type: str, profile: dict) -> str:
    """Generate a Seekho micro-lesson tied to the nudge concept."""
    concept = NUDGE_TO_CONCEPT.get(nudge_type, "basic personal finance")
    prompt = SEEKHO_LESSON.format(
        concept=concept,
        monthly_income=profile.get("monthly_income", 0),
        savings=profile.get("savings", 0),
        persona_type=profile.get("persona_type") or "unknown",
        seekho_level=profile.get("seekho_level", 0),
    )
    return await generate_text(prompt)


async def _answer_query(message: str, profile: dict) -> str:
    """Generate a direct answer to a user's financial question."""
    prompt = ANSWER_QUERY.format(
        question=message,
        persona_type=profile.get("persona_type") or "unknown",
        disclaimer=NUDGE_DISCLAIMER,
    )
    return await generate_text(prompt)


def _assemble_response(
    nudge_content: str | None,
    seekho_content: str | None,
    query_answer: str | None,
) -> str:
    """
    Assemble the final WhatsApp message from nudge + seekho parts.
    The disclaimer is already embedded in nudge/query content by the prompts.
    """
    parts: list[str] = []

    if query_answer:
        parts.append(query_answer)

    if nudge_content and not query_answer:
        parts.append(nudge_content)

    if seekho_content:
        parts.append(f"\nSeekho:\n{seekho_content}")

    return "\n\n".join(p.strip() for p in parts if p.strip())


# LangGraph node function 


async def run(state: AgentState) -> AgentState:
    """
    Nudge Agent node.

    Skipped by the orchestrator when interrupt=True.

    Decides nudge type, generates content, produces Seekho lesson,
    assembles final_response, and updates the DB.

    Updates state keys: nudge_type, nudge_content, seekho_content, final_response.
    """
    profile = state.get("profile", {})
    user_id = state["user_id"]
    risk_flags = state.get("risk_flags", [])
    message = state.get("translated_message", "")

    hours_since = _hours_since_nudge(profile.get("last_nudge_at"))

    # Step 1: decide if and what nudge to send
    decision = await _decide_nudge(state, hours_since)

    nudge_type = decision.nudge_type

    # Step 2: run all generation tasks concurrently — _noop() fills skipped slots
    nudge_content, seekho_content, query_answer = await asyncio.gather(
        _generate_nudge_content(nudge_type, profile, risk_flags)
            if decision.should_nudge and nudge_type else _noop(),
        _generate_seekho(nudge_type, profile)
            if nudge_type else _noop(),
        _answer_query(message, profile)
            if decision.is_query else _noop(),
    )

    # Step 3: assemble final response
    final_response = _assemble_response(nudge_content, seekho_content, query_answer)

    # Step 4: persist DB updates if a nudge was sent
    if decision.should_nudge and nudge_type:
        async with AsyncSessionFactory() as session:
            await update_profile(
                session,
                user_id,
                ProfileUpdate(
                    last_nudge_at=datetime.now(timezone.utc),
                    seekho_level=min((profile.get("seekho_level") or 0) + 1, 10),
                ),
            )

    return {
        **state,
        "nudge_type": nudge_type,
        "nudge_content": nudge_content,
        "seekho_content": seekho_content,
        "final_response": final_response,
    }


async def _noop() -> None:
    """Async no-op placeholder for asyncio.gather slots that are skipped."""
    return None
