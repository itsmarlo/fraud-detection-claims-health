from fastapi import FastAPI

from app.api.claims import router as claims_router

app = FastAPI(
    title="Health Fraud Detection Agent",
    version="0.1.0",
    description="Explainable health insurance claim fraud detection prototype.",
)

app.include_router(claims_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "health-fraud-detection-agent"}
