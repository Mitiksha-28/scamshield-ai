import operator
from typing import Annotated, Literal, TypedDict
from pydantic import BaseModel, Field

AGENTS = ["web_detective", "reputation", "price_market"]
MAX_LOOPS = 2  # max re-verification rounds


class Evidence(BaseModel):
    agent: str
    finding: str
    signal: Literal["risk", "trust"]
    severity: float = Field(ge=0, le=1)      # how strong/impactful the finding is
    confidence: float = Field(ge=0, le=1)    # how sure the agent is
    source: str = "n/a"
    source_reliability: float = Field(default=0.5, ge=0, le=1)
    pass_no: int = 1                         # 1 = first investigation, 2+ = re-verification

    @property
    def weight(self) -> float:
        return self.severity * self.confidence * self.source_reliability


class ConflictResolution(BaseModel):
    conflict: str
    resolution: str


class FinalReport(BaseModel):
    trust_score: int = Field(ge=0, le=100)
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "INCONCLUSIVE"]
    summary: str
    recommended_action: str
    evidence: list[Evidence]
    conflicts_resolved: list[ConflictResolution]
    limitations: list[str]
    risk_weight: float
    trust_weight: float


class ScamState(TypedDict, total=False):
    run_id: str
    input: dict
    evidence: Annotated[list, operator.add]     # blackboard: all agents append here
    unavailable: Annotated[list, operator.add]  # [{"agent","reason"}] failed tools
    conflicts: Annotated[list, operator.add]    # [{"round","text"}]
    requests: dict                              # agent -> re-verification question
    loop_count: int
    final: dict