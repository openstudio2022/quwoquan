"""Canonical environment activation identity derived from immutable evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class EnvironmentActivationEnvelopeError(ValueError):
    """Activation evidence is incomplete or mixes release/environment identity."""


def document_digest(value: Mapping[str, Any]) -> str:
    """Return the canonical digest used for nested activation documents."""

    canonical = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def file_digest(path: Path) -> str:
    """Bind one exact append-only evidence file, not only its decoded fields."""

    if path.is_symlink() or not path.is_file():
        raise EnvironmentActivationEnvelopeError(
            f"activation evidence is missing or symlinked: {path}"
        )
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_environment_activation_envelope(
    *,
    environment: str,
    release_id: str,
    manifest_digest: str,
    source_revision: str | None,
    source_digest: str | None,
    entity_catalog_digest: str | None,
    release_class: str,
    product_lifecycle_state: str,
    readiness_phase: str,
    import_run_id: str,
    verify_run_id: str,
    import_report_ref: str,
    import_report_digest: str,
    app_uat_envelope: Mapping[str, Any],
    research_isolation: Mapping[str, Any] | None,
    research_isolation_verification_ref: str = "",
    research_isolation_verification_digest: str = "",
    source_identities: list[dict[str, object]] | None = None,
    source_identity_set_digest: str | None = None,
    milestone: str | None = None,
    previous_environment_activation: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the one environment-specific activation/readback binding.

    The envelope deliberately contains no deployment endpoint or mutable active
    pointer.  It binds an immutable Data release to one environment import and
    one environment readback.  Research isolation is required only for the
    research activation phase; consumer probes and commercial activation remain
    separate lifecycle facts.
    """

    text_fields = {
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "releaseClass": release_class,
        "productLifecycleState": product_lifecycle_state,
        "readinessPhase": readiness_phase,
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "importReportRef": import_report_ref,
        "importReportDigest": import_report_digest,
    }
    missing = sorted(key for key, value in text_fields.items() if not str(value).strip())
    if missing:
        raise EnvironmentActivationEnvelopeError(
            "activation envelope has empty fields: " + ", ".join(missing)
        )
    envelope: dict[str, Any] = {
        "schema": "quwoquan_data.environment_activation_envelope",
        **text_fields,
        "appUatEnvelopeDigest": document_digest(app_uat_envelope),
    }
    scalar_identity = (source_revision, source_digest, entity_catalog_digest)
    if source_identities is not None:
        if any(value is not None for value in scalar_identity) or not (
            source_identities and source_identity_set_digest
        ):
            raise EnvironmentActivationEnvelopeError(
                "activation source identity set is incomplete"
            )
        envelope["sourceIdentities"] = list(source_identities)
        envelope["sourceIdentitySetDigest"] = source_identity_set_digest
    elif not all(str(value or "").strip() for value in scalar_identity):
        raise EnvironmentActivationEnvelopeError(
            "activation scalar source identity is incomplete"
        )
    else:
        envelope.update(
            {
                "sourceRevision": source_revision,
                "sourceDigest": source_digest,
                "entityCatalogDigest": entity_catalog_digest,
            }
        )
    if readiness_phase == "research":
        if research_isolation is None:
            raise EnvironmentActivationEnvelopeError(
                "research activation requires isolation policy and runtime proof"
            )
        isolation = {
            "policyRef": str(research_isolation.get("policyRef") or "").strip(),
            "policyDigest": str(
                research_isolation.get("policySha256") or ""
            ).strip(),
            "verificationRef": str(
                research_isolation_verification_ref or ""
            ).strip(),
            "verificationDigest": str(
                research_isolation_verification_digest or ""
            ).strip(),
            "subjectHash": str(research_isolation.get("subjectHash") or "").strip(),
        }
        missing_isolation = sorted(
            key for key, value in isolation.items() if not value
        )
        if missing_isolation:
            raise EnvironmentActivationEnvelopeError(
                "research activation isolation is incomplete: "
                + ", ".join(missing_isolation)
            )
        envelope["researchIsolationPolicy"] = isolation
    elif research_isolation is not None:
        raise EnvironmentActivationEnvelopeError(
            "research isolation cannot bind a non-research activation phase"
        )
    if milestone is not None:
        if (
            milestone not in {"M100", "M1000", "M10000"}
            or readiness_phase != "research"
            or release_class != "research"
            or product_lifecycle_state != "research"
            or source_identities is None
            or not source_identity_set_digest
        ):
            raise EnvironmentActivationEnvelopeError(
                "milestone activation must bind one Research source identity set"
            )
        previous = {
            "alpha": None,
            "beta": "alpha",
            "gamma": "beta",
            "prod": "gamma",
        }.get(environment)
        if environment not in {"alpha", "beta", "gamma", "prod"}:
            raise EnvironmentActivationEnvelopeError(
                f"unsupported milestone activation environment: {environment!r}"
            )
        if previous is None:
            if previous_environment_activation is not None:
                raise EnvironmentActivationEnvelopeError(
                    "alpha milestone activation must not bind a predecessor"
                )
        elif (
            not isinstance(previous_environment_activation, Mapping)
            or previous_environment_activation.get("environment") != previous
        ):
            raise EnvironmentActivationEnvelopeError(
                f"{environment} milestone activation requires {previous} predecessor"
            )
        envelope["milestone"] = milestone
        envelope["previousEnvironmentActivation"] = (
            dict(previous_environment_activation)
            if previous_environment_activation is not None
            else None
        )
    elif previous_environment_activation is not None:
        raise EnvironmentActivationEnvelopeError(
            "non-milestone activation cannot bind an environment predecessor"
        )
    return envelope


