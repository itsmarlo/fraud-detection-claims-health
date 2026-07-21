from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.claims import router as claims_router
from app.core.config import get_settings


settings = get_settings()
static_dir = Path(__file__).parent / "static"

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Explainable healthcare FWA review-prioritization prototype.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_origin_list != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(claims_router)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def review_console() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "health-fraud-detection-agent",
        "environment": settings.app_env,
        "version": settings.app_version,
    }
