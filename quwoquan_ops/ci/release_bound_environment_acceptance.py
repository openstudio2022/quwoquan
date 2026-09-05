"""Validate the EnvironmentAcceptanceFact bound to one release identity."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    EnvironmentAcceptanceFactError,
    load_environment_acceptance_fact,
)

def acceptance_relative_ref(path: Path, *, evidence_root: Path) -> str:
    root = evidence_root.expanduser().resolve()
    supplied = path.expanduser()
    if supplied.is_symlink():
        raise ValueError("EnvironmentAcceptanceFact must be a regular non-symlink file")
    candidate = supplied.resolve()
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("EnvironmentAcceptanceFact must be below data output root") from exc

def validate_environment_acceptance_authority(
    path: Path, *, evidence_root: Path, environment: str, target: str,
    release_id: str, release_digest: str,
    required_target_profiles: list[dict[str, str]] | tuple[dict[str, str], ...],
) -> dict[str, Any]:
    try:
        relative = acceptance_relative_ref(path, evidence_root=evidence_root)
        fact, fact_digest = load_environment_acceptance_fact(
            relative, evidence_root=evidence_root,
            required_target_profiles=required_target_profiles,
            verify_references=True,
        )
    except EnvironmentAcceptanceFactError as exc:
        raise ValueError(f"EnvironmentAcceptanceFact authority is invalid: {exc}") from exc
    expected = {
        "environment": environment, "target": target, "releaseId": release_id,
        "releaseDigest": release_digest,
    }
    for field, expected_value in expected.items():
        if fact.get(field) != expected_value:
            raise ValueError(f"EnvironmentAcceptanceFact {field} drift")
    raw_results = fact.get("requiredRawResults")
    if not isinstance(raw_results, list) or not raw_results:
        raise ValueError("EnvironmentAcceptanceFact lacks required raw ReadinessCaseResult refs")
    return {
        "factId": str(fact["factId"]), "ref": relative, "digest": fact_digest,
        "requiredRawResults": [
            {"ref": str(item["ref"]), "digest": str(item["digest"]),
             "slotId": str(item["slotId"])}
            for item in raw_results
        ],
    }
