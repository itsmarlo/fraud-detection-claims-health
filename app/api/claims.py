from fastapi import APIRouter

from app.models.health_claim_schema import HealthClaimInput, HealthFraudAssessment
from app.services.health_fraud_agent import HealthFraudDetectionAgent

router = APIRouter(tags=["healthcare claims"])
agent = HealthFraudDetectionAgent()


@router.post("/api/v1/healthcare-claims/assess", response_model=HealthFraudAssessment)
def assess_claim(claim: HealthClaimInput) -> HealthFraudAssessment:
    return agent.assess(claim)


@router.post(
    "/api/v1/claims/score",
    response_model=HealthFraudAssessment,
    include_in_schema=False,
    deprecated=True,
)
def score_claim_legacy(claim: HealthClaimInput) -> HealthFraudAssessment:
    """Compatibility route; new integrations should use the assessment endpoint."""
    return assess_claim(claim)
