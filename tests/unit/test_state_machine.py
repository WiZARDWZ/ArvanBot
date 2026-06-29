import pytest

from arvan_orchestrator.domain.state_machine import (
    ForbiddenTransitionError,
    RotationState,
    assert_transition_allowed,
    can_transition,
    is_forbidden_transition,
)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (RotationState.NEXT_SERVER_PROVISIONING, RotationState.TRAFFIC_SWITCHING),
        (RotationState.TARGET_PROVISIONING, RotationState.TRAFFIC_SWITCHING),
        (RotationState.NEXT_SERVER_BOOTSTRAPPING, RotationState.SOURCE_POWERING_OFF),
        (RotationState.TARGET_BOOTSTRAPPING, RotationState.SOURCE_POWERING_OFF),
        (RotationState.NEXT_SERVER_VERIFYING, RotationState.SOURCE_DELETING),
        (RotationState.TARGET_VERIFYING, RotationState.SOURCE_DELETING),
        (RotationState.TRAFFIC_SWITCHING, RotationState.SOURCE_DELETING),
        (RotationState.SOURCE_POWERING_OFF, RotationState.COMPLETE),
        (RotationState.USAGE_UNCERTAIN, RotationState.SOURCE_DELETING),
        (RotationState.CREATE_TIMEOUT, RotationState.BLIND_CREATE_RETRY),
    ],
)
def test_forbidden_rotation_transitions_are_rejected(
    source: RotationState, target: RotationState
) -> None:
    assert is_forbidden_transition(source, target)
    assert not can_transition(source, target)

    with pytest.raises(ForbiddenTransitionError):
        assert_transition_allowed(source, target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (RotationState.WAITING_FOR_THRESHOLD, RotationState.PREPARING_NEXT_ACCOUNT),
        (RotationState.NEXT_SERVER_VERIFYING, RotationState.NEXT_SERVER_READY),
        (RotationState.NEXT_SERVER_READY, RotationState.TRAFFIC_SWITCHING),
        (RotationState.SOURCE_POWERING_OFF, RotationState.SOURCE_STOPPED),
        (RotationState.SOURCE_DELETING, RotationState.PERIODIC_CLEANUP),
    ],
)
def test_expected_safe_rotation_transitions_are_allowed(
    source: RotationState, target: RotationState
) -> None:
    assert can_transition(source, target)
    assert_transition_allowed(source, target)
