"""
SQLAlchemy 2.x async ORM models mirroring the Supabase schema.

Tables:
  - UserProfile       → user_profiles
  - FinancialEvent    → financial_events

ProfileEmbedding is handled via raw Supabase RPC (pgvector) rather than ORM
because SQLAlchemy does not natively support the `vector` column type without
the pgvector-sqlalchemy extension.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    """Stores the aggregated financial profile for each WhatsApp user."""

    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="hi")
    persona_type: Mapped[str | None] = mapped_column(
        String(20),
        CheckConstraint(
            "persona_type IN ('salaried', 'gig', 'farmer', 'freelancer')",
            name="chk_persona_type",
        ),
        nullable=True,
    )
    monthly_income: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    monthly_expense: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    savings: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    loans: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    last_nudge_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    seekho_level: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    events: Mapped[list["FinancialEvent"]] = relationship(
        "FinancialEvent", back_populates="profile", cascade="all, delete-orphan"
    )


class FinancialEvent(Base):
    """Individual financial events extracted from user messages."""

    __tablename__ = "financial_events"

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('income', 'expense', 'loan', 'savings', 'query')",
            name="chk_event_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped["UserProfile"] = relationship("UserProfile", back_populates="events")
