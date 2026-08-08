from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ComplianceConclusion(BaseModel):
    conclusion: str = Field(..., min_length=1, max_length=500)
    risk_level: Literal["低", "中", "高"]
    clause_refs: list[str] = Field(..., min_length=1)
    evidence_quotes: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("clause_refs")
    @classmethod
    def clause_refs_must_be_non_empty(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("至少提供一条有效条款编号")
        return cleaned

    @model_validator(mode="after")
    def high_risk_should_not_be_overconfident(self) -> "ComplianceConclusion":
        if self.risk_level == "高" and self.confidence > 0.95:
            raise ValueError("高风险结论的置信度不应超过 0.95")
        return self
