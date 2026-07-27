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

    assert assessment.risk_tier == RiskLevel.LOW
    assert assessment.risk_score <= 30
    assert assessment.assessment_purpose == "HUMAN_REVIEW_DECISION_SUPPORT"


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
    assert assessment.risk_tier != RiskLevel.LOW
    assert all(reason.evidence_refs for reason in assessment.reasons)


def test_document_content_mismatches_are_explainable_risk_signals():
    claim = base_claim(
        documents=DocumentValidationInput(
            hospital_bill=True,
            document_amount_mismatch=True,
            document_identifier_mismatch=True,
        )
    )

    assessment = HealthFraudDetectionAgent().assess(claim)

    codes = {reason.code for reason in assessment.reasons}
    assert "DOCUMENT_AMOUNT_MISMATCH" in codes
    assert "DOCUMENT_IDENTIFIER_MISMATCH" in codes
    assert assessment.component_scores.document_validation == 100
    assert assessment.risk_tier != RiskLevel.LOW


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


def test_high_cost_or_service_type_is_not_a_risk_signal_by_itself():
    claim = base_claim(
        claim_type=ClaimType.HOSPITAL,
        cause_of_loss=CauseOfLoss.ELECTIVE_PROCEDURE,
        claim_amount=15000,
    )

    assessment = HealthFraudDetectionAgent().assess(claim)

    codes = {reason.code for reason in assessment.reasons}
    assert "HIGH_VALUE_HOSPITAL_CLAIM" not in codes
    assert "HIGH_RISK_CAUSE_OF_LOSS" not in codes


def test_missing_or_low_quality_evidence_lowers_confidence_not_risk():
    claim = base_claim(
        documents=DocumentValidationInput(hospital_bill=False, low_resolution_image=True)
    )

    assessment = HealthFraudDetectionAgent().assess(claim)

    assert assessment.component_scores.document_validation == 0
    assert assessment.confidence_score < 100
    assert assessment.warnings


def test_demographic_flag_is_not_used_as_a_fraud_signal():
    assessment = HealthFraudDetectionAgent().assess(base_claim(demographic_mismatch=True))

    assert "DEMOGRAPHIC_MISMATCH" not in {reason.code for reason in assessment.reasons}


def test_raw_provider_volume_requires_peer_context():
    raw_only = HealthFraudDetectionAgent().assess(base_claim(provider_claims_last_90_days=10000))
    peer_adjusted = HealthFraudDetectionAgent().assess(
        base_claim(provider_claims_last_90_days=10000, provider_peer_volume_percentile=99.5)
    )

    assert "PROVIDER_PEER_VOLUME_OUTLIER" not in {reason.code for reason in raw_only.reasons}
    assert "PROVIDER_PEER_VOLUME_OUTLIER" in {reason.code for reason in peer_adjusted.reasons}
