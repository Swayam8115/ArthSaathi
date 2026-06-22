import asyncio
import logging
from datetime import datetime, timezone, timedelta

from agents.prompts.pattern_prompts import (
    INTERRUPT_NUDGE_DISTRESS,
    INTERRUPT_NUDGE_PREDATORY_LOAN,
    SEMANTIC_RISK_CHECK,
)
from agents.schemas.pattern_schemas import SemanticRiskResponse
from db.supabase_client import AsyncSessionFactory
from db.user_profile import get_recent_events
from orchestrator.state import AgentState
from utils.constants import ESCALATION_MESSAGE, NO_SAVINGS_THRESHOLD_DAYS, NUDGE_DISCLAIMER
from utils.gemini_client import generate_json, generate_text

logger = logging.getLogger(__name__)


# Rule-based pattern checks 


def _check_rules(profile: dict, recent_events: list) -> list[str]:
    """
    Fast, deterministic risk checks that require no Gemini call.

    Returns a list of risk flag strings.
    """
    flags: list[str] = []

    monthly_income = profile.get("monthly_income", 0) or 0
    monthly_expense = profile.get("monthly_expense", 0) or 0
    savings = profile.get("savings", 0) or 0
    persona_type = profile.get("persona_type")
    loans: list = profile.get("loans", []) or []

    # Overspending: expenses exceed income (only flag when both are non-zero)
    if monthly_income > 0 and monthly_expense > monthly_income:
        flags.append("overspending")

    # High debt ratio: total loan principal > 6 months of income
    if monthly_income > 0 and loans:
        total_loan = sum(float(l.get("amount", 0)) for l in loans)
        if total_loan > monthly_income * 6:
            flags.append("high_debt_ratio")

    # No savings in past 30 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=NO_SAVINGS_THRESHOLD_DAYS)
    recent_savings = [
        e for e in recent_events
        if e.event_type == "savings"
        and e.occurred_at
        and e.occurred_at.replace(tzinfo=timezone.utc) > cutoff
    ]
    if savings == 0 and not recent_savings and len(recent_events) > 0:
        flags.append("no_savings_30d")

    # Seasonal income gap: farmer with no income event in 30 days
    if persona_type == "farmer":
        recent_income = [
            e for e in recent_events
            if e.event_type == "income"
            and e.occurred_at
            and e.occurred_at.replace(tzinfo=timezone.utc) > cutoff
        ]
        if not recent_income:
            flags.append("seasonal_income_gap")

    return flags


# Semantic pattern check 


async def _check_semantic(message: str, profile: dict) -> SemanticRiskResponse:
    """
    Ask Gemini to detect predatory loan language and distress signals in the message.
    Falls back to a safe no-risk response on any error.
    """
    prompt = SEMANTIC_RISK_CHECK.format(
        message=message,
        monthly_income=profile.get("monthly_income", 0),
        monthly_expense=profile.get("monthly_expense", 0),
        savings=profile.get("savings", 0),
        persona_type=profile.get("persona_type") or "unknown",
        loan_count=len(profile.get("loans", []) or []),
    )
    try:
        result = await generate_json(prompt, response_schema=SemanticRiskResponse)
        return SemanticRiskResponse(**result) if isinstance(result, dict) else SemanticRiskResponse(
            predatory_loan=False, distress_signal=False, reasoning="parse error"
        )
    except Exception:
        return SemanticRiskResponse(
            predatory_loan=False, distress_signal=False, reasoning="detection error"
        )


# Interrupt nudge generation 


async def _generate_interrupt_nudge(risk_flags: list[str]) -> str:
    """
    Generate an urgent nudge for high-risk patterns.
    distress_signal takes priority over predatory_loan.
    """
    if "distress_signal" in risk_flags:
        prompt = INTERRUPT_NUDGE_DISTRESS
    else:
        prompt = INTERRUPT_NUDGE_PREDATORY_LOAN.format(disclaimer=NUDGE_DISCLAIMER)

    return await generate_text(prompt)


# LangGraph node function


async def run(state: AgentState) -> AgentState:
    """
    Pattern Agent node.

    Runs rule-based and semantic checks concurrently, merges risk flags,
    and sets interrupt=True + nudge_content if a high-risk pattern is found.

    Updates state keys: risk_flags, interrupt, nudge_type, nudge_content.
    """
    user_id = state["user_id"]
    profile = state.get("profile", {})
    message = state.get("translated_message", "")
    logger.info("[pattern] started for user=%s", user_id)

    # Fetch recent events from DB and run semantic check concurrently
    async with AsyncSessionFactory() as session:
        recent_events = await get_recent_events(session, user_id, limit=30)

    rule_flags, semantic_result = await asyncio.gather(
        asyncio.to_thread(_check_rules, profile, recent_events),
        _check_semantic(message, profile),
    )

    # Merge all flags
    semantic_flags: list[str] = []
    if semantic_result.predatory_loan:
        semantic_flags.append("predatory_loan")
    if semantic_result.distress_signal:
        semantic_flags.append("distress_signal")

    all_flags = list(dict.fromkeys(rule_flags + semantic_flags))  # deduplicated, ordered

    # Determine if this is a high-risk interrupt situation
    high_risk = {"predatory_loan", "distress_signal"}
    should_interrupt = bool(high_risk & set(all_flags))

    nudge_type = None
    nudge_content = None

    if should_interrupt:
        nudge_type = "loan_warning" if "predatory_loan" in all_flags else "distress_escalation"
        nudge_content = await _generate_interrupt_nudge(all_flags)

    logger.info("[pattern] done  flags=%s interrupt=%s user=%s", all_flags, should_interrupt, user_id)
    return {
        **state,
        "risk_flags": all_flags,
        "interrupt": should_interrupt,
        "nudge_type": nudge_type,
        "nudge_content": nudge_content,
        "final_response": nudge_content or "",
    }
