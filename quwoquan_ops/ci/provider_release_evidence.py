#!/usr/bin/env python3
"""Execute Prod Provider cells and package the exact evidence closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance
from quwoquan_ops.cli.lib.output_paths import output_root
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    validate_manifest,
)


DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
IMMUTABLE_REF = re.compile(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")
METADATA_SCHEMA = "provider-release-evidence-binding"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _digest_json(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _component_identity(
    manifest_path: Path,
    component_evidence_ref: str,
) -> tuple[dict[str, Any], str]:
    manifest = _load(manifest_path)
    validate_manifest(manifest, allowed_statuses={"component-ready"})
    if manifest.get("candidateId") is not None:
        raise ValueError("Provider qualification must precede candidate sealing")
    if IMMUTABLE_REF.fullmatch(component_evidence_ref) is None:
        raise ValueError("component evidence ref must be an exact immutable GHCR ref")
    source = manifest.get("source")
    images = manifest.get("images")
    if not isinstance(source, Mapping) or not isinstance(images, Mapping) or not images:
        raise ValueError("component evidence source/images are incomplete")
    services: list[dict[str, str]] = []
    for service, descriptor in sorted(images.items()):
        digest = descriptor.get("digest") if isinstance(descriptor, Mapping) else None
        if not isinstance(service, str) or DIGEST.fullmatch(str(digest or "")) is None:
            raise ValueError("component evidence image identity is incomplete")
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
        raise ValueError("component evidence source does not match checked-out revision")
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
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def command_identity(args: argparse.Namespace) -> int:
    manifest, image_digest = _component_identity(
        args.component_manifest,
        args.component_evidence_ref,
    )
    source = manifest["source"]
    payload = {
        "sourceGitSha": source["gitSha"],
        "componentEvidenceRef": args.component_evidence_ref,
        "componentEvidenceDigest": args.component_evidence_ref.rsplit("@", 1)[1],
        "expectedImageDigest": image_digest,
    }
    _write_github_output(args.github_output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def command_execute_prod(args: argparse.Namespace) -> int:
    _, expected_image_digest = _component_identity(
        args.component_manifest,
        args.component_evidence_ref,
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
    }
    executed = 0
    for capability_id, binding in sorted(prod.items()):
        if not isinstance(binding, Mapping) or binding.get("state") != "enabled":
            continue
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
    if executed == 0:
        raise ValueError("Prod Provider execution selected zero enabled capabilities")
    print(f"provider_release_evidence: executed {executed} Prod Remote cells")
    return 0


def command_package(args: argparse.Namespace) -> int:
    manifest, expected_image_digest = _component_identity(
        args.component_manifest,
        args.component_evidence_ref,
    )
    previous = os.environ.get("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST")
    os.environ["QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"] = expected_image_digest
    try:
        evidence_root = output_root()
        report, issues = provider_conformance.load_validate_and_derive(
            root=evidence_root,
        )
    finally:
        if previous is None:
            os.environ.pop("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST", None)
        else:
            os.environ["QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"] = previous
    readiness = provider_conformance.readiness_issues(report, environment="prod")
    all_issues = [*issues, *readiness]
    if all_issues:
        raise ValueError(
            "executed Provider evidence is not release-ready: " + "; ".join(all_issues)
        )
    evidence_paths = provider_conformance.evidence_files(evidence_root)
    if not evidence_paths:
        raise ValueError("executed Provider evidence set is empty")
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
    source = manifest["source"]
    metadata = {
        "schema": METADATA_SCHEMA,
        "sourceGitSha": source["gitSha"],
        "componentEvidenceRef": args.component_evidence_ref,
        "componentEvidenceDigest": args.component_evidence_ref.rsplit("@", 1)[1],
        "expectedImageDigest": expected_image_digest,
        "evidenceCount": len(evidence_paths),
        "environments": list(provider_conformance.EVIDENCE_ENVIRONMENTS),
        "readinessEnvironment": "prod",
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
    for command in ("identity", "execute-prod", "package"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--component-manifest", required=True, type=Path)
        subparser.add_argument("--component-evidence-ref", required=True)
        if command == "identity":
            subparser.add_argument("--github-output", default="")
        elif command == "execute-prod":
            subparser.add_argument("--report-dir", required=True, type=Path)
        else:
            subparser.add_argument("--output-dir", required=True, type=Path)
            subparser.add_argument("--github-output", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "identity":
            return command_identity(args)
        if args.command == "execute-prod":
            return command_execute_prod(args)
        return command_package(args)
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        print(f"provider_release_evidence: GATE_BLOCK: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
