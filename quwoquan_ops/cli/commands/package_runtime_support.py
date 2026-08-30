"""Support helpers for the stackctl runtime packaging command.

This module owns receipt redaction, official Skill publication, immutable
package identity readback, and compile preflight. The command module keeps
only orchestration so both files remain within the governed line budget.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]
_RECEIPT_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|password|token|private[_-]?key|credential)s?\b"
    r"\s*[:=]\s*(\S+)"
)


def _receipt_safe_text(value: str) -> str:
    """Redact assignment-shaped output before it reaches disposable receipts."""

    return _RECEIPT_SECRET_ASSIGNMENT.sub(
        lambda match: match.group(0)[: -len(match.group(1))] + "<redacted>",
        str(value or ""),
    )


def _receipt_safe_step(step: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(step)
    for key in ("stdout", "stderr"):
        if key in sanitized:
            sanitized[key] = _receipt_safe_text(str(sanitized[key] or ""))
    return sanitized


def _build_official_skill_package_publication(
    env_name: str,
    target_name: str,
    *,
    package_source_root: Path,
    package_environment: dict[str, str],
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Build the signed official Skill publication into assistant packaging.

    The immutable candidate and the mutable dev session share one builder, so a
    packaged candidate always carries the ``release.json`` and
    ``trusted_public_keys.json`` that ``stackctl up`` reads back as the Skill
    trust root. A second local build here would sign the same assets without
    that material and leave immutable up unable to establish trust.
    """
    from quwoquan_ops.cli import stackctl as _stackctl
    from quwoquan_ops.cli.lib.assistant_skill_package_artifact import (
        build_official_skill_package_publication,
    )

    if output_root is None:
        output_root = (
            _stackctl.service_deployment_package_dir(
                env_name, "assistant-service", target=target_name
            )
            / "skill-packages"
        )
    environment = dict(package_environment)
    if not str(environment.get("QWQ_PACKAGE_SOURCE_REVISION") or "").strip():
        environment["QWQ_PACKAGE_SOURCE_REVISION"] = "0" * 40
    step = build_official_skill_package_publication(
        env_name,
        target_name,
        package_source_root=package_source_root,
        package_environment=environment,
        output_root=output_root,
    )
    step["argv"] = [item for item in step["argv"] if "PRIVATE" not in item]
    return step


def _validate_runtime_package_identity_readback(
    *,
    report_path: Path,
    fingerprint_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """Read back one non-claiming package identity from all three artifacts."""
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.deployment_candidate_manifest import manifest

    payloads: dict[str, dict[str, Any]] = {}
    for label, path in (
        ("package report", report_path),
        ("package fingerprint", fingerprint_path),
        ("candidate manifest", manifest_path),
    ):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} is missing or unsafe")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{label} is unreadable: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{label} must be a JSON object")
        if "formalRelease" in payload:
            raise ValueError(f"{label} must not claim formalRelease")
        payloads[label] = payload

    identities: dict[str, dict[str, Any]] = {}
    for label, payload in payloads.items():
        classification = payload.get("releaseInputClassification")
        graph_digest = payload.get("contractGraphDigest")
        if classification not in _stackctl.RELEASE_INPUT_CLASSIFICATIONS:
            raise ValueError(f"{label} releaseInputClassification is invalid")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", str(graph_digest or "")) is None:
            raise ValueError(f"{label} contractGraphDigest is invalid")
        identities[label] = {
            "releaseInputClassification": str(classification),
            "contractGraphDigest": str(graph_digest),
            "graphqlReadRegistry": payload.get("graphqlReadRegistry"),
            "appLaunchBundle": payload.get("appLaunchBundle"),
        }
        if not isinstance(identities[label]["graphqlReadRegistry"], dict):
            raise ValueError(f"{label} graphqlReadRegistry is invalid")
    expected = identities["candidate manifest"]
    if any(identity != expected for identity in identities.values()):
        raise ValueError("runtime package release/ContractGraph identity drifted")
    manifest._validate_prod_hosted_release_evidence_currentness(
        payloads["candidate manifest"], candidate_root=manifest_path.parent
    )
    return expected


def _runtime_package_report_path(report_ref: str) -> Path:
    """Resolve the package report file from the canonical report directory."""
    import quwoquan_ops.cli.stackctl as _stackctl

    normalized = str(report_ref or "").strip()
    if not normalized:
        raise ValueError("package report directory is required")
    report_dir = Path(normalized)
    if not report_dir.is_absolute():
        report_dir = _stackctl.ROOT / report_dir
    return report_dir / "report.json"


def _run_runtime_compile_preflight(
    *,
    package_environment: dict[str, str],
    source_root: Path = _REPO_ROOT,
) -> tuple[list[dict[str, Any]], str]:
    """Compile every runtime entrypoint before package/image materialization."""
    import quwoquan_ops.cli.stackctl as _stackctl

    checks = [
        (
            "compile-entrypoints:go",
            [
                "go",
                "test",
                "-run",
                "^$",
                "./services/.../cmd/...",
                "./control-plane/.../cmd/...",
            ],
            source_root / "quwoquan_service",
        ),
        (
            # The composition root lives outside services/ and control-plane/,
            # so the glob above never reaches it; packaging an image whose only
            # entrypoint does not compile is exactly what this step forbids.
            # Compiled as a test binary like its sibling above rather than built:
            # `go build` stamps VCS provenance, which needs a git-capable
            # environment that packaging deliberately does not hand to its steps,
            # and the package's provenance is bound from the source revision
            # anyway.
            "compile-entrypoint:service-core",
            [
                "go",
                "test",
                "-run",
                "^$",
                "./cmd/service-core",
            ],
            source_root / "quwoquan_service",
        ),
        (
            "compile-entrypoints:recommendation-python",
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "import ast,pathlib;"
                    "root=pathlib.Path('services/recommendation-service');"
                    "files=sorted(root.rglob('*.py'));"
                    "assert files, 'recommendation Python source set is empty';"
                    "[(ast.parse(path.read_text(encoding='utf-8'), filename=str(path))) "
                    "for path in files]"
                ),
            ],
            source_root / "quwoquan_service",
        ),
    ]
    reports: list[dict[str, Any]] = []
    for name, argv, cwd in checks:
        result = _stackctl.run(argv, cwd=cwd, env=package_environment)
        reports.append(
            _receipt_safe_step(
                {
                    "name": name,
                    "argv": argv,
                    "exitCode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
        )
        if result.returncode != 0:
            return (
                reports,
                _receipt_safe_text(result.stderr.strip())
                or _receipt_safe_text(result.stdout.strip())
                or f"{name} failed",
            )
    return reports, ""
