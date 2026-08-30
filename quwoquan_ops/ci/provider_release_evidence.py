#!/usr/bin/env python3
"""Execute Prod Provider cells and package the exact evidence closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.render_environment_release_receipt import (
    RELEASE_CLOSURE_PATHS,
    archive_exact_files,
    validate_release_closure_sources,
)
from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance
from quwoquan_ops.cli.lib.output_paths import output_root
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    sha256_file,
    validate_manifest,
)

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
IMMUTABLE_REF = re.compile(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")
METADATA_SCHEMA = "provider-release-evidence-binding"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _digest_json(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _release_identity(
    manifest_path: Path,
    release_evidence_ref: str,
) -> tuple[dict[str, Any], str]:
    manifest = _load(manifest_path)
    validate_manifest(manifest, allowed_statuses={"released"})
    candidate = str(manifest.get("candidateId") or "")
    if DIGEST.fullmatch(candidate) is None:
        raise ValueError("Provider qualification requires a released candidateId")
    if (
        IMMUTABLE_REF.fullmatch(release_evidence_ref) is None
        or "/release-artifact@" not in release_evidence_ref
    ):
        raise ValueError("release evidence ref must be an exact immutable GHCR ref")
    source = manifest.get("source")
    artifacts = manifest.get("environmentArtifacts")
    prod_artifact = artifacts.get("prod") if isinstance(artifacts, Mapping) else None
    images = prod_artifact.get("images") if isinstance(prod_artifact, Mapping) else None
    if not isinstance(source, Mapping) or not isinstance(images, Mapping) or not images:
        raise ValueError("Prod environment artifact source/images are incomplete")
    services: list[dict[str, str]] = []
    for service, descriptor in sorted(images.items()):
        digest = descriptor.get("digest") if isinstance(descriptor, Mapping) else None
        if not isinstance(service, str) or DIGEST.fullmatch(str(digest or "")) is None:
            raise ValueError("Prod environment artifact image identity is incomplete")
        services.append({"service": service, "imageDigest": str(digest)})
    source_sha = str(source.get("gitSha") or "")
    current_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if source_sha != current_sha:
        raise ValueError("release evidence source does not match checked-out revision")
    image_digest = _digest_json(
        {
            "schema": "provider-conformance-prod-candidate-image-set",
            "commit": source_sha,
            "services": services,
        }
    )
    return manifest, image_digest


def _write_github_output(path: str, values: Mapping[str, str]) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.writelines(f"{key}={value}\n" for key, value in values.items())


def command_identity(args: argparse.Namespace) -> int:
    manifest, image_digest = _release_identity(
        args.release_manifest,
        args.release_evidence_ref,
    )
    source = manifest["source"]
    payload = {
        "sourceGitSha": source["gitSha"],
        "producerWorkflowRunId": source["workflowRunId"],
        "releaseEvidenceRef": args.release_evidence_ref,
        "releaseEvidenceDigest": args.release_evidence_ref.rsplit("@", 1)[1],
        "candidateId": manifest["candidateId"],
        "artifactDigest": manifest["artifactDigest"],
        "expectedImageDigest": image_digest,
    }
    _write_github_output(args.github_output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def command_execute_prod(args: argparse.Namespace) -> int:
    _, expected_image_digest = _release_identity(
        args.release_manifest,
        args.release_evidence_ref,
    )
    compiled, issues = governance.load_and_compile()
    if issues:
        raise ValueError("; ".join(issue.render() for issue in issues))
    selected = compiled.get("selectedBindings")
    prod = selected.get("prod") if isinstance(selected, Mapping) else None
    if not isinstance(prod, Mapping) or not prod:
        raise ValueError("compiled Provider bindings contain no Prod selection")
    runtime_env = {
        **os.environ,
        "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST": expected_image_digest,
        "QWQ_PROVIDER_CONFORMANCE_REQUIRE_PROMOTABLE": "true",
    }
    expected_prod_cells = {
        cell
        for cell in provider_conformance.expected_required_cell_keys(compiled)
        if cell[1] == "prod"
    }
    executed = 0
    for capability_id in sorted(cell[0] for cell in expected_prod_cells):
        binding = prod.get(capability_id)
        if (
            not isinstance(binding, Mapping)
            or binding.get("state") != "enabled"
            or not governance.requires_provider_conformance(binding)
        ):
            raise ValueError(
                f"Prod Provider binding is not executable: {capability_id}"
            )
        adapter_id = str(binding.get("adapter_id") or "")
        if not adapter_id:
            raise ValueError(f"Prod Provider binding has no adapter: {capability_id}")
        report_dir = args.report_dir / capability_id
        command = [
            sys.executable,
            "quwoquan_ops/cli/stackctl.py",
            "provider-conformance",
            "--adapter-id",
            adapter_id,
            "--capability-id",
            str(capability_id),
            "--env",
            "prod",
            "--layer",
            "user_acceptance",
            "--execute",
            "--image-digest",
            expected_image_digest,
            "--report-dir",
            str(report_dir),
        ]
        subprocess.run(command, cwd=ROOT, env=runtime_env, check=True)
        executed += 1
    if executed != len(expected_prod_cells):
        raise ValueError(
            "Prod Provider execution must produce exactly the compiled required "
            f"cells: expected={len(expected_prod_cells)}, got={executed}"
        )
    print(f"provider_release_evidence: executed {executed} Prod Remote cells")
    return 0


def command_execute_nonprod(args: argparse.Namespace) -> int:
    _, expected_image_digest = _release_identity(
        args.release_manifest,
        args.release_evidence_ref,
    )
    compiled, issues = governance.load_and_compile()
    if issues:
        raise ValueError("; ".join(issue.render() for issue in issues))
    expected = provider_conformance.expected_required_cell_keys(compiled)
    runtime_env = {
        **os.environ,
        "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST": expected_image_digest,
        "QWQ_PROVIDER_CONFORMANCE_REQUIRE_PROMOTABLE": "true",
    }
    executed = 0
    expected_nonprod_cells = {
        cell for cell in expected if cell[1] in provider_conformance.ENVIRONMENTS
    }
    for environment in provider_conformance.ENVIRONMENTS:
        expected_environment = {cell for cell in expected if cell[1] == environment}
        if not expected_environment:
            raise ValueError(
                f"{environment} Provider matrix contains no compiled required cells"
            )
        subprocess.run(
            [
                sys.executable,
                "quwoquan_ops/cli/stackctl.py",
                "provider-conformance",
                "--environment-matrix",
                "--env",
                environment,
                "--execute",
                "--report-dir",
                str(args.report_dir / environment),
            ],
            cwd=ROOT,
            env=runtime_env,
            check=True,
        )
        executed += len(expected_environment)
    if executed != len(expected_nonprod_cells):
        raise ValueError(
            "nonprod Provider execution must produce exactly the compiled required "
            f"cells: expected={len(expected_nonprod_cells)}, got={executed}"
        )
    print(f"provider_release_evidence: executed {executed} nonprod cells")
    return 0


def command_package(args: argparse.Namespace) -> int:
    manifest, expected_image_digest = _release_identity(
        args.release_manifest,
        args.release_evidence_ref,
    )
    previous = os.environ.get("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST")
    os.environ["QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"] = expected_image_digest
    try:
        evidence_root = output_root()
        report, issues = provider_conformance.load_validate_and_derive(
            root=evidence_root,
        )
        compiled, governance_issues = governance.load_and_compile()
        evidence, load_issues = provider_conformance.load_evidence(evidence_root)
    finally:
        if previous is None:
            os.environ.pop("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST", None)
        else:
            os.environ["QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"] = previous
    readiness = [
        issue
        for environment in provider_conformance.EVIDENCE_ENVIRONMENTS
        for issue in provider_conformance.readiness_issues(
            report,
            environment=environment,
        )
    ]
    all_issues = [
        *issues,
        *(issue.render() for issue in governance_issues),
        *load_issues,
        *provider_conformance.exact_required_cell_issues(
            evidence,
            compiled=compiled,
        ),
        *readiness,
    ]
    if all_issues:
        raise ValueError(
            "executed Provider evidence is not release-ready: " + "; ".join(all_issues)
        )
    expected_cells = provider_conformance.expected_required_cell_keys(compiled)
    evidence_paths = sorted(Path(str(item["_source"])) for item in evidence)
    if len(evidence_paths) != len(expected_cells):
        raise ValueError(
            "executed Provider evidence set must contain exactly the compiled "
            f"required cells: expected={len(expected_cells)}, got={len(evidence_paths)}"
        )
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    copied_dirs: set[Path] = set()
    for evidence_path in evidence_paths:
        run_dir = evidence_path.parent.resolve()
        if run_dir in copied_dirs:
            continue
        copied_dirs.add(run_dir)
        relative = run_dir.relative_to(evidence_root.resolve())
        shutil.copytree(run_dir, output_dir / relative, dirs_exist_ok=True)
    release_root = args.release_root.resolve(strict=True)
    if args.release_manifest.resolve(strict=True) != release_root / "manifest.json":
        raise ValueError(
            "release manifest must be the canonical file under release root"
        )
    test_evidence = manifest.get("testEvidence")
    evidence_closure = (
        test_evidence.get("evidence") if isinstance(test_evidence, Mapping) else None
    )
    closure_descriptors = (
        evidence_closure.get("files") if isinstance(evidence_closure, Mapping) else None
    )
    if not isinstance(closure_descriptors, Mapping) or set(closure_descriptors) != set(
        RELEASE_CLOSURE_PATHS
    ):
        raise ValueError("released manifest closure is incomplete")
    closure_sources: dict[str, Path] = {}
    for label, expected_path in RELEASE_CLOSURE_PATHS.items():
        descriptor = closure_descriptors.get(label)
        if (
            not isinstance(descriptor, Mapping)
            or descriptor.get("path") != expected_path
            or DIGEST.fullmatch(str(descriptor.get("digest") or "")) is None
        ):
            raise ValueError(
                f"released manifest closure descriptor is invalid: {label}"
            )
        source_path = release_root / expected_path
        if (
            source_path.is_symlink()
            or not source_path.is_file()
            or sha256_file(source_path) != descriptor["digest"]
        ):
            raise ValueError(f"released manifest closure digest mismatch: {label}")
        closure_sources[label] = source_path
    lifecycle_sources = {
        environment: closure_sources[f"content-lifecycle-{environment}"]
        for environment in ("alpha", "beta", "gamma")
    }
    validate_release_closure_sources(
        pilot_release_attestation=closure_sources["pilot-release"],
        pilot_rollback_attestation=closure_sources["pilot-rollback"],
        lifecycle_exits=lifecycle_sources,
        green_matrix=closure_sources["green-matrix"],
    )
    archive_exact_files(
        archive_root=output_dir,
        files={
            label: (path, RELEASE_CLOSURE_PATHS[label])
            for label, path in closure_sources.items()
        },
    )
    source = manifest["source"]
    metadata = {
        "schema": METADATA_SCHEMA,
        "sourceGitSha": source["gitSha"],
        "producerWorkflowRunId": source["workflowRunId"],
        "releaseEvidenceRef": args.release_evidence_ref,
        "releaseEvidenceDigest": args.release_evidence_ref.rsplit("@", 1)[1],
        "candidateId": manifest["candidateId"],
        "artifactDigest": manifest["artifactDigest"],
        "expectedImageDigest": expected_image_digest,
        "evidenceCount": len(evidence_paths),
        "environments": list(provider_conformance.EVIDENCE_ENVIRONMENTS),
        "readinessEnvironment": "alpha,beta,gamma,prod",
    }
    (output_dir / "provider-candidate.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_github_output(
        args.github_output,
        {
            "expected_image_digest": expected_image_digest,
            "evidence_count": str(len(evidence_paths)),
        },
    )
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("identity", "execute-nonprod", "execute-prod", "package"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--release-manifest", required=True, type=Path)
        subparser.add_argument("--release-evidence-ref", required=True)
        if command == "identity":
            subparser.add_argument("--github-output", default="")
        elif command in {"execute-nonprod", "execute-prod"}:
            subparser.add_argument("--report-dir", required=True, type=Path)
        else:
            subparser.add_argument("--release-root", required=True, type=Path)
            subparser.add_argument("--output-dir", required=True, type=Path)
            subparser.add_argument("--github-output", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "identity":
            return command_identity(args)
        if args.command == "execute-nonprod":
            return command_execute_nonprod(args)
        if args.command == "execute-prod":
            return command_execute_prod(args)
        return command_package(args)
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        TypeError,
        ValueError,
    ) as error:
        print(f"provider_release_evidence: GATE_BLOCK: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
