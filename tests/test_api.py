from fastapi.testclient import TestClient

from app.main import app


def test_health_check():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_review_console_is_served():
    client = TestClient(app)

    page = client.get("/")
    stylesheet = client.get("/static/fiori.css")
    script = client.get("/static/app.js")
    logo = client.get("/static/sap-fioneer-logo.svg")
    font = client.get("/static/BentonSans-Regular.woff2")

    assert page.status_code == 200
    assert "Claim Review Console" in page.text
    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert logo.status_code == 200
    assert font.status_code == 200


def test_score_endpoint():
    payload = {
        "claim_id": "CLM-API-1",
        "policy_id": "POL-API-1",
        "member_id": "MBR-API-1",
        "provider_id": "NPI-API-1",
        "claim_type": "OUT_PATIENT",
        "cause_of_loss": "ROUTINE_CONSULTATION",
        "claim_amount": 250,
        "billed_amount": 300,
        "allowed_amount": 200,
        "policy_start_date": "2026-01-01",
        "policy_end_date": "2026-12-31",
        "date_of_loss": "2026-05-01",
        "claim_submission_date": "2026-05-02",
        "diagnosis_codes": ["Z00.0"],
        "procedure_codes": ["99213"],
        "documents": {"hospital_bill": True}
    }

    response = TestClient(app).post("/api/v1/healthcare-claims/assess", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["claim_id"] == "CLM-API-1"
    assert body["risk_tier"] == "ROUTINE_REVIEW_PRIORITY"
    assert body["assessment_purpose"] == "HUMAN_REVIEW_DECISION_SUPPORT"
    assert body["rule_set_version"] == "health-fwa-rules-1.0.0"
    assert "component_scores" in body


def test_legacy_score_route_remains_available():
    payload = {
        "claim_id": "CLM-LEGACY-1",
        "policy_id": "POL-LEGACY-1",
        "member_id": "MBR-LEGACY-1",
        "provider_id": "NPI-LEGACY-1",
        "claim_type": "OUT_PATIENT",
        "claim_amount": 250,
        "billed_amount": 300,
        "allowed_amount": 200,
        "policy_start_date": "2026-01-01",
        "policy_end_date": "2026-12-31",
        "date_of_loss": "2026-05-01",
        "claim_submission_date": "2026-05-02",
        "documents": {"hospital_bill": True},
    }

    response = TestClient(app).post("/api/v1/claims/score", json=payload)

    assert response.status_code == 200
