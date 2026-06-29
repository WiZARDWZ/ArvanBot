"""Fail-closed rotation handover state machine rules.

Evidence level: INFERRED from ``Agent.md`` section 25 and the operator plan. This module is
pure domain logic; it performs no provider API calls and does not assume provider lifecycle states.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class RotationState(StrEnum):
    """Rotation handover states for replacing a source server with a next server."""

    # Agent.md section 25 planning/precheck states.
    PLANNED = "PLANNED"
    PRECHECK = "PRECHECK"

    # User-plan next-account / next-server flow.
    WAITING_FOR_THRESHOLD = "WAITING_FOR_THRESHOLD"
    PREPARING_NEXT_ACCOUNT = "PREPARING_NEXT_ACCOUNT"
    NEXT_SERVER_CREATE_REQUESTED = "NEXT_SERVER_CREATE_REQUESTED"
    NEXT_SERVER_PROVISIONING = "NEXT_SERVER_PROVISIONING"
    NEXT_SERVER_BOOTSTRAPPING = "NEXT_SERVER_BOOTSTRAPPING"
    NEXT_SERVER_VERIFYING = "NEXT_SERVER_VERIFYING"
    NEXT_SERVER_READY = "NEXT_SERVER_READY"

    # Agent.md section 25 target aliases retained for compatibility with design text.
    TARGET_CREATE_REQUESTED = "TARGET_CREATE_REQUESTED"
    TARGET_PROVISIONING = "TARGET_PROVISIONING"
    TARGET_BOOTSTRAPPING = "TARGET_BOOTSTRAPPING"
    TARGET_VERIFYING = "TARGET_VERIFYING"
    TARGET_READY = "TARGET_READY"

    # Traffic handover and source retirement.
    DNS_UPDATE_REQUESTED = "DNS_UPDATE_REQUESTED"
    DNS_UPDATE_VERIFIED = "DNS_UPDATE_VERIFIED"
    TRAFFIC_SWITCHING = "TRAFFIC_SWITCHING"
    TRAFFIC_VERIFYING = "TRAFFIC_VERIFYING"
    SOURCE_DRAINING = "SOURCE_DRAINING"
    SOURCE_POWERING_OFF = "SOURCE_POWERING_OFF"
    SOURCE_STOPPED = "SOURCE_STOPPED"
    SOURCE_RETENTION = "SOURCE_RETENTION"
    SOURCE_DELETE_PENDING = "SOURCE_DELETE_PENDING"
    SOURCE_DELETING = "SOURCE_DELETING"
    PERIODIC_CLEANUP = "PERIODIC_CLEANUP"
    COMPLETE = "COMPLETE"

    # Error / recovery states. These are intentionally terminal unless explicitly handled by a
    # higher-level reconciler; unsafe retries must not be encoded as normal progress.
    ROLLBACK = "ROLLBACK"
    FAILED = "FAILED"
    USAGE_UNCERTAIN = "USAGE_UNCERTAIN"
    CREATE_TIMEOUT = "CREATE_TIMEOUT"
    BLIND_CREATE_RETRY = "BLIND_CREATE_RETRY"


class ForbiddenTransitionError(ValueError):
    """Raised when a rotation transition is not permitted by the fail-closed state machine."""

    def __init__(self, source: RotationState, target: RotationState) -> None:
        super().__init__(f"forbidden rotation transition: {source.value} -> {target.value}")
        self.source = source
        self.target = target


_FORBIDDEN_TRANSITIONS: Final[frozenset[tuple[RotationState, RotationState]]] = frozenset(
    {
        # Explicitly forbidden by Agent.md section 25.
        (RotationState.TARGET_PROVISIONING, RotationState.TRAFFIC_SWITCHING),
        (RotationState.TARGET_BOOTSTRAPPING, RotationState.SOURCE_POWERING_OFF),
        (RotationState.TARGET_VERIFYING, RotationState.SOURCE_DELETING),
        (RotationState.TRAFFIC_SWITCHING, RotationState.SOURCE_DELETING),
        (RotationState.SOURCE_POWERING_OFF, RotationState.COMPLETE),
        # Same safety rules applied to the user-plan NEXT_* names.
        (RotationState.NEXT_SERVER_PROVISIONING, RotationState.TRAFFIC_SWITCHING),
        (RotationState.NEXT_SERVER_BOOTSTRAPPING, RotationState.SOURCE_POWERING_OFF),
        (RotationState.NEXT_SERVER_VERIFYING, RotationState.SOURCE_DELETING),
        # Additional user-plan safety prohibitions.
        (RotationState.USAGE_UNCERTAIN, RotationState.SOURCE_DELETING),
        (RotationState.CREATE_TIMEOUT, RotationState.BLIND_CREATE_RETRY),
    }
)

_ALLOWED_TRANSITIONS: Final[dict[RotationState, frozenset[RotationState]]] = {
    RotationState.WAITING_FOR_THRESHOLD: frozenset({RotationState.PREPARING_NEXT_ACCOUNT}),
    RotationState.PREPARING_NEXT_ACCOUNT: frozenset({RotationState.NEXT_SERVER_CREATE_REQUESTED}),
    RotationState.NEXT_SERVER_CREATE_REQUESTED: frozenset(
        {RotationState.NEXT_SERVER_PROVISIONING, RotationState.CREATE_TIMEOUT}
    ),
    RotationState.NEXT_SERVER_PROVISIONING: frozenset(
        {RotationState.NEXT_SERVER_BOOTSTRAPPING, RotationState.FAILED}
    ),
    RotationState.NEXT_SERVER_BOOTSTRAPPING: frozenset(
        {RotationState.NEXT_SERVER_VERIFYING, RotationState.FAILED}
    ),
    RotationState.NEXT_SERVER_VERIFYING: frozenset(
        {RotationState.NEXT_SERVER_READY, RotationState.FAILED}
    ),
    RotationState.NEXT_SERVER_READY: frozenset({RotationState.TRAFFIC_SWITCHING}),
    RotationState.TRAFFIC_SWITCHING: frozenset({RotationState.TRAFFIC_VERIFYING, RotationState.ROLLBACK}),
    RotationState.TRAFFIC_VERIFYING: frozenset({RotationState.SOURCE_DRAINING, RotationState.ROLLBACK}),
    RotationState.SOURCE_DRAINING: frozenset({RotationState.SOURCE_POWERING_OFF}),
    RotationState.SOURCE_POWERING_OFF: frozenset({RotationState.SOURCE_STOPPED, RotationState.FAILED}),
    RotationState.SOURCE_STOPPED: frozenset({RotationState.SOURCE_RETENTION}),
    RotationState.SOURCE_RETENTION: frozenset({RotationState.SOURCE_DELETE_PENDING}),
    RotationState.SOURCE_DELETE_PENDING: frozenset({RotationState.SOURCE_DELETING}),
    RotationState.SOURCE_DELETING: frozenset({RotationState.PERIODIC_CLEANUP, RotationState.FAILED}),
    RotationState.PERIODIC_CLEANUP: frozenset({RotationState.COMPLETE, RotationState.FAILED}),
    # Legacy Agent.md section 25 names follow the same safe order.
    RotationState.PLANNED: frozenset({RotationState.PRECHECK}),
    RotationState.PRECHECK: frozenset({RotationState.TARGET_CREATE_REQUESTED}),
    RotationState.TARGET_CREATE_REQUESTED: frozenset(
        {RotationState.TARGET_PROVISIONING, RotationState.CREATE_TIMEOUT}
    ),
    RotationState.TARGET_PROVISIONING: frozenset({RotationState.TARGET_BOOTSTRAPPING, RotationState.FAILED}),
    RotationState.TARGET_BOOTSTRAPPING: frozenset({RotationState.TARGET_VERIFYING, RotationState.FAILED}),
    RotationState.TARGET_VERIFYING: frozenset({RotationState.TARGET_READY, RotationState.FAILED}),
    RotationState.TARGET_READY: frozenset({RotationState.TRAFFIC_SWITCHING}),
    RotationState.DNS_UPDATE_REQUESTED: frozenset({RotationState.DNS_UPDATE_VERIFIED}),
    RotationState.DNS_UPDATE_VERIFIED: frozenset({RotationState.TRAFFIC_VERIFYING}),
}


def is_forbidden_transition(source: RotationState, target: RotationState) -> bool:
    """Return whether ``source -> target`` is an explicitly forbidden unsafe transition."""

    return (source, target) in _FORBIDDEN_TRANSITIONS


def can_transition(source: RotationState, target: RotationState) -> bool:
    """Return whether ``source -> target`` is allowed.

    The state machine fails closed: transitions must be listed in the allowed map and must not be
    listed in the explicit forbidden set.
    """

    return not is_forbidden_transition(source, target) and target in _ALLOWED_TRANSITIONS.get(
        source, frozenset()
    )


def assert_transition_allowed(source: RotationState, target: RotationState) -> None:
    """Raise :class:`ForbiddenTransitionError` unless the transition is allowed."""

    if not can_transition(source, target):
        raise ForbiddenTransitionError(source, target)
