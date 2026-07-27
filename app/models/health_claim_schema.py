from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.risk import RiskLevel


class ClaimType(str, Enum):
    OUT_PATIENT = "OUT_PATIENT"
    IN_PATIENT = "IN_PATIENT"
    DENTAL = "DENTAL"
    HOSPITAL = "HOSPITAL"


class CauseOfLoss(str, Enum):
    EMERGENCY_TREATMENT = "EMERGENCY_TREATMENT"
    ELECTIVE_PROCEDURE = "ELECTIVE_PROCEDURE"
    CHRONIC_CONDITION = "CHRONIC_CONDITION"
    ACCIDENT_RELATED = "ACCIDENT_RELATED"
    DENTAL_TREATMENT = "DENTAL_TREATMENT"
    ROUTINE_CONSULTATION = "ROUTINE_CONSULTATION"
    PHARMACY = "PHARMACY"
    DIAGNOSTIC_TEST = "DIAGNOSTIC_TEST"
    OTHER = "OTHER"


class ReasonSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class DocumentValidationInput(BaseModel):
    hospital_bill: bool = False
    discharge_summary: bool = False
    prescription: bool = False
    medical_report: bool = False
    lab_or_test_results: bool = False
    prior_authorization: bool = False
    referral: bool = False
    low_resolution_image: bool = False
    duplicate_document_found: bool = False
    document_amount_mismatch: bool = False
    document_identifier_mismatch: bool = False
    doctor_name: str | None = None
    hospital_name: str | None = None
    invoice_number: str | None = None
    prescription_number: str | None = None
    medical_report_date: date | None = None
    treatment_date: date | None = None
    admission_date: date | None = None
    discharge_date: date | None = None


class HealthClaimInput(BaseModel):
    claim_id: str = Field(..., min_length=3)
    policy_id: str = Field(..., min_length=3)
    member_id: str = Field(..., min_length=3)
    claimant_id: str | None = None
    provider_id: str = Field(..., min_length=3)
    doctor_id: str | None = None
    facility_id: str | None = None

    claim_type: ClaimType
    cause_of_loss: CauseOfLoss = CauseOfLoss.OTHER
    claim_amount: float = Field(..., ge=0)
    billed_amount: float = Field(..., ge=0)
    allowed_amount: float = Field(..., ge=0)

    policy_start_date: date
    policy_end_date: date
    date_of_loss: date
    claim_submission_date: date
    coverage_upgrade_date: date | None = None
    beneficiary_added_date: date | None = None
    last_policy_modification_date: date | None = None

    previous_claims_last_12_months: int = Field(0, ge=0)
    active_policy_count: int = Field(1, ge=1)
    provider_claims_last_90_days: int = Field(0, ge=0)
    provider_peer_volume_percentile: float | None = Field(None, ge=0, le=100)
    provider_suspicious_claims_last_12_months: int = Field(0, ge=0)
    same_doctor_or_hospital_claims_last_12_months: int = Field(0, ge=0)

    patient_age: int | None = Field(None, ge=0, le=120)
    patient_gender: Literal["F", "M", "X", "UNKNOWN"] = "UNKNOWN"
    diagnosis_codes: list[str] = Field(default_factory=list)
    procedure_codes: list[str] = Field(default_factory=list)
    provider_specialty: str | None = None
    place_of_service: str | None = None

    treatment_before_policy_inception: bool = False
    demographic_mismatch: bool = Field(
        False,
        deprecated=True,
        description="Accepted for compatibility but deliberately excluded from risk scoring.",
    )
    diagnosis_procedure_mismatch: bool = False
    provider_specialty_mismatch: bool = False
    high_value_claim: bool = False
    newly_added_beneficiary: bool = False
    policy_modified_shortly_before_claim: bool = False

    documents: DocumentValidationInput = Field(default_factory=DocumentValidationInput)

    @field_validator("diagnosis_codes", "procedure_codes")
    @classmethod
    def normalize_codes(cls, value: list[str]) -> list[str]:
        return [item.strip().upper() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_dates(self) -> "HealthClaimInput":
        if self.policy_end_date < self.policy_start_date:
            raise ValueError("policy_end_date must be on or after policy_start_date")
        if self.claim_submission_date < self.date_of_loss:
            raise ValueError("claim_submission_date cannot be before date_of_loss")
        return self


class RiskReason(BaseModel):
    code: str
    message: str
    severity: ReasonSeverity
    points: float
    component: str
    evidence_refs: list[str] = Field(default_factory=list)


class ComponentScores(BaseModel):
    eligibility: float
    member_history: float
    incident_type: float
    document_validation: float
    provider_network: float
    policy_beneficiary: float


class ClaimWorkflowStep(BaseModel):
    name: str
    status: Literal["COMPLETED", "REVIEW_REQUIRED"]
    notes: str


class UploadedDocumentFinding(BaseModel):
    role: str
    filename: str
    media_type: str
    size_bytes: int
    fingerprint: str
    status: Literal["ANALYZED", "LIMITED_ANALYSIS"]
    extracted_dates: dict[str, date] = Field(default_factory=dict)
    extracted_amounts: list[float] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HealthFraudAssessment(BaseModel):
    claim_id: str
    schema_version: str
    assessment_purpose: Literal["HUMAN_REVIEW_DECISION_SUPPORT"]
    risk_score: float
    risk_tier: RiskLevel
    recommended_action: str
    confidence_score: float
    component_scores: ComponentScores
    reasons: list[RiskReason]
    warnings: list[str]
    document_findings: list[UploadedDocumentFinding] = Field(default_factory=list)
    workflow: list[ClaimWorkflowStep]
    rule_set_version: str
    model_version: str | None = None
