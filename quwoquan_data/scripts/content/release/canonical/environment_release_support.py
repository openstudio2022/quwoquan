"""Small deterministic helpers for canonical pool selection."""

from __future__ import annotations

def pool_error_code(exc: BaseException) -> str:
    value = str(exc).strip().split(":", 1)[0]
    return value if value.startswith("DATA.") else "DATA.POOL.OBJECT_INVALID"


def pool_gate_for_code(code: str) -> str:
    if any(token in code for token in ("REFERENCE", "AUTHOR", "MEDIA")):
        return "delivery"
    if any(token in code for token in ("QUALITY", "MANIFEST", "GENERATOR")):
        return "quality"
    return "eligibility"
__all__ = ["pool_error_code", "pool_gate_for_code"]
