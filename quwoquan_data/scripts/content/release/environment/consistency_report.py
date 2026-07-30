"""Release consistency report primitives shared by focused scanners."""

from __future__ import annotations


def blocking_issue(code: str, message: str, ref: str = "") -> dict[str, str]:
    return {"severity": "blocking", "code": code, "message": message, "ref": ref}


__all__ = ["blocking_issue"]
