from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import FinancialEvent, UserProfile
from pydantic import BaseModel, Field


class LoanRecord(BaseModel):
    """Schema for a single loan entry stored in user_profiles.loans (JSONB)."""

    source: str
    amount: float
    monthly_emi: float | None = None
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FinancialEventCreate(BaseModel):
    """Input schema for creating a FinancialEvent row."""

    user_id: str
    event_type: str  # income | expense | loan | savings | query
    amount: float | None = None
    description: str | None = None
    raw_message: str | None = None


class ProfileUpdate(BaseModel):
    """Fields that agents are allowed to update on a UserProfile."""

    language: str | None = None
    persona_type: str | None = None
    monthly_income: float | None = None
    monthly_expense: float | None = None
    savings: float | None = None
    loans: list[LoanRecord] | None = None
    last_nudge_at: datetime | None = None
    seekho_level: int | None = None


# CRUD 


async def get_profile(session: AsyncSession, user_id: str) -> UserProfile | None:
    """Fetch a user's financial profile. Returns None if not found."""
    result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_profile(session: AsyncSession, user_id: str, language: str = "hi") -> UserProfile:
    """
    Create a new UserProfile with sensible defaults.
    Called the first time a user messages ArthSaathi.
    """
    profile = UserProfile(user_id=user_id, language=language)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def get_or_create_profile(
    session: AsyncSession, user_id: str, language: str = "hi"
) -> UserProfile:
    """Return existing profile or create a fresh one."""
    profile = await get_profile(session, user_id)
    if profile is None:
        profile = await create_profile(session, user_id, language)
    return profile


async def update_profile(
    session: AsyncSession, user_id: str, updates: ProfileUpdate
) -> UserProfile:
    """
    Apply a partial update to a UserProfile.
    Only fields explicitly set in `updates` are written.
    """
    profile = await get_or_create_profile(session, user_id)

    for field, value in updates.model_dump(exclude_none=True).items():
        if field == "loans" and value is not None:
            # Convert list of LoanRecord → list of dicts for JSONB storage
            setattr(profile, field, [lr if isinstance(lr, dict) else lr.model_dump() for lr in value])
        else:
            setattr(profile, field, value)

    await session.commit()
    await session.refresh(profile)
    return profile


async def append_financial_event(
    session: AsyncSession, event_data: FinancialEventCreate
) -> FinancialEvent:
    """
    Record a financial event extracted from a user's message.

    Events are immutable once written — they form an audit trail.
    """
    event = FinancialEvent(**event_data.model_dump())
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def get_recent_events(
    session: AsyncSession, user_id: str, limit: int = 20
) -> list[FinancialEvent]:
    """Fetch the most recent financial events for a user (newest first)."""
    result = await session.execute(
        select(FinancialEvent)
        .where(FinancialEvent.user_id == user_id)
        .order_by(FinancialEvent.occurred_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def delete_profile(session: AsyncSession, user_id: str) -> bool:
    """
    Permanently delete a user's profile and all related events.
    Cascade delete handles financial_events rows automatically.
    Required by responsible-AI rule: user owns all data.
    Returns True if a profile was found and deleted, False otherwise.
    """
    profile = await get_profile(session, user_id)
    if profile is None:
        return False
    await session.delete(profile)
    await session.commit()
    return True
