from uuid import UUID

from arvan_orchestrator.repositories.locks import (
    LockBackend,
    LockScope,
    RepositoryLockKey,
    RepositoryLockRequest,
    RepositoryLockToken,
)


def test_service_rotation_lock_request_is_stable() -> None:
    service_id = UUID("00000000-0000-0000-0000-000000000001")
    key = RepositoryLockKey(scope=LockScope.SERVICE_ROTATION, service_id=service_id)

    request = RepositoryLockRequest(
        key=key,
        backend=LockBackend.POSTGRES_ADVISORY,
        wait=False,
    )
    token = RepositoryLockToken(key=key, backend=request.backend)

    assert request.key == key
    assert request.backend == LockBackend.POSTGRES_ADVISORY
    assert request.wait is False
    assert token.key == key
    assert token.backend == request.backend
