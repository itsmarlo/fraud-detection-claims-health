from enum import Enum


class RiskLevel(str, Enum):
    LOW = "ROUTINE_REVIEW_PRIORITY"
    MEDIUM = "ELEVATED_REVIEW_PRIORITY"
    HIGH = "HIGH_REVIEW_PRIORITY"
    VERY_HIGH = "URGENT_REVIEW_PRIORITY"


def risk_level_for_score(
    score: float,
    routine_max: float = 30,
    elevated_max: float = 60,
    high_max: float = 80,
) -> RiskLevel:
    if score <= routine_max:
        return RiskLevel.LOW
    if score <= elevated_max:
        return RiskLevel.MEDIUM
    if score <= high_max:
        return RiskLevel.HIGH
    return RiskLevel.VERY_HIGH


def recommended_action_for_level(level: RiskLevel) -> str:
    actions = {
        RiskLevel.LOW: "Continue standard processing and routine controls.",
        RiskLevel.MEDIUM: "Route to a payment-integrity analyst for review.",
        RiskLevel.HIGH: "Prioritize for payment-integrity review and gather supporting evidence.",
        RiskLevel.VERY_HIGH: (
            "Prioritize for SIU/compliance review; do not take adverse action without a human determination."
        ),
    }
    return actions[level]
