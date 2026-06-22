from typing import Literal
from pydantic import BaseModel


class NudgeDecisionResponse(BaseModel):
    should_nudge: bool
    nudge_type: Literal[
        "savings_nudge",
        "loan_warning",
        "scheme_alert",
        "investment_nudge",
        "tax_saving_nudge",
    ] | None
    is_query: bool
    reasoning: str


class CombinedNudgeResponse(BaseModel):
    should_nudge: bool
    nudge_type: Literal[
        "savings_nudge",
        "loan_warning",
        "scheme_alert",
        "investment_nudge",
        "tax_saving_nudge",
    ] | None
    is_query: bool
    nudge_content: str | None
    seekho_content: str | None
    query_answer: str | None
