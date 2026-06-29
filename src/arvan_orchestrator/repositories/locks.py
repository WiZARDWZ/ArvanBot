"""Repository-level locking interfaces for rotation-critical operations.

This module intentionally defines contracts only. Concrete implementations must be completed with
whichever database adapter owns persistence, and must be tested before scheduler code relies on
these locks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import AsyncContextManager, Protocol
from uuid import UUID


class LockBackend(StrEnum):
    """Database locking mechanisms supported by the repository contract."""

    POSTGRES_ADVISORY = "postgres_advisory"
    ROW_LEVEL = "row_level"


class LockScope(StrEnum):
    """Named lock scopes for service-level operations that must be serialized."""

    SERVICE_ROTATION = "service_rotation"


@dataclass(frozen=True, slots=True)
class RepositoryLockKey:
    """A stable, database-safe identifier for a repository lock."""

    scope: LockScope
    service_id: UUID


@dataclass(frozen=True, slots=True)
class RepositoryLockRequest:
    """Request parameters for acquiring a repository lock."""

    key: RepositoryLockKey
    backend: LockBackend
    wait: bool = False


@dataclass(frozen=True, slots=True)
class RepositoryLockToken:
    """Opaque token returned after a lock has been acquired."""

    key: RepositoryLockKey
    backend: LockBackend


class RepositoryLockError(RuntimeError):
    """Base error for repository lock failures."""


class RepositoryLockUnavailableError(RepositoryLockError):
    """Raised when a non-blocking lock acquisition cannot obtain the requested lock."""


class RepositoryLockManager(Protocol):
    """Contract for serializing service-level repository operations.

    Implementations may use PostgreSQL advisory locks or transactional row-level locks, but callers
    should depend only on this interface. Rotation workflows should acquire a
    :class:`RepositoryLockToken` before mutating per-service rotation state, provider resource
    mappings, or any other state that must not be updated concurrently for the same service.
    """

    async def acquire(self, request: RepositoryLockRequest) -> RepositoryLockToken:
        """Acquire and return a lock token for ``request``.

        If ``request.wait`` is false, implementations should fail fast by raising
        :class:`RepositoryLockUnavailableError` when another transaction or session owns the lock.
        """

    async def release(self, token: RepositoryLockToken) -> None:
        """Release a previously acquired lock token."""

    def hold(self, request: RepositoryLockRequest) -> AsyncContextManager[RepositoryLockToken]:
        """Return an async context manager that acquires and releases ``request``."""
