"""聚合全部 typed receipt 计算终局 verdict 并原子写出（自原单文件逐字搬移）。"""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.release_evidence_reader import (
    validate_historical_release_snapshot,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.artifact_closure import (
    _artifact_closure,
    _validate_manifest_bound_acceptance_inputs,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.attested_evidence import (
    _reject_retired_ci_evidence,
    _validate_prod_sim,
    _verify_authority,
    verify_github_actions_receipt,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.hosted_prod import (
    _validate_hosted_readbacks,
    _validate_soak_authority,
    verify_canonical_hosted_prod_soak,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.model import (
    ArtifactClosureVerifier,
    AttestationVerifier,
    BLOCKED_VERDICT,
    ENVIRONMENTS,
    FinalAcceptanceInputs,
    LoadedReceipt,
    ProviderReadinessVerifier,
    RETIRED_GITHUB_ATTESTED_EVIDENCE_KINDS,
    SCHEMA,
    SoakAuthorityVerifier,
    _Evaluation,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.pilot_content import (
    _pilot_identity,
    _validate_content_lifecycle,
    _validate_green_matrix,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.provider_readiness import (
    verify_canonical_provider_readiness,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.receipt_io import (
    _canonical_digest,
    _load_receipt,
    _reject_self_asserted_authority,
    _resolve_artifact_root,
)


def _descriptor(
    receipt: LoadedReceipt | None,
    evaluation: _Evaluation,
    *,
    role: str = "promotion",
) -> dict[str, Any] | None:
    if receipt is None:
        return None
    authority = evaluation.authority.get(receipt.label)
    return {
        "schema": str(receipt.payload.get("schema") or ""),
        "path": receipt.path.as_posix(),
        "digest": receipt.digest,
        "observedAt": evaluation.observed_at.get(receipt.label, ""),
        "role": role,
        "authority": (
            {
                "kind": authority.authority,
                "verificationDigest": authority.verification_digest,
                "claims": sorted(authority.claims),
            }
            if authority is not None
            else None
        ),
    }


def _input_projection(
    loaded: Mapping[str, LoadedReceipt | None],
    evaluation: _Evaluation,
) -> dict[str, Any]:
    return {
        "pilot": {
            "release": _descriptor(loaded["pilot.release"], evaluation),
            "rollback": _descriptor(loaded["pilot.rollback"], evaluation),
        },
        "contentLifecycle": {
            environment: _descriptor(loaded[f"content.{environment}"], evaluation)
            for environment in ENVIRONMENTS
        },
        "localEnvGreenMatrix": _descriptor(
            loaded["local_env.green_matrix"],
            evaluation,
            role="supporting",
        ),
        "recoveryUat": {
            platform: _descriptor(
                loaded[f"recovery.{platform}"],
                evaluation,
                role="diagnostic_only",
            )
            for platform in ("ios", "android")
        },
        "nightlyArtifact": _descriptor(
            loaded["nightly"],
            evaluation,
            role="diagnostic_only",
        ),
        "prodSim": _descriptor(
            loaded["prod_sim"],
            evaluation,
            role="diagnostic_only",
        ),
        "prodHosted": {
            "rolloutReadback": _descriptor(
                loaded["prod.rollout_readback"],
                evaluation,
            ),
            "rollbackReadback": _descriptor(
                loaded["prod.rollback_readback"],
                evaluation,
            ),
            "soakReadback": _descriptor(
                loaded["prod.soak_readback"],
                evaluation,
            ),
        },
    }


def evaluate_final_acceptance(
    inputs: FinalAcceptanceInputs,
    *,
    max_age_seconds: int = 86_400,
    now: datetime | None = None,
    artifact_closure_verifier: ArtifactClosureVerifier = validate_historical_release_snapshot,
    provider_readiness_verifier: ProviderReadinessVerifier = (
        verify_canonical_provider_readiness
    ),
    attestation_verifier: AttestationVerifier = verify_github_actions_receipt,
    soak_authority_verifier: SoakAuthorityVerifier = verify_canonical_hosted_prod_soak,
) -> dict[str, Any]:
    """Validate frozen diagnostics without granting release qualification."""

    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    evaluation = _Evaluation()
    evaluation.block(
        "NON_PROMOTABLE",
        "final_acceptance",
        "frozen diagnostic final acceptance cannot qualify a release; use QualificationFact "
        "and qualified_prod admission",
    )
    artifact_root = _resolve_artifact_root(evaluation, inputs.artifact_root)
    loaded = {
        label: (
            None
            if label in RETIRED_GITHUB_ATTESTED_EVIDENCE_KINDS and path is None
            else _load_receipt(evaluation, label=label, path=path)
        )
        for label, path in inputs.receipt_paths().items()
    }

    seen_paths: dict[Path, str] = {}
    for label, receipt in loaded.items():
        if receipt is None:
            continue
        previous = seen_paths.get(receipt.path)
        if previous is not None and {
            previous,
            label,
        } != {"prod.rollout_readback", "prod.rollback_readback"}:
            evaluation.block(
                "DIGEST_MISMATCH",
                label,
                f"one file cannot satisfy both {previous} and {label}",
            )
        seen_paths[receipt.path] = label
        if label != "candidate":
            _reject_self_asserted_authority(
                evaluation,
                receipt,
                allow_prod_sim_non_promotable=label == "prod_sim",
            )

    manifest, closure = _artifact_closure(
        evaluation,
        artifact_root=artifact_root,
        manifest_receipt=loaded["candidate"],
        verifier=artifact_closure_verifier,
        provider_verifier=provider_readiness_verifier,
        now=current_time,
        max_age_seconds=max_age_seconds,
    )
    pilot = _pilot_identity(
        evaluation,
        loaded["pilot.release"],
        loaded["pilot.rollback"],
        now=current_time,
    )
    for environment in ENVIRONMENTS:
        _validate_content_lifecycle(
            evaluation,
            loaded[f"content.{environment}"],
            environment=environment,
            pilot=pilot,
            now=current_time,
            max_age_seconds=max_age_seconds,
        )
    _validate_green_matrix(
        evaluation,
        loaded["local_env.green_matrix"],
        pilot=pilot,
        now=current_time,
        max_age_seconds=max_age_seconds,
    )
    _validate_manifest_bound_acceptance_inputs(
        evaluation,
        artifact_root=artifact_root,
        manifest=manifest,
        loaded=loaded,
    )
    for kind in sorted(RETIRED_GITHUB_ATTESTED_EVIDENCE_KINDS):
        _reject_retired_ci_evidence(
            evaluation,
            loaded[kind],
            kind=kind,
        )
    _validate_prod_sim(
        evaluation,
        loaded["prod_sim"],
        manifest=manifest,
        pilot=pilot,
        now=current_time,
        max_age_seconds=max_age_seconds,
    )
    _verify_authority(
        evaluation,
        loaded["prod_sim"],
        manifest=manifest,
        verifier=attestation_verifier,
    )
    hosted_receipt = _validate_hosted_readbacks(
        evaluation,
        rollout=loaded["prod.rollout_readback"],
        rollback=loaded["prod.rollback_readback"],
        artifact_root=artifact_root,
        manifest=manifest,
        now=current_time,
        max_age_seconds=max_age_seconds,
    )
    if hosted_receipt is not None:
        deployment_artifact = hosted_receipt["artifactDigest"]
        prod_sim = loaded["prod_sim"]
        prod_sim_release = (
            prod_sim.payload.get("releaseEvidence")
            if prod_sim is not None
            else None
        )
        if prod_sim is not None and (
            not isinstance(prod_sim_release, Mapping)
            or prod_sim_release.get("artifactDigest") != deployment_artifact
        ):
            evaluation.block(
                "DIGEST_MISMATCH",
                "prod_sim",
                "signed prod-sim evidence differs from the hosted deployment artifact",
            )
    _validate_soak_authority(
        evaluation,
        soak=loaded["prod.soak_readback"],
        rollout_receipt=hosted_receipt,
        manifest=manifest,
        verifier=soak_authority_verifier,
    )

    blockers = sorted(
        evaluation.blockers,
        key=lambda item: (item["input"], item["code"], item["message"]),
    )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "generatedAt": current_time.isoformat().replace("+00:00", "Z"),
        "verdict": BLOCKED_VERDICT,
        "artifactClosure": closure,
        "pilot": pilot,
        "inputs": _input_projection(loaded, evaluation),
        "blockers": blockers,
    }
    payload["receiptDigest"] = _canonical_digest(payload)
    return payload


def write_final_acceptance(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write the final typed receipt without following symlinks."""

    output = path.expanduser()
    if output.is_symlink():
        raise ValueError("final acceptance output must not be a symlink")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, output)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
