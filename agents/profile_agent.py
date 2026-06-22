import json
import logging
from datetime import datetime, timezone

from agents.prompts.profile_prompts import EXTRACT_AND_INFER
from agents.schemas.profile_schemas import CombinedProfileResponse
from db.supabase_client import AsyncSessionFactory
from db.user_profile import (
    FinancialEventCreate,
    LoanRecord,
    ProfileUpdate,
    append_financial_event,
    get_or_create_profile,
    update_profile,
)
from orchestrator.state import AgentState
from utils.gemini_client import generate_json

logger = logging.getLogger(__name__)


async def _extract_and_infer(message: str) -> tuple[list[dict], str | None]:
    prompt = EXTRACT_AND_INFER.format(message=message)
    try:
        result = await generate_json(prompt, response_schema=CombinedProfileResponse)
        events = result.get("events", []) if isinstance(result, dict) else []
        persona = result.get("persona_type") if isinstance(result, dict) else None
        valid_personas = {"salaried", "gig", "farmer", "freelancer"}
        return events, (persona if persona in valid_personas else None)
    except (json.JSONDecodeError, Exception):
        return [], None


def _build_profile_update(
    current_profile,
    events: list[dict],
    inferred_persona: str | None,
) -> tuple[ProfileUpdate, list[LoanRecord]]:
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


async def run(state: AgentState) -> AgentState:
    user_id = state["user_id"]
    message = state.get("translated_message", "")
    logger.info("[profile] started for user=%s", user_id)

    # Single Gemini call: extract events + infer persona together
    events, inferred_persona = await _extract_and_infer(message)

    async with AsyncSessionFactory() as session:
        profile = await get_or_create_profile(
            session, user_id, language=state.get("detected_language", "hi")
        )

        update, _ = _build_profile_update(profile, events, inferred_persona)

        if update.model_dump(exclude_none=True):
            profile = await update_profile(session, user_id, update)

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

    logger.info("[profile] done  events=%d user=%s", len(events), user_id)
    return {
        **state,
        "profile": profile_snapshot,
        "extracted_events": events,
    }
