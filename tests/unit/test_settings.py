from pathlib import Path

import pytest

from arvan_orchestrator.settings import FeatureGateError, Settings, load_settings


def test_defaults_fail_closed_when_settings_file_missing(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.feature_gates.automatic_rotation_enabled is False
    assert settings.feature_gates.provider_writes_enabled is False
    assert settings.feature_gates.traffic_calibration_required is True
    assert settings.feature_gates.delete_requires_approval is True
    assert settings.feature_gates.cross_account_handover_enabled is False


@pytest.mark.parametrize(
    ("guard_name", "message"),
    [
        ("require_provider_write_enabled", "Provider writes are disabled"),
        ("require_automatic_rotation_enabled", "Automatic rotation is disabled"),
        ("require_traffic_calibration_complete", "Traffic calibration is required"),
        ("require_delete_approval_not_required", "Delete operations require"),
        ("require_cross_account_handover_enabled", "Cross-account handover is disabled"),
    ],
)
def test_feature_gate_guards_fail_closed_by_default(guard_name: str, message: str) -> None:
    guard = getattr(Settings().feature_gates, guard_name)

    with pytest.raises(FeatureGateError, match=message):
        guard()


def test_example_settings_load_explicit_phase_one_two_feature_gates() -> None:
    settings = load_settings("config/settings.example.yaml")

    assert settings.feature_gates.automatic_rotation_enabled is False
    assert settings.feature_gates.provider_writes_enabled is False
    assert settings.feature_gates.traffic_calibration_required is True
    assert settings.feature_gates.delete_requires_approval is True
    assert settings.feature_gates.cross_account_handover_enabled is False
