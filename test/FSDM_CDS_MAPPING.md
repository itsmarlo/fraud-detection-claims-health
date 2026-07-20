# FSDM CDS view mapping

`ZI_FSDM_HEALTH_CLAIM_FRAUD.ddls.asddls` is an ABAP CDS view entity for health-claim fraud analysis.

Before activation, replace `zfsdm_hlth_clm` and its field names with the physical FSDM entity or source-system table used in your installation. FSDM physical names vary with the product release, deployed content, and customer extensions.

The expected source fields are:

| Area | Expected fields |
|---|---|
| Keys | `claim_uuid`, `claim_id`, `policy_id`, `business_partner_id`, `provider_id` |
| Claim | `claim_type`, `claim_status`, diagnosis/procedure codes, loss/submission/service dates |
| Amount | claimed, approved, and paid amounts plus currency code |
| Fraud | fraud score, triggered rule, case status, and manual-review indicator |
| Audit | source system, created/changed user and timestamps, deletion indicator |

The fraud score is assumed to be a decimal value from `0.00` to `1.00`. The derived risk levels are low below `0.50`, medium from `0.50` to below `0.80`, and high from `0.80`.

An authorization object is expected because the view uses `@AccessControl.authorizationCheck: #CHECK`. Add a matching DCL role before exposing the view through a service.
