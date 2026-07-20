from fastapi import APIRouter

from app.models.health_claim_schema import HealthClaimInput, HealthFraudAssessment
from app.services.health_fraud_agent import HealthFraudDetectionAgent

router = APIRouter(prefix="/api/v1/claims", tags=["claims"])
agent = HealthFraudDetectionAgent()


@router.post("/score", response_model=HealthFraudAssessment)
def score_claim(claim: HealthClaimInput) -> HealthFraudAssessment:
    return agent.assess(claim)
