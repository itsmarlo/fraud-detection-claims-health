# Health Fraud Detection Agent

This repository contains an explainable FastAPI prototype for health insurance claim fraud detection. It implements deterministic fraud indicators for health claims and returns a final score, risk level, component scores, reasons, warnings, confidence, workflow status, and recommended next actions.

## Claim Flow

```text
Customer Requests Claim Creation
  -> Search Policyholder
  -> Select Policy
  -> Validate Policy Eligibility
  -> Select Claim Type
  -> Capture Medical Details
  -> Collect Required Documents
  -> Coverage & Fraud Validation
  -> Review Claim Summary
  -> Create Claim
  -> Generate Claim Number
  -> Provide Next Actions
```

## Implemented Fraud Indicators

- Early claim after policy purchase:
  - `< 30 days`: high risk
  - `30-90 days`: medium risk
  - `> 90 days`: low risk
- Frequent claims by same policyholder:
  - `0-1 claims`: low risk
  - `2-3 claims`: medium risk
  - `> 3 claims`: high risk
- High-risk cause-of-loss and claim-type scoring.
- Duplicate health documents and reused invoices/prescriptions.
- Document date mismatch:
  - Medical report date not equal to treatment date.
  - Admission date after discharge date.
  - Treatment before policy inception.
- Missing supporting documents:
  - Hospital bill.
  - Discharge summary.
  - Prescription.
  - Medical report.
  - Reports/test results.
  - Low-resolution image warning.
- Suspicious hospital or doctor repetition.
- Newly added beneficiary or recent policy modification with an immediate high-value claim.
- Rule coverage for:
  - `EARLY_CLAIM_AFTER_POLICY_START`
  - `MULTIPLE_ACTIVE_POLICIES`
  - `EXCESSIVE_CLAIM_FREQUENCY`
  - `CLAIM_AFTER_COVERAGE_UPGRADE`
  - `DEMOGRAPHIC_MISMATCH`

## Scoring

The agent combines these components into a final `fraud_score` from 0 to 100:

| Component | Weight |
|---|---:|
| Eligibility | 20% |
| Member history | 18% |
| Incident type | 12% |
| Document validation | 25% |
| Provider network | 15% |
| Policy and beneficiary risk | 10% |

Risk levels:

| Score | Risk level | Action |
|---:|---|---|
| `0-30` | `LOW` | Auto-adjudicate or continue normal payment workflow. |
| `31-60` | `MEDIUM` | Pend for claims analyst review. |
| `61-80` | `HIGH` | Request medical records or provider clarification before payment. |
| `81-100` | `VERY_HIGH` | Suspend payment and refer to SIU/compliance. |

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Useful URLs:

- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## Example Request

```bash
curl -X POST http://localhost:8000/api/v1/claims/score \
  -H "Content-Type: application/json" \
  -d @docs/example-health-claim.json
```

Run tests:

```bash
pytest
```

## Deploy to SAP BTP Cloud Foundry

After logging in and targeting the intended organization and space:

```bash
cf push
```

The deployment uses `manifest.yml`, starts the FastAPI service on the Cloud
Foundry-provided port, and checks application health through `/health`.
