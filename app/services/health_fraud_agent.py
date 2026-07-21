from datetime import date

from app.core.config import Settings, get_settings
from app.core.risk import RiskLevel, recommended_action_for_level, risk_level_for_score
from app.models.health_claim_schema import (
    CauseOfLoss,
    ClaimType,
    ClaimWorkflowStep,
    ComponentScores,
    HealthClaimInput,
    HealthFraudAssessment,
    ReasonSeverity,
    RiskReason,
)


class HealthFraudDetectionAgent:
    """Explainable rules service for healthcare FWA review prioritization."""

    EVIDENCE_REFS = {
        "TREATMENT_BEFORE_POLICY_INCEPTION": [
            "claim.date_of_loss",
            "claim.policy_start_date",
            "documents.treatment_date",
        ],
        "EARLY_CLAIM_AFTER_POLICY_START": ["claim.date_of_loss", "claim.policy_start_date"],
        "COVERAGE_INACTIVE_ON_SERVICE_DATE": ["claim.date_of_loss", "claim.policy_end_date"],
        "EXCESSIVE_CLAIM_FREQUENCY": ["claim.previous_claims_last_12_months"],
        "MULTIPLE_ACTIVE_POLICIES": ["claim.active_policy_count"],
        "DUPLICATE_HEALTH_DOCUMENT": ["documents.duplicate_document_found"],
        "DOCUMENT_DATE_MISMATCH": ["documents.medical_report_date", "documents.treatment_date"],
        "INVALID_ADMISSION_DISCHARGE_DATES": [
            "documents.admission_date",
            "documents.discharge_date",
        ],
        "SUSPICIOUS_HOSPITAL_DOCTOR_REPETITION": [
            "claim.same_doctor_or_hospital_claims_last_12_months"
        ],
        "HIGH_RISK_PROVIDER_HISTORY": ["claim.provider_suspicious_claims_last_12_months"],
        "PROVIDER_PEER_VOLUME_OUTLIER": [
            "claim.provider_claims_last_90_days",
            "claim.provider_peer_volume_percentile",
        ],
        "PROCEDURE_DIAGNOSIS_MISMATCH": ["claim.diagnosis_codes", "claim.procedure_codes"],
        "PROVIDER_SPECIALTY_MISMATCH": ["claim.provider_specialty", "claim.procedure_codes"],
        "CLAIM_AFTER_COVERAGE_UPGRADE": ["claim.coverage_upgrade_date", "claim.date_of_loss"],
        "NEW_BENEFICIARY_HIGH_VALUE_CLAIM": [
            "claim.beneficiary_added_date",
            "claim.claim_amount",
        ],
        "POLICY_MODIFIED_SHORTLY_BEFORE_CLAIM": [
            "claim.last_policy_modification_date",
            "claim.date_of_loss",
        ],
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def assess(self, claim: HealthClaimInput) -> HealthFraudAssessment:
        reasons: list[RiskReason] = []
        warnings: list[str] = []

        component_scores = ComponentScores(
            eligibility=self._eligibility_score(claim, reasons),
            member_history=self._member_history_score(claim, reasons),
            incident_type=self._incident_type_score(claim, reasons),
            document_validation=self._document_score(claim, reasons, warnings),
            provider_network=self._provider_network_score(claim, reasons),
            policy_beneficiary=self._policy_beneficiary_score(claim, reasons),
        )

        risk_score = self._weighted_total(component_scores)
        risk_level = risk_level_for_score(
            risk_score,
            routine_max=self.settings.routine_review_max_score,
            elevated_max=self.settings.elevated_review_max_score,
            high_max=self.settings.high_review_max_score,
        )

        return HealthFraudAssessment(
            claim_id=claim.claim_id,
            schema_version=self.settings.schema_version,
            assessment_purpose="HUMAN_REVIEW_DECISION_SUPPORT",
            risk_score=round(risk_score, 2),
            risk_tier=risk_level,
            recommended_action=recommended_action_for_level(risk_level),
            confidence_score=self._confidence_score(claim, warnings),
            component_scores=component_scores,
            reasons=sorted(reasons, key=lambda item: item.points, reverse=True),
            warnings=warnings,
            workflow=self._workflow(risk_level),
            rule_set_version=self.settings.rule_set_version,
            model_version=None,
        )

    def _eligibility_score(self, claim: HealthClaimInput, reasons: list[RiskReason]) -> float:
        score = 0.0
        days_since_start = (claim.date_of_loss - claim.policy_start_date).days

        if claim.date_of_loss < claim.policy_start_date or claim.treatment_before_policy_inception:
            score += 100
            self._add_reason(
                reasons,
                "TREATMENT_BEFORE_POLICY_INCEPTION",
                "Treatment date is before policy inception.",
                RiskLevel.VERY_HIGH,
                100,
                "eligibility",
            )
        elif days_since_start < 30:
            score += 85
            self._add_reason(
                reasons,
                "EARLY_CLAIM_AFTER_POLICY_START",
                "Date of loss is less than 30 days after policy start.",
                RiskLevel.HIGH,
                85,
                "eligibility",
            )
        elif days_since_start <= 90:
            score += 50
            self._add_reason(
                reasons,
                "EARLY_CLAIM_AFTER_POLICY_START",
                "Date of loss is 30-90 days after policy start.",
                RiskLevel.MEDIUM,
                50,
                "eligibility",
            )

        if claim.date_of_loss > claim.policy_end_date:
            score += 100
            self._add_reason(
                reasons,
                "COVERAGE_INACTIVE_ON_SERVICE_DATE",
                "Date of loss is after policy end date.",
                RiskLevel.VERY_HIGH,
                100,
                "eligibility",
            )

        return min(score, 100)

    def _member_history_score(self, claim: HealthClaimInput, reasons: list[RiskReason]) -> float:
        score = 0.0
        previous_claims = claim.previous_claims_last_12_months

        if previous_claims > 3:
            score += 80
            self._add_reason(
                reasons,
                "EXCESSIVE_CLAIM_FREQUENCY",
                "Policyholder has more than 3 claims in the last 12 months.",
                RiskLevel.HIGH,
                80,
                "member_history",
            )
        elif previous_claims >= 2:
            score += 45
            self._add_reason(
                reasons,
                "EXCESSIVE_CLAIM_FREQUENCY",
                "Policyholder has 2-3 claims in the last 12 months.",
                RiskLevel.MEDIUM,
                45,
                "member_history",
            )

        if claim.active_policy_count > 1:
            points = min(20 + claim.active_policy_count * 10, 70)
            score += points
            self._add_reason(
                reasons,
                "MULTIPLE_ACTIVE_POLICIES",
                "Member has multiple active policies.",
                RiskLevel.MEDIUM if points < 60 else RiskLevel.HIGH,
                points,
                "member_history",
            )

        return min(score, 100)

    def _incident_type_score(self, claim: HealthClaimInput, reasons: list[RiskReason]) -> float:
        # A service type or high amount is not suspicious by itself. This component
        # stays neutral until clinically reviewed, effective-dated edits are added.
        return 0.0

    def _document_score(
        self,
        claim: HealthClaimInput,
        reasons: list[RiskReason],
        warnings: list[str],
    ) -> float:
        score = 0.0
        documents = claim.documents

        required_missing = []
        if not documents.hospital_bill:
            required_missing.append("hospital bill")
        if claim.claim_type in {ClaimType.IN_PATIENT, ClaimType.HOSPITAL} and not documents.discharge_summary:
            required_missing.append("discharge summary")
        if claim.cause_of_loss == CauseOfLoss.PHARMACY and not documents.prescription:
            required_missing.append("prescription")
        if claim.high_value_claim and not documents.medical_report:
            required_missing.append("medical report")
        if claim.cause_of_loss in {CauseOfLoss.ELECTIVE_PROCEDURE, CauseOfLoss.DIAGNOSTIC_TEST} and not documents.lab_or_test_results:
            required_missing.append("reports/test results")

        if required_missing:
            warnings.append(f"Missing supporting documents: {', '.join(required_missing)}.")

        if documents.low_resolution_image:
            warnings.append("At least one uploaded evidence image is low resolution.")

        if documents.duplicate_document_found:
            score += 80
            self._add_reason(
                reasons,
                "DUPLICATE_HEALTH_DOCUMENT",
                "Duplicate invoice, prescription, or medical document was detected.",
                RiskLevel.HIGH,
                80,
                "document_validation",
            )

        score += self._date_mismatch_score(claim, reasons)
        return min(score, 100)

    def _date_mismatch_score(self, claim: HealthClaimInput, reasons: list[RiskReason]) -> float:
        documents = claim.documents
        score = 0.0

        if documents.medical_report_date and documents.treatment_date:
            if documents.medical_report_date != documents.treatment_date:
                score += 35
                self._add_reason(
                    reasons,
                    "DOCUMENT_DATE_MISMATCH",
                    "Medical report date does not match treatment date.",
                    RiskLevel.MEDIUM,
                    35,
                    "document_validation",
                )

        if documents.admission_date and documents.discharge_date:
            if documents.admission_date > documents.discharge_date:
                score += 90
                self._add_reason(
                    reasons,
                    "INVALID_ADMISSION_DISCHARGE_DATES",
                    "Admission date is after discharge date.",
                    RiskLevel.VERY_HIGH,
                    90,
                    "document_validation",
                )

        if documents.treatment_date and documents.treatment_date < claim.policy_start_date:
            score += 100
            self._add_reason(
                reasons,
                "TREATMENT_BEFORE_POLICY_INCEPTION",
                "Documented treatment date is before policy inception.",
                RiskLevel.VERY_HIGH,
                100,
                "document_validation",
            )

        return min(score, 100)

    def _provider_network_score(self, claim: HealthClaimInput, reasons: list[RiskReason]) -> float:
        score = 0.0

        if claim.same_doctor_or_hospital_claims_last_12_months >= 8:
            score += 75
            self._add_reason(
                reasons,
                "SUSPICIOUS_HOSPITAL_DOCTOR_REPETITION",
                "Unusually high claims from the same doctor or hospital.",
                RiskLevel.HIGH,
                75,
                "provider_network",
            )
        elif claim.same_doctor_or_hospital_claims_last_12_months >= 4:
            score += 45
            self._add_reason(
                reasons,
                "SUSPICIOUS_HOSPITAL_DOCTOR_REPETITION",
                "Repeated claims from the same doctor or hospital.",
                RiskLevel.MEDIUM,
                45,
                "provider_network",
            )

        if claim.provider_suspicious_claims_last_12_months > 3:
            score += 80
            self._add_reason(
                reasons,
                "HIGH_RISK_PROVIDER_HISTORY",
                "Provider has more than 3 suspicious claims in the last 12 months.",
                RiskLevel.HIGH,
                80,
                "provider_network",
            )

        if (
            claim.provider_peer_volume_percentile is not None
            and claim.provider_peer_volume_percentile >= 99
        ):
            score += 35
            self._add_reason(
                reasons,
                "PROVIDER_PEER_VOLUME_OUTLIER",
                "Provider volume is at or above the 99th percentile of its supplied peer group.",
                RiskLevel.MEDIUM,
                35,
                "provider_network",
            )

        if claim.diagnosis_procedure_mismatch:
            score += 70
            self._add_reason(
                reasons,
                "PROCEDURE_DIAGNOSIS_MISMATCH",
                "Procedure is inconsistent with the supplied diagnosis.",
                RiskLevel.HIGH,
                70,
                "provider_network",
            )

        if claim.provider_specialty_mismatch:
            score += 50
            self._add_reason(
                reasons,
                "PROVIDER_SPECIALTY_MISMATCH",
                "Provider specialty is inconsistent with billed procedure.",
                RiskLevel.MEDIUM,
                50,
                "provider_network",
            )

        return min(score, 100)

    def _policy_beneficiary_score(self, claim: HealthClaimInput, reasons: list[RiskReason]) -> float:
        score = 0.0
        if self._recent_before_claim(claim.coverage_upgrade_date, claim.date_of_loss, 30):
            score += 70
            self._add_reason(
                reasons,
                "CLAIM_AFTER_COVERAGE_UPGRADE",
                "Claim occurred within 30 days of a coverage upgrade.",
                RiskLevel.HIGH,
                70,
                "policy_beneficiary",
            )

        beneficiary_recent = claim.newly_added_beneficiary or self._recent_before_claim(
            claim.beneficiary_added_date, claim.date_of_loss, 30
        )
        if beneficiary_recent and claim.claim_amount >= self.settings.high_value_beneficiary_threshold:
            score += 75
            self._add_reason(
                reasons,
                "NEW_BENEFICIARY_HIGH_VALUE_CLAIM",
                "Newly added beneficiary has an immediate high-value claim.",
                RiskLevel.HIGH,
                75,
                "policy_beneficiary",
            )

        modified_recently = claim.policy_modified_shortly_before_claim or self._recent_before_claim(
            claim.last_policy_modification_date, claim.date_of_loss, 30
        )
        if modified_recently:
            score += 45
            self._add_reason(
                reasons,
                "POLICY_MODIFIED_SHORTLY_BEFORE_CLAIM",
                "Policy was modified shortly before the claim.",
                RiskLevel.MEDIUM,
                45,
                "policy_beneficiary",
            )

        return min(score, 100)

    def _weighted_total(self, scores: ComponentScores) -> float:
        total = 0.0
        for component, weight in self.settings.component_weights.items():
            total += getattr(scores, component) * weight
        return max(0.0, min(total, 100.0))

    def _confidence_score(self, claim: HealthClaimInput, warnings: list[str]) -> float:
        confidence = 100.0
        documents = claim.documents
        if not documents.hospital_bill:
            confidence -= 12
        if claim.claim_type in {ClaimType.IN_PATIENT, ClaimType.HOSPITAL} and not documents.discharge_summary:
            confidence -= 10
        if not claim.diagnosis_codes:
            confidence -= 8
        if not claim.procedure_codes:
            confidence -= 8
        confidence -= min(len(warnings) * 5, 15)
        return round(max(confidence, 40.0), 2)

    def _workflow(self, risk_level: RiskLevel) -> list[ClaimWorkflowStep]:
        status = "COMPLETED" if risk_level == RiskLevel.LOW else "REVIEW_REQUIRED"
        return [
            ClaimWorkflowStep(
                name="Search Member",
                status="COMPLETED",
                notes="Member and benefit-plan context accepted for scoring.",
            ),
            ClaimWorkflowStep(
                name="Validate Policy Eligibility",
                status=status,
                notes="Coverage dates, policy changes, and beneficiary timing evaluated.",
            ),
            ClaimWorkflowStep(
                name="Capture Medical Details",
                status="COMPLETED",
                notes="Claim type, cause of loss, diagnosis, procedure, and provider details processed.",
            ),
            ClaimWorkflowStep(
                name="Collect Required Documents",
                status=status,
                notes="Required health documents and document-date consistency evaluated.",
            ),
            ClaimWorkflowStep(
                name="Coverage & FWA Risk Assessment",
                status=status,
                notes="Rules combined into an explainable review-priority score.",
            ),
            ClaimWorkflowStep(
                name="Provide Next Actions",
                status=status,
                notes=recommended_action_for_level(risk_level),
            ),
        ]

    def _recent_before_claim(self, event_date: date | None, claim_date: date, days: int) -> bool:
        if not event_date:
            return False
        delta = (claim_date - event_date).days
        return 0 <= delta <= days

    def _add_reason(
        self,
        reasons: list[RiskReason],
        code: str,
        message: str,
        severity: RiskLevel,
        points: float,
        component: str,
        evidence_refs: list[str] | None = None,
    ) -> None:
        reasons.append(
            RiskReason(
                code=code,
                message=message,
                severity=ReasonSeverity[severity.name],
                points=round(points, 2),
                component=component,
                evidence_refs=evidence_refs or self.EVIDENCE_REFS.get(code, []),
            )
        )
