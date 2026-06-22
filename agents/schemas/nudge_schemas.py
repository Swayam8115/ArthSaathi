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
    is_query: bool      # True when the message is a direct financial question
    reasoning: str      # internal only — never shown to the user
