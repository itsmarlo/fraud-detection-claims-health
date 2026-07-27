# Healthcare FWA Review-Prioritization Service

This repository contains an explainable FastAPI prototype for healthcare fraud,
waste, and abuse (FWA) review prioritization. It is a decision-support service:
it ranks claims, explains triggered rules, and points reviewers to the source
fields. It does not deny care or reimbursement, or determine that a member or
provider committed fraud.

Development follows a rules-first vertical slice: validated contracts,
deterministic rules, evidence quality, entity/network context, and only then
calibrated ML or bounded LLM extraction. The current prototype is in the first
phase; it has no production ML or LLM dependency. See
[`docs/DEVELOPMENT_PATTERN.md`](docs/DEVELOPMENT_PATTERN.md) for the enforced
guardrails and next-stage gates.

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

## Implemented Review Signals

- Early claim after policy purchase:
  - `< 30 days`: high risk
  - `30-90 days`: medium risk
  - `> 90 days`: low risk
- Frequent claims by same policyholder:
  - `0-1 claims`: low risk
  - `2-3 claims`: medium risk
  - `> 3 claims`: high risk
- Duplicate health documents and reused invoices/prescriptions.
- Document date mismatch:
  - Medical report date not equal to treatment date.
  - Admission date after discharge date.
  - Treatment before policy inception.
- Missing supporting documents reduce confidence rather than increasing risk:
  - Hospital bill.
  - Discharge summary.
  - Prescription.
  - Medical report.
  - Reports/test results.
  - Low-resolution image warning.
- Suspicious hospital or doctor repetition.
- Newly added beneficiary or recent policy modification with an immediate high-value claim.
- Explainable rule coverage for:
  - `EARLY_CLAIM_AFTER_POLICY_START`
  - `MULTIPLE_ACTIVE_POLICIES`
  - `EXCESSIVE_CLAIM_FREQUENCY`
  - `CLAIM_AFTER_COVERAGE_UPGRADE`

Service type, claim cost, and patient demographics are not treated as FWA
signals by themselves.

## Scoring

The agent combines these prototype components into a `risk_score` from 0 to
100. The score prioritizes human review; it is not a fraud determination.

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
| `0-30` | `ROUTINE_REVIEW_PRIORITY` | Continue standard processing and routine controls. |
| `31-60` | `ELEVATED_REVIEW_PRIORITY` | Route to a payment-integrity analyst. |
| `61-80` | `HIGH_REVIEW_PRIORITY` | Prioritize review and gather supporting evidence. |
| `81-100` | `URGENT_REVIEW_PRIORITY` | Prioritize SIU/compliance review; no adverse action without human determination. |

Risk and confidence are separate. Missing or unprocessable evidence lowers
`confidence_score`; it does not prove fraud. Every risk reason includes
`evidence_refs`, and responses include schema and rule-set versions. Component
weights, review thresholds, and selected monetary thresholds are environment
configuration; the defaults remain prototype hypotheses requiring domain and
prospective validation.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Application metadata, browser origins, fraud component weights, and high-value
claim thresholds are configured through `.env`. Keep local secrets in `.env`;
commit only `.env.example`.

Useful URLs:

- Review console: `http://localhost:8000/`
- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## Document-Aware Assessment

The review console accepts PDF, PNG, and JPEG supporting evidence up to 10 MB
per file. Files are inspected in memory and discarded after the request. The
prototype checks file integrity, exact document reuse, image resolution,
machine-readable PDF identifiers, labelled totals, and supported clinical
dates. Extracted findings feed the same explainable human-review rules; they do
not establish fraud or trigger an automated adverse action.

High-severity document inconsistencies apply an elevated-review floor so they
cannot be diluted into routine processing by otherwise neutral components. The
underlying component score and evidence references remain visible to reviewers.

For API clients, send `claim_json` plus any of these multipart fields to
`POST /api/v1/healthcare-claims/assess-with-documents`:

- `hospital_bill_file`
- `discharge_summary_file`
- `prescription_file`
- `medical_report_file`
- `lab_or_test_results_file`

Scanned PDFs and images receive integrity and resolution checks. OCR is not
enabled in this prototype, so their textual analysis is reported as limited.
Only short SHA-256 fingerprints are kept in the running process to identify
exact reuse; this memory resets when the app restarts. Use synthetic evidence
until production authentication, malware scanning, encrypted storage, audit,
and retention controls are in place.

## Example Request

```bash
curl -X POST http://localhost:8000/api/v1/healthcare-claims/assess \
  -H "Content-Type: application/json" \
  -d @docs/example-health-claim.json
```

Run tests:

```bash
pytest
```

## Bruno API Collection

Open `bruno/health-fraud-detection-api` in Bruno and select `local` while the
Uvicorn server is running. The collection includes the health check plus
high-risk and low-risk claim-scoring requests with response assertions. Select
`btp` and set its `BASE_URL` after deploying to Cloud Foundry.

## Deploy to SAP BTP Cloud Foundry

After logging in and targeting the intended organization and space:

```bash
cf push
```

The deployment uses `manifest.yml`, the Python buildpack, environment-specific
configuration, the Cloud Foundry-provided port, and the `/health` health check.

The older `POST /api/v1/claims/score` path remains as a hidden compatibility
route. New integrations should use `POST /api/v1/healthcare-claims/assess`.
