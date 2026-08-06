#!/usr/bin/env python3
"""从服务自治入口生成 canonical ReleaseEvidenceManifest 构建输入。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.immutable_image_composition import (
    first_party_service_names,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    APPLICATION_PACKAGES,
    ENVIRONMENTS,
    SCHEMA,
    TEST_LAYERS,
    seal_manifest,
    validate_manifest,
)
from quwoquan_ops.cli.render_runtime_config import render_workload


RELEASE_SERVICES = first_party_service_names(ROOT)
DOMAIN_SERVICES = tuple(
    service for service in RELEASE_SERVICES if service != "platform-ops-service"
)
DEPLOYED_SERVICES = RELEASE_SERVICES
TRANSPORT_TAG_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate canonical release evidence from autonomous prod entries.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--run-number", required=True, type=int)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--registry", default="ghcr.io")
    parser.add_argument(
        "--image-transport-tag",
        default="",
        help="Registry transport tag only; release identity remains the OCI digest.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_tree_digest(git_sha: str) -> str:
    algorithm = subprocess.run(
        ["git", "rev-parse", "--show-object-format"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    tree = subprocess.run(
        ["git", "rev-parse", "--verify", f"{git_sha}^{{tree}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if algorithm.returncode != 0 or tree.returncode != 0:
        detail = tree.stderr.strip() or algorithm.stderr.strip()
        raise ValueError(f"cannot resolve source tree digest: {detail}")
    name = algorithm.stdout.strip()
    digest = tree.stdout.strip()
    if name not in {"sha1", "sha256"}:
        raise ValueError(f"unsupported git object format: {name!r}")
    return f"{name}:{digest}"


def render_release_snapshot(service: str, environment: str) -> dict[str, Any]:
    if service not in RELEASE_SERVICES:
        raise ValueError(f"unknown release service: {service}")
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unknown release environment: {environment}")
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "config.yaml"
        render_workload(ROOT, environment, service, output)
        payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"rendered config for {service} must be a mapping")
    return payload


def dump_yaml_like(payload: dict[str, Any]) -> str:
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return text if text.endswith("\n") else text + "\n"


def write_release_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml_like(payload), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def write_summary(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "## Release Evidence Manifest",
        "",
        f"- `candidateId`: `{manifest['candidateId']}`",
        f"- `artifactDigest`: `{manifest['artifactDigest']}`",
        "- `status`: `build-input`（全部不可变摘要与证据收齐后才可部署）",
        "",
        "### Image transport references",
        *[
            f"- `{service}`: `{descriptor['transportRef']}`"
            for service, descriptor in manifest["images"].items()
        ],
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    transport_tag = args.image_transport_tag.strip() or f"sha-{args.git_sha}"
    if transport_tag == "latest" or TRANSPORT_TAG_PATTERN.fullmatch(transport_tag) is None:
        raise ValueError("image transport tag must be fixed and registry-safe")

    configuration_packages: dict[str, dict[str, dict[str, str]]] = {}
    for environment in ENVIRONMENTS:
        environment_packages: dict[str, dict[str, str]] = {}
        for service in RELEASE_SERVICES:
            relative_path = (
                Path("packages/environments")
                / environment
                / "services"
                / service
                / "config/config.yaml"
            )
            snapshot_path = output_dir / relative_path
            write_release_snapshot(
                snapshot_path,
                render_release_snapshot(service, environment),
            )
            environment_packages[service] = {
                "path": relative_path.as_posix(),
                "digest": sha256_file(snapshot_path),
            }
        configuration_packages[environment] = environment_packages

    registry = args.registry.rstrip("/")
    repository = args.repository.strip("/")
    images = {
        service: {
            "repository": f"{registry}/{repository}/{service}",
            "transportRef": f"{registry}/{repository}/{service}:{transport_tag}",
        }
        for service in DEPLOYED_SERVICES
    }
    required_evidence = {
        "images": list(DEPLOYED_SERVICES),
        "configurationPackages": {
            environment: list(RELEASE_SERVICES) for environment in ENVIRONMENTS
        },
        "applicationPackages": {
            environment: list(APPLICATION_PACKAGES[environment])
            for environment in ENVIRONMENTS
        },
        "contractGraphDigest": True,
        "providerEvidence": True,
        "testEvidence": list(TEST_LAYERS),
        "environmentReceipts": list(ENVIRONMENTS),
        "rolloutReceipt": True,
        "rollbackReceipt": True,
    }
    manifest = seal_manifest(
        {
            "schema": SCHEMA,
            "candidateId": None,
            "status": "build-input",
            "generatedAt": utc_now(),
            "source": {
                "gitSha": args.git_sha,
                "treeDigest": resolve_tree_digest(args.git_sha),
                "repository": args.repository,
                "workflowRunId": str(os.environ.get("GITHUB_RUN_ID") or args.run_number),
                "sourceArchiveDigest": None,
            },
            "artifactDigest": None,
            "images": images,
            "configurationPackages": configuration_packages,
            "applicationPackages": {environment: {} for environment in ENVIRONMENTS},
            "contractGraphDigest": None,
            "requiredEvidence": required_evidence,
            "testEvidence": {},
            "providerEvidence": {},
            "environmentReceipts": {},
            "rolloutReceipt": None,
            "rollbackReceipt": None,
            "blockers": [
                "immutable-image-evidence-pending",
                "whole-application-evidence-pending",
            ],
            "missingEvidence": [
                *(f"images.{service}.digest" for service in DEPLOYED_SERVICES),
                *(
                    f"applicationPackages.{environment}.{surface}"
                    for environment in ENVIRONMENTS
                    for surface in APPLICATION_PACKAGES[environment]
                ),
                "contractGraphDigest",
                "providerEvidence",
                "testEvidence",
                *(f"environmentReceipts.{environment}" for environment in ENVIRONMENTS),
                "rollbackReceipt.ready",
                "rolloutReceipt",
                "rollbackReceipt.outcome",
            ],
        }
    )
    validate_manifest(manifest, allowed_statuses={"build-input"})
    write_json(output_dir / "manifest.json", manifest)
    write_summary(output_dir / "summary.md", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