def build_release_activation_envelope(
    *,
    header: Mapping[str, Any],
    environment: str,
    release_id: str,
    manifest_digest: str,
    release_class: str,
    product_lifecycle_state: str,
    readiness_phase: str,
    import_run_id: str,
    verify_run_id: str,
    import_report_ref: str,
    import_report_digest: str,
    app_uat_envelope: Mapping[str, Any],
    research_isolation: Mapping[str, Any] | None,
    research_isolation_verification_ref: str,
    research_isolation_verification_digest: str,
    previous_environment_activation: Mapping[str, str] | None,
) -> dict[str, Any]:
    """Project immutable header identity into one environment envelope."""

    return build_environment_activation_envelope(
        environment=environment,
        release_id=release_id,
        manifest_digest=manifest_digest,
        source_revision=(
            str(header["sourceRevision"]) if "sourceRevision" in header else None
        ),
        source_digest=(
            str(header["sourceDigest"]) if "sourceDigest" in header else None
        ),
        entity_catalog_digest=(
            str(header["entityCatalogDigest"])
            if "entityCatalogDigest" in header
            else None
        ),
        release_class=release_class,
        product_lifecycle_state=product_lifecycle_state,
        readiness_phase=readiness_phase,
        import_run_id=import_run_id,
        verify_run_id=verify_run_id,
        import_report_ref=import_report_ref,
        import_report_digest=import_report_digest,
        app_uat_envelope=app_uat_envelope,
        research_isolation=research_isolation,
        research_isolation_verification_ref=research_isolation_verification_ref,
        research_isolation_verification_digest=(
            research_isolation_verification_digest
        ),
        source_identities=(
            list(header["sourceIdentities"])
            if "sourceIdentities" in header
            else None
        ),
        source_identity_set_digest=(
            str(header["sourceIdentitySetDigest"])
            if "sourceIdentitySetDigest" in header
            else None
        ),
        milestone=(str(header["milestone"]) if "milestone" in header else None),
        previous_environment_activation=previous_environment_activation,
    )


__all__ = [
    "EnvironmentActivationEnvelopeError",
    "build_environment_activation_envelope",
    "build_release_activation_envelope",
    "document_digest",
    "file_digest",
]
