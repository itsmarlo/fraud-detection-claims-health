from fastapi.testclient import TestClient

from app.main import app


def test_health_check():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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

    response = TestClient(app).post("/api/v1/claims/score", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["claim_id"] == "CLM-API-1"
    assert body["risk_level"] == "LOW"
    assert "component_scores" in body
