from typing import Literal
from pydantic import BaseModel


class ExtractedEvent(BaseModel):
    event_type: Literal["income", "expense", "loan", "savings", "query"]
    amount: float | None
    description: str


class ExtractedEventsResponse(BaseModel):
    events: list[ExtractedEvent]


class PersonaResponse(BaseModel):
    persona_type: Literal["salaried", "gig", "farmer", "freelancer"] | None


class CombinedProfileResponse(BaseModel):
    events: list[ExtractedEvent]
    persona_type: Literal["salaried", "gig", "farmer", "freelancer"] | None
