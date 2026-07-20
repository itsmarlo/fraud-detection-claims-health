@AbapCatalog.viewEnhancementCategory: [#PROJECTION_LIST]
@AccessControl.authorizationCheck: #CHECK
@EndUserText.label: 'FSDM Health Claim Fraud Analysis'
@Metadata.allowExtensions: true
@ObjectModel.usageType: {
    serviceQuality: #X,
    sizeCategory: #L,
    dataClass: #MIXED
}
define view entity ZI_FSDM_HealthClaimFraud
  as select from zfsdm_hlth_clm as Claim
{
  /* Business keys */
  key Claim.claim_uuid                       as ClaimUUID,
      Claim.claim_id                         as ClaimID,
      Claim.policy_id                        as PolicyID,
      Claim.business_partner_id              as BusinessPartnerID,
      Claim.provider_id                      as ProviderID,

  /* Claim information */
      Claim.claim_type                       as ClaimType,
      Claim.claim_status                     as ClaimStatus,
      Claim.diagnosis_code                   as DiagnosisCode,
      Claim.procedure_code                   as ProcedureCode,
      Claim.loss_date                        as LossDate,
      Claim.submission_date                  as SubmissionDate,
      Claim.service_from_date                as ServiceFromDate,
      Claim.service_to_date                  as ServiceToDate,

  /* Amounts */
      @Semantics.amount.currencyCode: 'Currency'
      Claim.claimed_amount                   as ClaimedAmount,

      @Semantics.amount.currencyCode: 'Currency'
      Claim.approved_amount                  as ApprovedAmount,

      @Semantics.amount.currencyCode: 'Currency'
      Claim.paid_amount                      as PaidAmount,

      @Semantics.currencyCode: true
      Claim.currency_code                    as Currency,

  /* Fraud assessment */
      Claim.fraud_score                      as FraudScore,
      Claim.fraud_rule_code                  as FraudRuleCode,
      Claim.fraud_case_status                as FraudCaseStatus,
      Claim.manual_review_required           as ManualReviewRequired,

      cast(
        case
          when Claim.fraud_score >= 0.80 then 'HIGH'
          when Claim.fraud_score >= 0.50 then 'MEDIUM'
          else                                  'LOW'
        end
        as abap.char( 6 )
      )                                       as FraudRiskLevel,

      cast(
        case
          when Claim.claimed_amount > 0
            then ( Claim.claimed_amount - Claim.approved_amount )
                 / Claim.claimed_amount * 100
          else 0
        end
        as abap.dec( 7, 2 )
      )                                       as ReductionPercentage,

  /* Audit fields */
      Claim.source_system                    as SourceSystem,
      Claim.created_by                       as CreatedBy,
      Claim.created_at                       as CreatedAt,
      Claim.changed_by                       as ChangedBy,
      Claim.changed_at                       as ChangedAt
}
where Claim.is_deleted = abap_false

