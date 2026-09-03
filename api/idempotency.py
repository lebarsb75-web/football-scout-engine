import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CachedSubmission:
    fingerprint: str
    response: dict[str, Any]
    created_at: float


class IdempotencyStore:
    """Small process-local duplicate submission guard.

    This does not replace a shared database in production, but it prevents an
    accidental double-click / retry from spending twice on a single API
    instance. The production architecture should replace this with a durable,
    atomic store such as Postgres/Redis before horizontal scaling.
    """

    def __init__(self, ttl_seconds: int = 24 * 60 * 60, max_entries: int = 5000):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._items: dict[str, CachedSubmission] = {}
        self._lock = threading.Lock()

    @staticmethod
    def fingerprint(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _purge(self, now: float) -> None:
        expired = [
            key
            for key, value in self._items.items()
            if now - value.created_at >= self.ttl_seconds
        ]
        for key in expired:
            self._items.pop(key, None)

        if len(self._items) > self.max_entries:
            oldest = sorted(self._items.items(), key=lambda item: item[1].created_at)
            for key, _ in oldest[: len(self._items) - self.max_entries]:
                self._items.pop(key, None)

    def get(self, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        now = time.time()
        fingerprint = self.fingerprint(payload)
        with self._lock:
            self._purge(now)
            cached = self._items.get(key)
            if cached is None:
                return None
            if cached.fingerprint != fingerprint:
                raise ValueError("Idempotency key was already used with a different payload")
            return cached.response

    def put(self, key: str, payload: dict[str, Any], response: dict[str, Any]) -> None:
        now = time.time()
        fingerprint = self.fingerprint(payload)
        with self._lock:
            self._purge(now)
            existing = self._items.get(key)
            if existing is not None and existing.fingerprint != fingerprint:
                raise ValueError("Idempotency key was already used with a different payload")
            self._items[key] = CachedSubmission(
                fingerprint=fingerprint,
                response=response,
                created_at=now,
            )
