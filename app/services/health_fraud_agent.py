from datetime import date

from app.core.risk import RiskLevel, recommended_action_for_level, risk_level_for_score
from app.models.health_claim_schema import (
    CauseOfLoss,
    ClaimType,
    ClaimWorkflowStep,
    ComponentScores,
    HealthClaimInput,
    HealthFraudAssessment,
    RiskReason,
)


class HealthFraudDetectionAgent:
    """Explainable rules agent for health claim fraud assessment."""

    COMPONENT_WEIGHTS = {
        "eligibility": 0.20,
        "member_history": 0.18,
        "incident_type": 0.12,
        "document_validation": 0.25,
        "provider_network": 0.15,
        "policy_beneficiary": 0.10,
    }

    HIGH_RISK_CAUSES = {
        CauseOfLoss.ELECTIVE_PROCEDURE,
        CauseOfLoss.DENTAL_TREATMENT,
        CauseOfLoss.PHARMACY,
    }

    MEDIUM_RISK_CAUSES = {
        CauseOfLoss.DIAGNOSTIC_TEST,
        CauseOfLoss.CHRONIC_CONDITION,
        CauseOfLoss.ROUTINE_CONSULTATION,
    }

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

        fraud_score = self._weighted_total(component_scores)
        risk_level = risk_level_for_score(fraud_score)

        return HealthFraudAssessment(
            claim_id=claim.claim_id,
            fraud_score=round(fraud_score, 2),
            risk_level=risk_level,
            recommended_action=recommended_action_for_level(risk_level),
            confidence_score=self._confidence_score(claim, warnings),
            component_scores=component_scores,
            reasons=sorted(reasons, key=lambda item: item.points, reverse=True),
            warnings=warnings,
            workflow=self._workflow(risk_level),
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
        score = 0.0
        if claim.cause_of_loss in self.HIGH_RISK_CAUSES:
            score += 70
            self._add_reason(
                reasons,
                "HIGH_RISK_CAUSE_OF_LOSS",
                f"{claim.cause_of_loss.value} is configured as a high-risk health claim cause.",
                RiskLevel.HIGH,
                70,
                "incident_type",
            )
        elif claim.cause_of_loss in self.MEDIUM_RISK_CAUSES:
            score += 35
            self._add_reason(
                reasons,
                "MEDIUM_RISK_CAUSE_OF_LOSS",
                f"{claim.cause_of_loss.value} is configured as a medium-risk health claim cause.",
                RiskLevel.MEDIUM,
                35,
                "incident_type",
            )

        if claim.claim_type in {ClaimType.IN_PATIENT, ClaimType.HOSPITAL} and claim.claim_amount >= 5000:
            score += 20
            self._add_reason(
                reasons,
                "HIGH_VALUE_HOSPITAL_CLAIM",
                "Hospital or inpatient claim has a high claimed amount.",
                RiskLevel.MEDIUM,
                20,
                "incident_type",
            )

        return min(score, 100)

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
            points = min(25 + len(required_missing) * 15, 85)
            score += points
            self._add_reason(
                reasons,
                "MISSING_SUPPORTING_DOCUMENTS",
                f"Missing required supporting documents: {', '.join(required_missing)}.",
                RiskLevel.MEDIUM if points < 60 else RiskLevel.HIGH,
                points,
                "document_validation",
            )

        if documents.low_resolution_image:
            score += 30
            warnings.append("At least one uploaded evidence image is low resolution.")
            self._add_reason(
                reasons,
                "LOW_RESOLUTION_EVIDENCE",
                "Evidence contains a low-resolution image.",
                RiskLevel.MEDIUM,
                30,
                "document_validation",
            )

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

        if claim.provider_claims_last_90_days > 50:
            score += 35
            self._add_reason(
                reasons,
                "PROVIDER_CLAIM_VOLUME_SPIKE",
                "Provider claim volume is unusually high in the last 90 days.",
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

        if claim.demographic_mismatch:
            score += 60
            self._add_reason(
                reasons,
                "DEMOGRAPHIC_MISMATCH",
                "Patient demographics are inconsistent with claimed treatment.",
                RiskLevel.HIGH,
                60,
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
        if beneficiary_recent and claim.claim_amount >= 3000:
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
        for component, weight in self.COMPONENT_WEIGHTS.items():
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
        if risk_level == RiskLevel.VERY_HIGH:
            status = "BLOCKED"
        return [
            ClaimWorkflowStep(
                name="Search Policyholder",
                status="COMPLETED",
                notes="Policyholder and policy context accepted for scoring.",
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
                name="Coverage & Fraud Validation",
                status=status,
                notes="Rules fused into final explainable fraud score.",
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
    ) -> None:
        reasons.append(
            RiskReason(
                code=code,
                message=message,
                severity=severity,
                points=round(points, 2),
                component=component,
            )
        )
