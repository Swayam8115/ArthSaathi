"""
Celery tasks for scheduled and event-driven nudge delivery.

Tasks:
  send_scheduled_nudge()   — send a proactive nudge to a single user (queued on-demand)
  check_inactive_users()   — daily beat task: find quiet users and queue nudges
  seasonal_farmer_check()  — monthly beat task: remind farmers about seasonal schemes

Celery workers are synchronous, so all async calls are wrapped with asyncio.run().
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import select, and_

from db.supabase_client import AsyncSessionFactory
from db.models import UserProfile
from api.whatsapp import send_message
from utils.gemini_client import generate_text
from utils.constants import NUDGE_DISCLAIMER

logger = logging.getLogger(__name__)

# Users inactive for this many days get a proactive check-in
_INACTIVE_THRESHOLD_DAYS = 7

# Prompt for proactive scheduled nudge 

_PROACTIVE_NUDGE_PROMPT = """\
You are ArthSaathi, a financial literacy assistant sending a gentle proactive check-in
to a user who hasn't been active for a few days.

Write a SHORT, warm, encouraging message (2-3 sentences).
Rules:
- Invite them to share any recent financial update (income, expense, savings)
- Tone: friendly, non-intrusive, no pressure
- End with: "{disclaimer}"

User persona: {persona_type}
Monthly income (last known): ₹{monthly_income}

Write ONLY the message. No heading.
"""

_FARMER_SEASONAL_PROMPT = """\
You are ArthSaathi sending a monthly seasonal reminder to a farmer.

Write a SHORT, relevant message (2-3 sentences) about one of these topics
(pick the most seasonally appropriate for an Indian farmer in the current month):
- Kisan Credit Card usage
- PM-KISAN installment check
- Crop insurance renewal (PMFBY)
- Post-harvest savings opportunity

End with: "{disclaimer}"

Write ONLY the message. No heading.
"""


# Helper 

def _run(coro):
    """Run an async coroutine from a synchronous Celery task."""
    return asyncio.run(coro)


# Tasks 

@shared_task(name="scheduler.nudge_tasks.send_scheduled_nudge", bind=True, max_retries=3)
def send_scheduled_nudge(self, user_id: str, nudge_type: str = "proactive_checkin") -> dict:
    """
    Send a proactive nudge to a single user.

    Queued on-demand by check_inactive_users() or external triggers.
    Retries up to 3 times on failure with exponential backoff.

    Args:
        user_id  : WhatsApp phone number (E.164)
        nudge_type: Type label for logging (not used for routing here)
    """
    async def _task():
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()

        if not profile:
            logger.warning("send_scheduled_nudge: no profile found for %s", user_id)
            return {"status": "skipped", "reason": "no_profile"}

        prompt = _PROACTIVE_NUDGE_PROMPT.format(
            persona_type=profile.persona_type or "unknown",
            monthly_income=float(profile.monthly_income or 0),
            disclaimer=NUDGE_DISCLAIMER,
        )
        message = await generate_text(prompt)
        await send_message(to=user_id, text=message)

        # Update last_nudge_at
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            p = result.scalar_one_or_none()
            if p:
                p.last_nudge_at = datetime.now(timezone.utc)
                await session.commit()

        return {"status": "sent", "user_id": user_id, "nudge_type": nudge_type}

    try:
        return _run(_task())
    except Exception as exc:
        logger.exception("send_scheduled_nudge failed for %s", user_id)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 60)


@shared_task(name="scheduler.nudge_tasks.check_inactive_users")
def check_inactive_users() -> dict:
    """
    Daily beat task (9 AM IST).

    Finds users whose last_nudge_at is older than _INACTIVE_THRESHOLD_DAYS
    and queues a send_scheduled_nudge task for each.
    """
    async def _task() -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=_INACTIVE_THRESHOLD_DAYS)
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(UserProfile.user_id).where(
                    and_(
                        UserProfile.last_nudge_at < cutoff,
                        UserProfile.monthly_income > 0,  # only nudge users with profile data
                    )
                )
            )
            return [row[0] for row in result.fetchall()]

    user_ids = _run(_task())

    for user_id in user_ids:
        send_scheduled_nudge.delay(user_id, nudge_type="proactive_checkin")

    logger.info("check_inactive_users: queued nudges for %d users", len(user_ids))
    return {"queued": len(user_ids)}


@shared_task(name="scheduler.nudge_tasks.seasonal_farmer_check")
def seasonal_farmer_check() -> dict:
    """
    Monthly beat task (1st of month, 9 AM IST).

    Sends a seasonal scheme reminder to all users with persona_type='farmer'.
    """
    async def _task() -> list[str]:
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(UserProfile.user_id).where(
                    UserProfile.persona_type == "farmer"
                )
            )
            return [row[0] for row in result.fetchall()]

    async def _send_farmer_nudge(user_id: str) -> None:
        message = await generate_text(
            _FARMER_SEASONAL_PROMPT.format(disclaimer=NUDGE_DISCLAIMER)
        )
        await send_message(to=user_id, text=message)

    farmer_ids = _run(_task())

    for user_id in farmer_ids:
        try:
            _run(_send_farmer_nudge(user_id))
        except Exception:
            logger.exception("seasonal_farmer_check: failed for %s", user_id)

    logger.info("seasonal_farmer_check: sent to %d farmers", len(farmer_ids))
    return {"sent": len(farmer_ids)}
