"""Typed constants and canonical hashing for media source admission."""

from __future__ import annotations

import hashlib
import json

MEDIA_SOURCE_ADMISSION_INVALID = "DATA.SOURCE.ADMISSION_INVALID"
MEDIA_SOURCE_ADMISSION_BLOCKED = "DATA.SOURCE.ADMISSION_BLOCKED"
MEDIA_SOURCE_MEDIA_PROBE_BLOCKED = "DATA.SOURCE.MEDIA_PROBE_BLOCKED"
MEDIA_SOURCE_SAFETY_REVIEW_BLOCKED = "DATA.SOURCE.SAFETY_REVIEW_BLOCKED"


class MediaSourceAdmissionError(ValueError):
    """Typed source-admission failure."""

    def __init__(self, code: str, issues: list[object] | tuple[object, ...] | object) -> None:
        raw = issues if isinstance(issues, list | tuple) else [issues]
        normalized = tuple(str(issue).strip() for issue in raw if str(issue).strip())
        if not normalized:
            normalized = ("media source admission failed",)
        self.code = str(code)
        self.issues = normalized
        self.issue = normalized[0]
        super().__init__(f"{self.code}: " + "; ".join(normalized))


def canonical_digest(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


__all__ = [
    "MEDIA_SOURCE_ADMISSION_BLOCKED",
    "MEDIA_SOURCE_ADMISSION_INVALID",
    "MEDIA_SOURCE_MEDIA_PROBE_BLOCKED",
    "MEDIA_SOURCE_SAFETY_REVIEW_BLOCKED",
    "MediaSourceAdmissionError",
    "canonical_digest",
]
