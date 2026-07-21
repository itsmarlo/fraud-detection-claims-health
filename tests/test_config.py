import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_default_component_weights_add_up_to_one():
    settings = Settings(_env_file=None)

    assert sum(settings.component_weights.values()) == pytest.approx(1.0)


def test_component_weights_must_add_up_to_one():
    with pytest.raises(ValidationError, match="must add up to 1.0"):
        Settings(_env_file=None, eligibility_weight=0.50)


def test_cors_origins_are_parsed_from_comma_separated_value():
    settings = Settings(_env_file=None, cors_origins="https://one.example, https://two.example")

    assert settings.cors_origin_list == ["https://one.example", "https://two.example"]


def test_review_score_thresholds_must_be_strictly_increasing():
    with pytest.raises(ValidationError, match="strictly increasing"):
        Settings(
            _env_file=None,
            routine_review_max_score=60,
            elevated_review_max_score=30,
        )
