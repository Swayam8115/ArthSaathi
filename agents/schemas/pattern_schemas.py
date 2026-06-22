from pydantic import BaseModel


class SemanticRiskResponse(BaseModel):
    predatory_loan: bool
    distress_signal: bool
    reasoning: str      # internal only — never shown to the user
