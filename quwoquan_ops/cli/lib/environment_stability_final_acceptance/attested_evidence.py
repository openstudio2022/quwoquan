"""GitHub OIDC attestation 验证与 CI / prod-sim 证据校验（自原单文件逐字搬移）。"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.prod import oci_supply_chain
from quwoquan_ops.ci.release_evidence_reader import (
    DIGEST_PATTERN,
    sha256_file,
)

from quwoquan_ops.cli.lib.environment_stability_final_acceptance.model import (
    AttestationVerifier,
    CommandRunner,
    GITHUB_ATTESTED_WORKFLOW_BY_KIND,
    LoadedReceipt,
    RETIRED_GITHUB_ATTESTED_EVIDENCE_KINDS,
    VerifiedAuthority,
    _Evaluation,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.receipt_io import (
    _canonical_digest,
    _schema,
    _timestamp,
)


def verify_github_actions_receipt(
    path: Path,
    kind: str,
    manifest: Mapping[str, Any],
    *,
    runner: CommandRunner = subprocess.run,
) -> VerifiedAuthority:
    """Verify exact receipt bytes with GitHub's trusted OIDC attestation chain."""

    repository = str(manifest["source"]["repository"])
    if oci_supply_chain.REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise ValueError("manifest repository is not canonical owner/repository")
    if kind not in GITHUB_ATTESTED_WORKFLOW_BY_KIND:
        raise ValueError(f"unsupported GitHub-attested evidence kind: {kind}")
    workflow = f"{repository}/{GITHUB_ATTESTED_WORKFLOW_BY_KIND[kind]}"
    receipt_payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(receipt_payload, Mapping):
        raise TypeError("GitHub-attested receipt root must be an object")
    receipt_candidate = (
        (receipt_payload.get("releaseEvidence") or {}).get("candidateId")
        if kind == "prod_sim"
        else receipt_payload.get("candidateId")
    )
    if receipt_candidate != manifest["candidateId"]:
        raise ValueError("GitHub-attested receipt candidate differs from manifest")
    result = runner(
        [
            "gh",
            "attestation",
            "verify",
            str(path),
            "--repo",
            repository,
            "--signer-workflow",
            workflow,
            "--cert-oidc-issuer",
            oci_supply_chain.OIDC_ISSUER,
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise RuntimeError(f"gh attestation verify failed: {detail[-1200:]}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("gh attestation verify returned invalid JSON") from exc
    expected_hex = sha256_file(path).removeprefix("sha256:")
    if not _attestation_has_subject_digest(payload, expected_hex):
        raise RuntimeError("GitHub attestation does not bind the exact receipt bytes")
    return VerifiedAuthority(
        authority="github-actions-oidc",
        subject_digest=f"sha256:{expected_hex}",
        verification_digest=_canonical_digest(payload),
        claims=frozenset(
            {
                "receipt_bytes",
                kind,
                f"repository:{repository}",
                f"workflow:{workflow}",
                f"issuer:{oci_supply_chain.OIDC_ISSUER}",
                f"candidate:{manifest['candidateId']}",
            }
        ),
    )


def _attestation_has_subject_digest(value: Any, expected_hex: str) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        try:
            subjects = item["verificationResult"]["statement"]["subject"]
        except (KeyError, TypeError):
            continue
        if isinstance(subjects, list) and any(
            isinstance(subject, Mapping)
            and isinstance(subject.get("digest"), Mapping)
            and subject["digest"].get("sha256") == expected_hex
            for subject in subjects
        ):
            return True
    return False


def _verify_authority(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    manifest: Mapping[str, Any] | None,
    verifier: AttestationVerifier,
) -> None:
    if receipt is None or manifest is None:
        return
    try:
        verified = verifier(receipt.path, receipt.label, manifest)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            receipt.label,
            f"cryptographic receipt verification failed: {exc}",
        )
        return
    repository = str(manifest["source"]["repository"])
    workflow_path = GITHUB_ATTESTED_WORKFLOW_BY_KIND[receipt.label]
    required_claims = {
        "receipt_bytes",
        receipt.label,
        f"repository:{repository}",
        f"workflow:{repository}/{workflow_path}",
        f"issuer:{oci_supply_chain.OIDC_ISSUER}",
        f"candidate:{manifest['candidateId']}",
    }
    if (
        verified.authority != "github-actions-oidc"
        or verified.subject_digest != receipt.digest
        or DIGEST_PATTERN.fullmatch(verified.verification_digest) is None
        or not required_claims.issubset(verified.claims)
    ):
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            receipt.label,
            "trusted verifier result does not bind exact receipt bytes and evidence kind",
        )
        return
    evaluation.authority[receipt.label] = verified


def _reject_retired_ci_evidence(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    kind: str,
) -> None:
    """对签发 workflow 已退役的旧输入保持 fail-closed。"""

    if kind not in RETIRED_GITHUB_ATTESTED_EVIDENCE_KINDS:
        raise ValueError(f"evidence kind is not retired: {kind}")
    if receipt is None:
        return
    evaluation.block(
        "UNSUPPORTED_INPUT",
        receipt.label,
        "retired recovery/nightly receipts are not accepted by final acceptance",
    )
    evaluation.block(
        "NON_PROMOTABLE",
        receipt.label,
        "local Environment Ops evidence cannot impersonate hosted OIDC; "
        "physical-device package acceptance belongs to QualificationFact",
    )


def _validate_prod_sim(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    manifest: Mapping[str, Any] | None,
    pilot: Mapping[str, str] | None,
    now: datetime,
    max_age_seconds: int,
) -> None:
    if receipt is None:
        return
    if not _schema(
        evaluation,
        receipt,
        "prod-hosted-first-party-prevalidation-report",
    ):
        return
    payload = receipt.payload
    eligibility = payload.get("releaseEligibility")
    release = payload.get("releaseEvidence")
    if not (
        payload.get("target") == "prod-hosted"
        and payload.get("mode") == "prevalidate"
        and payload.get("dataMode") == "isolated"
        and payload.get("scope") == "first-party"
        and payload.get("dryRun") is False
        and (payload.get("containerDeployment") or {}).get("status") == "passed"
        and isinstance(eligibility, Mapping)
        and eligibility.get("status") == "GATE_BLOCK"
        and eligibility.get("promotable") is False
        and eligibility.get("ledgerWritten") is False
        and eligibility.get("receiptWritten") is False
        and payload.get("issues") == []
    ):
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "prod-sim is not the canonical non-promotable isolated rehearsal",
        )
    if manifest is not None and (
        not isinstance(release, Mapping)
        or release.get("candidateId") != manifest["candidateId"]
        or (release.get("source") or {}).get("gitSha")
        != manifest["source"]["gitSha"]
    ):
        evaluation.block(
            "IDENTITY_MISMATCH",
            receipt.label,
            "prod-sim rehearsal differs from ReleaseEvidenceManifest",
        )
    if pilot is not None and (
        payload.get("releaseId") != pilot["releaseId"]
        or payload.get("releaseDigest") != pilot["releaseDigest"]
    ):
        evaluation.block(
            "DIGEST_MISMATCH",
            receipt.label,
            "prod-sim content release differs from pilot-003",
        )
    _timestamp(
        evaluation,
        receipt,
        ("endedAt",),
        now=now,
        max_age_seconds=max_age_seconds,
    )
