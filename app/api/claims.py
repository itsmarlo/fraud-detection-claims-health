from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.models.health_claim_schema import HealthClaimInput, HealthFraudAssessment
from app.services.health_fraud_agent import HealthFraudDetectionAgent
from app.services.document_analyzer import DocumentAnalyzer

router = APIRouter(tags=["healthcare claims"])
agent = HealthFraudDetectionAgent()
document_analyzer = DocumentAnalyzer()


@router.post("/api/v1/healthcare-claims/assess", response_model=HealthFraudAssessment)
def assess_claim(claim: HealthClaimInput) -> HealthFraudAssessment:
    return agent.assess(claim)


@router.post(
    "/api/v1/healthcare-claims/assess-with-documents",
    response_model=HealthFraudAssessment,
)
async def assess_claim_with_documents(
    claim_json: str = Form(...),
    hospital_bill_file: UploadFile | None = File(None),
    discharge_summary_file: UploadFile | None = File(None),
    prescription_file: UploadFile | None = File(None),
    medical_report_file: UploadFile | None = File(None),
    lab_or_test_results_file: UploadFile | None = File(None),
) -> HealthFraudAssessment:
    """Assess a claim and inspect uploaded evidence without retaining source files."""
    try:
        claim = HealthClaimInput.model_validate_json(claim_json)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    analysis = await document_analyzer.analyze(
        claim,
        {
            "hospital_bill": hospital_bill_file,
            "discharge_summary": discharge_summary_file,
            "prescription": prescription_file,
            "medical_report": medical_report_file,
            "lab_or_test_results": lab_or_test_results_file,
        },
    )
    assessment = agent.assess(analysis.claim)
    confidence_penalty = min(len(analysis.warnings) * 5, 15)
    return assessment.model_copy(
        update={
            "confidence_score": max(40.0, assessment.confidence_score - confidence_penalty),
            "warnings": [*assessment.warnings, *analysis.warnings],
            "document_findings": analysis.findings,
        }
    )


@router.post(
    "/api/v1/claims/score",
    response_model=HealthFraudAssessment,
    include_in_schema=False,
    deprecated=True,
)
def score_claim_legacy(claim: HealthClaimInput) -> HealthFraudAssessment:
    """Compatibility route; new integrations should use the assessment endpoint."""
    return assess_claim(claim)
