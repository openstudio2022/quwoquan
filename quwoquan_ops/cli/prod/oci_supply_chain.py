#!/usr/bin/env python3
"""Extract BuildKit SBOMs and verify signed OCI supply-chain claims.

BuildKit's structured SBOM/provenance prove that the immutable image index
contains both predicates.  GitHub artifact attestations add the cryptographic
signature, trusted OIDC issuer and signer-workflow identity.  Release callers
must require both layers; human-readable ``imagetools inspect`` output is never
accepted as verification evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

IMAGE_REF_PATTERN = re.compile(r"ghcr\.io/[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
PREDICATES = {
    "slsaProvenance": "https://slsa.dev/provenance/v1",
    "spdxSbom": "https://spdx.dev/Document/v2.3",
}
CANONICAL_SIGNER_WORKFLOWS = frozenset(
    {
        "service_pipeline.yml",
        "deploy-prod-auto.yml",
    }
)

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _run(
    argv: Sequence[str],
    *,
    timeout_seconds: int | None = None,
    runner: CommandRunner = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    return runner(
        list(argv),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )


def _load_json_output(result: subprocess.CompletedProcess[str], label: str) -> Any:
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise RuntimeError(f"{label} failed: {detail[-1200:]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{label} returned invalid JSON") from error


def _find_spdx(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("spdxVersion") == "SPDX-2.3" and value.get("SPDXID"):
            return value
        for child in value.values():
            found = _find_spdx(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_spdx(child)
            if found is not None:
                return found
    return None


def _has_slsa_provenance(value: Any) -> bool:
    if isinstance(value, dict):
        if (
            isinstance(value.get("builder"), dict)
            and isinstance(value.get("buildType"), str)
            and bool(value.get("buildType"))
            and isinstance(value.get("materials"), list)
        ):
            return True
        return any(_has_slsa_provenance(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_slsa_provenance(child) for child in value)
    return False


def inspect_buildkit_attestations(
    ref: str,
    *,
    timeout_seconds: int | None = None,
    runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    """Return the image's structured SPDX document after validating both predicates."""

    if IMAGE_REF_PATTERN.fullmatch(ref) is None:
        raise ValueError(
            "OCI supply-chain verification requires an exact GHCR digest ref"
        )
    deadline = (
        time.monotonic() + timeout_seconds if timeout_seconds is not None else None
    )

    def remaining() -> int | None:
        if deadline is None:
            return None
        value = int(deadline - time.monotonic())
        if value < 1:
            raise subprocess.TimeoutExpired(
                "OCI BuildKit attestation verification", timeout_seconds
            )
        return value

    sbom_result = _run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            ref,
            "--format",
            "{{json .SBOM}}",
        ],
        timeout_seconds=remaining(),
        runner=runner,
    )
    sbom_payload = _load_json_output(sbom_result, "structured BuildKit SBOM lookup")
    spdx = _find_spdx(sbom_payload)
    if (
        spdx is None
        or not isinstance(spdx.get("packages"), list)
        or not spdx["packages"]
    ):
        raise RuntimeError("OCI image has no structured SPDX SBOM")

    provenance_result = _run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            ref,
            "--format",
            "{{json .Provenance}}",
        ],
        timeout_seconds=remaining(),
        runner=runner,
    )
    provenance = _load_json_output(
        provenance_result, "structured BuildKit provenance lookup"
    )
    if not _has_slsa_provenance(provenance):
        raise RuntimeError("OCI image has no structured SLSA provenance")
    return spdx


def _subject_matches_ref(result: Any, ref: str) -> bool:
    if not isinstance(result, list) or not result:
        return False
    image_name, digest = ref.rsplit("@", 1)
    expected_hex = digest.removeprefix("sha256:")
    for item in result:
        try:
            subjects = item["verificationResult"]["statement"]["subject"]
        except (KeyError, TypeError):
            continue
        if not isinstance(subjects, list):
            continue
        for subject in subjects:
            if not isinstance(subject, dict):
                continue
            subject_name = str(subject.get("name") or "").removeprefix("oci://")
            subject_digest = subject.get("digest")
            if (
                subject_name == image_name
                and isinstance(subject_digest, dict)
                and subject_digest.get("sha256") == expected_hex
            ):
                return True
    return False


