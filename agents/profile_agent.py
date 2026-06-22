import json
from datetime import datetime, timezone

from agents.prompts.profile_prompts import EXTRACT_FINANCIAL_EVENTS, INFER_PERSONA
from db.supabase_client import AsyncSessionFactory
from db.user_profile import (
    FinancialEventCreate,
    LoanRecord,
    ProfileUpdate,
    append_financial_event,
    get_or_create_profile,
    update_profile,
)
from orchestrator.graph import AgentState
from utils.gemini_client import generate_json


# Internal helpers 


async def _extract_events(message: str) -> list[dict]:
    """
    Ask Gemini to extract financial events from the English message.
    Returns a list of event dicts; falls back to [] on any parse error.
    """
    prompt = EXTRACT_FINANCIAL_EVENTS.format(message=message)
    try:
        result = await generate_json(prompt)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, Exception):
        return []


async def _infer_persona(message: str) -> str | None:
    """
    Ask Gemini to infer the user's persona type from the message.
    Returns one of the valid persona strings, or None if inconclusive.
    """
    prompt = INFER_PERSONA.format(message=message)
    try:
        result = await generate_json(prompt)
        persona = result.get("persona_type") if isinstance(result, dict) else None
        valid = {"salaried", "gig", "farmer", "freelancer"}
        return persona if persona in valid else None
    except Exception:
        return None


def _build_profile_update(
    current_profile,
    events: list[dict],
    inferred_persona: str | None,
) -> tuple[ProfileUpdate, list[LoanRecord]]:
    """
    Compute the ProfileUpdate and any new LoanRecords from the extracted events.

    Income and expense amounts are accumulated onto the current monthly totals.
    Savings is set to the reported value (most recent self-report wins).
    """
    income_delta = sum(
        e.get("amount") or 0 for e in events if e.get("event_type") == "income"
    )
    expense_delta = sum(
        e.get("amount") or 0 for e in events if e.get("event_type") == "expense"
    )
    savings_events = [e for e in events if e.get("event_type") == "savings"]
    loan_events = [e for e in events if e.get("event_type") == "loan"]

    new_loans: list[LoanRecord] = [
        LoanRecord(
            source=e.get("description", "Unknown"),
            amount=e.get("amount") or 0,
            detected_at=datetime.now(timezone.utc),
        )
        for e in loan_events
        if e.get("amount")
    ]

    existing_loans: list = current_profile.loans or []

    update = ProfileUpdate(
        monthly_income=float(current_profile.monthly_income or 0) + income_delta,
        monthly_expense=float(current_profile.monthly_expense or 0) + expense_delta,
        savings=(
            float(savings_events[-1].get("amount") or current_profile.savings or 0)
            if savings_events
            else None
        ),
        loans=(
            [LoanRecord(**l) if isinstance(l, dict) else l for l in existing_loans]
            + new_loans
        ) if new_loans else None,
        persona_type=(
            inferred_persona
            if inferred_persona and not current_profile.persona_type
            else None
        ),
    )
    return update, new_loans


# LangGraph node function


async def run(state: AgentState) -> AgentState:
    """
    Profile Agent node.

    Reads the English-translated message, extracts financial events,
    updates the Supabase profile, and writes a profile snapshot to state.

    Updates state keys: profile, extracted_events.
    """
    user_id = state["user_id"]
    message = state.get("translated_message", "")

    # Run extraction and persona inference concurrently
    import asyncio
    events, inferred_persona = await asyncio.gather(
        _extract_events(message),
        _infer_persona(message),
    )

    async with AsyncSessionFactory() as session:
        # Get or create the user profile
        profile = await get_or_create_profile(
            session, user_id, language=state.get("detected_language", "hi")
        )

        # Compute updates from extracted events
        update, _ = _build_profile_update(profile, events, inferred_persona)

        # Persist profile updates (only if there's something to update)
        if update.model_dump(exclude_none=True):
            profile = await update_profile(session, user_id, update)

        # Persist each financial event to the events table
        for event in events:
            event_type = event.get("event_type", "query")
            if event_type not in {"income", "expense", "loan", "savings", "query"}:
                continue
            await append_financial_event(
                session,
                FinancialEventCreate(
                    user_id=user_id,
                    event_type=event_type,
                    amount=event.get("amount"),
                    description=event.get("description"),
                    raw_message=state.get("raw_message"),
                ),
            )

        # Snapshot the profile as a plain dict for downstream agents
        profile_snapshot = {
            "user_id": profile.user_id,
            "language": profile.language,
            "persona_type": profile.persona_type,
            "monthly_income": float(profile.monthly_income or 0),
            "monthly_expense": float(profile.monthly_expense or 0),
            "savings": float(profile.savings or 0),
            "loans": profile.loans or [],
            "last_nudge_at": (
                profile.last_nudge_at.isoformat() if profile.last_nudge_at else None
            ),
            "seekho_level": profile.seekho_level or 0,
        }

    return {
        **state,
        "profile": profile_snapshot,
        "extracted_events": events,
    }
