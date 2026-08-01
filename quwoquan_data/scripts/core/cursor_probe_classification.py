"""Classification helpers for repeated Cursor startup probes."""
from __future__ import annotations

from collections.abc import Mapping


def _attempt_rows(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = payload.get("attempts")
    candidates: list[Mapping[str, object]] = [payload]
    if isinstance(rows, list):
        candidates.extend(row for row in rows if isinstance(row, Mapping))
    return candidates


def cursor_probe_attempt_has_5xx(payload: Mapping[str, object]) -> bool:
    for row in _attempt_rows(payload):
        status = row.get("httpStatus")
        try:
            status_int = int(status) if status is not None else 0
        except (TypeError, ValueError):
            status_int = 0
        if 500 <= status_int < 600:
            return True
        if str(row.get("errorClass") or "") == "InternalServerError":
            return True
        if str(row.get("errorCode") or "") == "internal":
            return True
    return False


def cursor_probe_attempt_is_auth(payload: Mapping[str, object]) -> bool:
    try:
        from core.cursor_credentials import is_cursor_auth_error
    except Exception:  # noqa: BLE001
        from cursor_credentials import is_cursor_auth_error  # type: ignore
    return any(
        is_cursor_auth_error(
            str(row.get("error") or row.get("status") or ""),
            code=str(row.get("errorCode") or ""),
            status=row.get("httpStatus"),
        )
        for row in _attempt_rows(payload)
    )


def cursor_probe_attempt_is_bridge_disconnect(
    payload: Mapping[str, object],
) -> bool:
    markers = (
        "connection refused",
        "connecterror",
        "connection reset",
        "server disconnected",
        "remoteprotocolerror",
        "bridge request failed",
        "exited before discovery",
        "failed before discovery",
    )
    for row in _attempt_rows(payload):
        text = f"{row.get('errorClass') or ''} {row.get('error') or ''}".casefold()
        if any(marker in text for marker in markers):
            return True
    return False


def cursor_probe_is_startup_timeout(payload: Mapping[str, object]) -> bool:
    """Return whether the probe terminal verdict is a startup timeout."""

    return (
        str(payload.get("status") or "") == "timeout"
        or str(payload.get("errorClass") or "") == "TimeoutExpired"
        or str(payload.get("errorCode") or "") == "timeout"
    )


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(
        0,
        min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1),
    )
    return round(ordered[index], 4)
