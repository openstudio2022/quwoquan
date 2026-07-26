#!/usr/bin/env python3
"""从服务自治配置入口生成主干发布输入；不维护服务配置模板副本。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.render_runtime_config import render_workload


ARTIFACT_NAME = "mainline-release-artifact"
DOMAIN_SERVICES = tuple(
    sorted(
        path.name
        for path in (ROOT / "quwoquan_service/services").iterdir()
        if path.is_dir() and (path / "config/schema.yaml").is_file()
    )
)
RELEASE_SERVICES = DOMAIN_SERVICES + ("platform-ops-service",)
DEPLOYED_SERVICES = RELEASE_SERVICES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate mainline release manifest from autonomous prod entries.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--run-number", required=True, type=int)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--registry", default="ghcr.io")
    parser.add_argument("--image-version", default="")
    parser.add_argument("--config-version", default="")
    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def compute_versions(run_number: int) -> tuple[str, str]:
    stamp = dt.datetime.now(dt.timezone.utc)
    return (
        f"1.{stamp.strftime('%Y%m%d')}.{run_number}",
        f"v{stamp.strftime('%Y.%m.%d')}.{run_number}",
    )


def render_release_snapshot(service: str, config_version: str) -> dict[str, Any]:
    del config_version  # release ID belongs to the manifest; CONFIG_VERSION is the content digest.
    if service not in RELEASE_SERVICES:
        raise ValueError(f"unknown release service: {service}")
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "config.yaml"
        render_workload(ROOT, "prod", service, output)
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


def write_summary(
    path: Path,
    *,
    image_version: str,
    config_version: str,
    image_repositories: dict[str, str],
) -> None:
    lines = [
        "## Mainline Release Artifact",
        "",
        f"- `image_version`: `{image_version}`",
        f"- `release_id`: `{config_version}`",
        "- `CONFIG_VERSION`: 每个服务最终配置的 sha256 摘要",
        "- `status`: `build-input`（全部 OCI digest 与 attestations 收齐后才可部署）",
        "",
        "### Required images",
        *[
            f"- `{service}`: `{repository}:{image_version}`"
            for service, repository in image_repositories.items()
        ],
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    image_version = args.image_version.strip()
    release_id = args.config_version.strip()
    if not image_version or not release_id:
        image_version, release_id = compute_versions(args.run_number)

    release_files: dict[str, str] = {}
    release_file_digests: dict[str, str] = {}
    for service in RELEASE_SERVICES:
        relative_path = Path("packages/services") / service / "config/config.yaml"
        snapshot_path = output_dir / relative_path
        write_release_snapshot(snapshot_path, render_release_snapshot(service, release_id))
        release_files[service] = relative_path.as_posix()
        release_file_digests[service] = sha256_file(snapshot_path)

    registry = args.registry.rstrip("/")
    repository = args.repository.strip("/")
    image_repositories = {
        service: f"{registry}/{repository}/{service}" for service in DEPLOYED_SERVICES
    }
    manifest = {
        "schema": "mainline-release-artifact",
        "artifactName": ARTIFACT_NAME,
        "status": "build-input",
        "generatedAt": utc_now(),
        "source": {
            "gitSha": args.git_sha,
            "runNumber": args.run_number,
            "repository": args.repository,
        },
        "versions": {"imageVersion": image_version, "configVersion": release_id},
        "requiredImages": list(DEPLOYED_SERVICES),
        "imageRepositories": image_repositories,
        "images": {},
        "releaseFiles": release_files,
        "releaseFileDigests": release_file_digests,
    }
    write_json(output_dir / "manifest.json", manifest)
    write_summary(
        output_dir / "summary.md",
        image_version=image_version,
        config_version=release_id,
        image_repositories=image_repositories,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
