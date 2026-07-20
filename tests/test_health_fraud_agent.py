from datetime import date

from app.core.risk import RiskLevel
from app.models.health_claim_schema import (
    CauseOfLoss,
    ClaimType,
    DocumentValidationInput,
    HealthClaimInput,
)
from app.services.health_fraud_agent import HealthFraudDetectionAgent


def base_claim(**overrides):
    payload = {
        "claim_id": "CLM-1",
        "policy_id": "POL-1",
        "member_id": "MBR-1",
        "provider_id": "NPI-1",
        "claim_type": ClaimType.OUT_PATIENT,
        "cause_of_loss": CauseOfLoss.ROUTINE_CONSULTATION,
        "claim_amount": 250.0,
        "billed_amount": 300.0,
        "allowed_amount": 200.0,
        "policy_start_date": date(2026, 1, 1),
        "policy_end_date": date(2026, 12, 31),
        "date_of_loss": date(2026, 5, 1),
        "claim_submission_date": date(2026, 5, 3),
        "diagnosis_codes": ["Z00.0"],
        "procedure_codes": ["99213"],
        "documents": DocumentValidationInput(hospital_bill=True),
    }
    payload.update(overrides)
    return HealthClaimInput(**payload)


def test_low_risk_claim_scores_low():
    assessment = HealthFraudDetectionAgent().assess(base_claim())

    assert assessment.risk_level == RiskLevel.LOW
    assert assessment.fraud_score <= 30


def test_early_claim_under_30_days_is_high_eligibility_signal():
    claim = base_claim(date_of_loss=date(2026, 1, 15), claim_submission_date=date(2026, 1, 16))
    assessment = HealthFraudDetectionAgent().assess(claim)

    assert assessment.component_scores.eligibility >= 80
    assert "EARLY_CLAIM_AFTER_POLICY_START" in {reason.code for reason in assessment.reasons}


def test_frequent_claims_rule_thresholds():
    claim = base_claim(previous_claims_last_12_months=4)
    assessment = HealthFraudDetectionAgent().assess(claim)

    assert assessment.component_scores.member_history >= 80
    assert "EXCESSIVE_CLAIM_FREQUENCY" in {reason.code for reason in assessment.reasons}


def test_document_validation_detects_duplicates_and_invalid_dates():
    claim = base_claim(
        documents=DocumentValidationInput(
            hospital_bill=True,
            duplicate_document_found=True,
            admission_date=date(2026, 4, 5),
            discharge_date=date(2026, 4, 1),
        )
    )
    assessment = HealthFraudDetectionAgent().assess(claim)

    codes = {reason.code for reason in assessment.reasons}
    assert "DUPLICATE_HEALTH_DOCUMENT" in codes
    assert "INVALID_ADMISSION_DISCHARGE_DATES" in codes
    assert assessment.component_scores.document_validation == 100


def test_policy_and_beneficiary_risk_rules():
    claim = base_claim(
        claim_amount=4000,
        coverage_upgrade_date=date(2026, 4, 20),
        beneficiary_added_date=date(2026, 4, 25),
    )
    assessment = HealthFraudDetectionAgent().assess(claim)

    codes = {reason.code for reason in assessment.reasons}
    assert "CLAIM_AFTER_COVERAGE_UPGRADE" in codes
    assert "NEW_BENEFICIARY_HIGH_VALUE_CLAIM" in codes
    assert assessment.component_scores.policy_beneficiary == 100