def verify_signed_attestations(
    ref: str,
    *,
    repository: str,
    signer_workflow: str,
    source_digest: str = "",
    timeout_seconds: int | None = None,
    runner: CommandRunner = subprocess.run,
) -> dict[str, str]:
    """Cryptographically verify signed provenance and SBOM bundles from OCI."""

    if IMAGE_REF_PATTERN.fullmatch(ref) is None:
        raise ValueError(
            "signed attestation verification requires an exact GHCR digest ref"
        )
    if REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise ValueError("signed attestation verification requires owner/repository")
    canonical_signers = {
        f"{repository}/.github/workflows/{workflow}"
        for workflow in CANONICAL_SIGNER_WORKFLOWS
    }
    if "/release-artifact@" not in ref:
        canonical_signers = {f"{repository}/.github/workflows/service_pipeline.yml"}
    if signer_workflow not in canonical_signers:
        raise ValueError("signed attestation signer workflow is not canonical")
    if source_digest and GIT_SHA_PATTERN.fullmatch(source_digest) is None:
        raise ValueError("signed attestation source digest is invalid")

    deadline = (
        time.monotonic() + timeout_seconds if timeout_seconds is not None else None
    )

    def remaining() -> int | None:
        if deadline is None:
            return None
        value = int(deadline - time.monotonic())
        if value < 1:
            raise subprocess.TimeoutExpired(
                "OCI signed attestation verification", timeout_seconds
            )
        return value

    verified: dict[str, str] = {}
    for name, predicate_type in PREDICATES.items():
        argv = [
            "gh",
            "attestation",
            "verify",
            f"oci://{ref}",
            "--repo",
            repository,
            "--signer-workflow",
            signer_workflow,
            "--cert-oidc-issuer",
            OIDC_ISSUER,
            "--bundle-from-oci",
            "--predicate-type",
            predicate_type,
            "--format",
            "json",
        ]
        if source_digest:
            argv.extend(["--source-digest", source_digest])
        result = _run(
            argv,
            timeout_seconds=remaining(),
            runner=runner,
        )
        payload = _load_json_output(result, f"signed {name} verification")
        if not _subject_matches_ref(payload, ref):
            raise RuntimeError(f"signed {name} does not bind the exact image digest")
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        verified[name] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return verified


def verify_oci_supply_chain(
    ref: str,
    *,
    repository: str,
    signer_workflow: str,
    source_digest: str = "",
    timeout_seconds: int | None = None,
    runner: CommandRunner = subprocess.run,
) -> dict[str, str]:
    deadline = (
        time.monotonic() + timeout_seconds if timeout_seconds is not None else None
    )

    def remaining() -> int | None:
        if deadline is None:
            return None
        value = int(deadline - time.monotonic())
        if value < 1:
            raise subprocess.TimeoutExpired(
                "OCI supply-chain verification", timeout_seconds
            )
        return value

    inspect_buildkit_attestations(
        ref,
        timeout_seconds=remaining(),
        runner=runner,
    )
    return verify_signed_attestations(
        ref,
        repository=repository,
        signer_workflow=signer_workflow,
        source_digest=source_digest,
        timeout_seconds=remaining(),
        runner=runner,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract-sbom")
    extract.add_argument("--ref", required=True)
    extract.add_argument("--output", required=True, type=Path)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--ref", required=True)
    verify.add_argument("--repository", required=True)
    verify.add_argument("--signer-workflow", required=True)
    verify.add_argument("--source-digest", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "extract-sbom":
            spdx = inspect_buildkit_attestations(args.ref)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(spdx, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(str(args.output))
        else:
            verified = verify_oci_supply_chain(
                args.ref,
                repository=args.repository,
                signer_workflow=args.signer_workflow,
                source_digest=args.source_digest,
            )
            print(
                json.dumps(
                    {"status": "passed", "attestations": verified}, sort_keys=True
                )
            )
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
