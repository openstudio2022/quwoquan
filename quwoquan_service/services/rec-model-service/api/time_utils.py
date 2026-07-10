from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    effective = value or utc_now()
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=timezone.utc)
    return effective.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
