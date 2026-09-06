"""Validate canonical EnvironmentAcceptanceFact v2 candidate authority."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.environment_scheduler import dsse_pae
from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    EnvironmentAcceptanceFactError,
    load_environment_acceptance_fact,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import DSSE_PAYLOAD_TYPE

_NAMED_EXACT_REF_FIELDS = (
    "runtimeIdentity",
    "dataLifecycle",
    "providerReadiness",
    "observabilityReadiness",
    "inspectEvidence",
    "doctorEvidence",
    "cleanupEvidence",
    "leaseClosureEvidence",
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
    path: Path,
    *,
    evidence_root: Path,
    environment: str,
    candidate_id: str,
    commit: str,
    tree: str,
    signature_verifier: Callable[[str, bytes, str], bool] | None = None,
) -> dict[str, Any]:
    """Load one exact v2 fact and bind it to the release manifest candidate."""

    if environment == "prod":
        raise ValueError("EnvironmentAcceptanceFact v2 does not cover prod")
    if signature_verifier is None:
        raise ValueError("EnvironmentAcceptanceFact DSSE verifier is required")

    def verify_dsse(
        signer_identity: str, signed_payload: bytes, signature: str
    ) -> bool:
        try:
            return signature_verifier(
                signer_identity,
                dsse_pae(DSSE_PAYLOAD_TYPE, signed_payload),
                signature,
            ) is True
        except Exception:
            return False

    try:
        relative = acceptance_relative_ref(path, evidence_root=evidence_root)
        fact, fact_digest = load_environment_acceptance_fact(
            relative,
            store_root=evidence_root,
            verify_references=True,
            accepted_at=datetime.now(timezone.utc),
            signature_verifier=verify_dsse,
        )
    except EnvironmentAcceptanceFactError as exc:
        raise ValueError(f"EnvironmentAcceptanceFact authority is invalid: {exc}") from exc

    if fact.get("environment") != environment:
        raise ValueError("EnvironmentAcceptanceFact environment drift")
    if fact.get("profile") != "release":
        raise ValueError("EnvironmentAcceptanceFact profile must be release")
    if fact.get("status") != "passed":
        raise ValueError("EnvironmentAcceptanceFact status must be passed")
    if fact.get("nonPromotable") is not False:
        raise ValueError("EnvironmentAcceptanceFact must be promotable")
    expected_candidate = {
        "candidateId": candidate_id,
        "commit": commit,
        "tree": tree,
    }
    if fact.get("candidate") != expected_candidate:
        raise ValueError("EnvironmentAcceptanceFact candidate drift")

    return {
        "factId": str(fact["factId"]),
        "ref": relative,
        "digest": fact_digest,
        "caseResultRefs": [dict(item) for item in fact["caseResultRefs"]],
        "namedEvidenceRefs": {
            field: dict(fact[field]) for field in _NAMED_EXACT_REF_FIELDS
        },
    }
