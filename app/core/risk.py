from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


def risk_level_for_score(score: float) -> RiskLevel:
    if score <= 30:
        return RiskLevel.LOW
    if score <= 60:
        return RiskLevel.MEDIUM
    if score <= 80:
        return RiskLevel.HIGH
    return RiskLevel.VERY_HIGH


def recommended_action_for_level(level: RiskLevel) -> str:
    actions = {
        RiskLevel.LOW: "Auto-adjudicate or continue normal payment workflow.",
        RiskLevel.MEDIUM: "Pend for claims analyst review.",
        RiskLevel.HIGH: "Request medical records or provider clarification before payment.",
        RiskLevel.VERY_HIGH: "Suspend payment and refer to SIU/compliance.",
    }
    return actions[level]
