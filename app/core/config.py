from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or `.env`."""

    app_name: str = "Health Fraud Detection Agent"
    app_env: str = "local"
    app_version: str = "0.1.0"
    schema_version: str = "health-claim-assessment-1.0.0"
    rule_set_version: str = "health-fwa-rules-1.0.0"
    cors_origins: str = "*"

    eligibility_weight: float = Field(default=0.20, ge=0, le=1)
    member_history_weight: float = Field(default=0.18, ge=0, le=1)
    incident_type_weight: float = Field(default=0.12, ge=0, le=1)
    document_validation_weight: float = Field(default=0.25, ge=0, le=1)
    provider_network_weight: float = Field(default=0.15, ge=0, le=1)
    policy_beneficiary_weight: float = Field(default=0.10, ge=0, le=1)

    high_value_beneficiary_threshold: float = Field(default=3000, ge=0)
    routine_review_max_score: float = Field(default=30, ge=0, le=100)
    elevated_review_max_score: float = Field(default=60, ge=0, le=100)
    high_review_max_score: float = Field(default=80, ge=0, le=100)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_component_weights(self) -> "Settings":
        if abs(sum(self.component_weights.values()) - 1.0) > 1e-9:
            raise ValueError("Risk component weights must add up to 1.0")
        if not (
            self.routine_review_max_score
            < self.elevated_review_max_score
            < self.high_review_max_score
        ):
            raise ValueError("Review score thresholds must be strictly increasing")
        return self

    @property
    def component_weights(self) -> dict[str, float]:
        return {
            "eligibility": self.eligibility_weight,
            "member_history": self.member_history_weight,
            "incident_type": self.incident_type_weight,
            "document_validation": self.document_validation_weight,
            "provider_network": self.provider_network_weight,
            "policy_beneficiary": self.policy_beneficiary_weight,
        }

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
