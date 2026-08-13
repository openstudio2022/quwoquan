"""Canonical non-promotable Assistant Skill package publication for test_live."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import utc_now, write_json
from .local_assistant_skill_package_keys import (
    KEY_ID,
    prepare_local_assistant_skill_package_keys,
)
from .output_paths import deployment_target_path

SCHEMA = "stackctl.local_assistant_skill_package_publication.v1"
TARGET = "alpha-local"
ENVIRONMENT = "alpha"
CONTAINER = "quwoquan_alpha_test_live-assistant-service-1"
PUBLISHER = "service:local-managed-assistant-skill-publisher:alpha-local"


def _run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail[-2000:])
    return result


def _source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    )
    if not files:
        raise RuntimeError("canonical Assistant Skill package source is empty")
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def _private_key_base64(private_pem: Path, public_keys_json: str) -> str:
    result = subprocess.run(
        ["openssl", "pkey", "-in", str(private_pem), "-outform", "DER"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or len(result.stdout) < 32:
        raise RuntimeError("local-managed Assistant Skill private key is invalid")
    seed = result.stdout[-32:]
    public = base64.b64decode(json.loads(public_keys_json)[KEY_ID], validate=True)
    if len(public) != 32:
        raise RuntimeError("local-managed Assistant Skill public key is invalid")
    return base64.b64encode(seed + public).decode("ascii")


def _container_runtime() -> tuple[
    dict[str, str],
    Path,
    str,
    list[tuple[str, str, bool]],
]:
    result = subprocess.run(
        ["docker", "inspect", CONTAINER],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Alpha Assistant runtime container is unavailable")
    rows = json.loads(result.stdout)
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError("Alpha Assistant runtime identity is ambiguous")
    row = rows[0]
    values = {
        item.partition("=")[0]: item.partition("=")[2]
        for item in (row.get("Config") or {}).get("Env") or []
        if "=" in item
    }
    labels = (row.get("Config") or {}).get("Labels") or {}
    if (
        values.get("APP_ENV") != ENVIRONMENT
        or labels.get("com.docker.compose.project")
        != "quwoquan_alpha_test_live"
        or labels.get("com.docker.compose.service") != "assistant-service"
    ):
        raise RuntimeError(
            "Assistant Skill publication requires non-promotable Alpha test_live"
        )
    config_mounts = [
        Path(item["Source"])
        for item in row.get("Mounts") or []
        if item.get("Destination") == "/etc/qwq-config"
        and item.get("Type") == "bind"
        and item.get("RW") is False
    ]
    if len(config_mounts) != 1:
        raise RuntimeError("Alpha Assistant config root identity is ambiguous")
    networks = list((row.get("NetworkSettings") or {}).get("Networks") or {})
    expected_network = "quwoquan_alpha_test_live_default"
    if expected_network not in networks:
        raise RuntimeError("Alpha Assistant runtime network identity is ambiguous")
    mounts = [
        (
            str(item["Source"]),
            str(item["Destination"]),
            item.get("RW") is not True,
        )
        for item in row.get("Mounts") or []
        if item.get("Type") == "bind"
    ]
    return values, config_mounts[0], expected_network, mounts


def _run_go(
    arguments: list[str],
    *,
    repo_root: Path,
    service_root: Path,
    environment: dict[str, str],
    network: str,
    mounts: list[tuple[str, str, bool]],
) -> subprocess.CompletedProcess[str]:
    local_go = shutil.which("go")
    if local_go and Path(local_go).resolve().is_file():
        return _run(
            [local_go, *arguments],
            cwd=service_root,
            environment={**os.environ, **environment},
        )
    deploy_root = deployment_target_path(TARGET)
    deploy_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=deploy_root / "secrets" / "assistant-skill-package",
        prefix=".publisher-env-",
        delete=False,
    ) as stream:
        env_file = Path(stream.name)
        for key, value in sorted(environment.items()):
            if "\n" in value or "\r" in value:
                raise RuntimeError(
                    f"Assistant Skill publisher environment is multiline: {key}"
                )
            stream.write(f"{key}={value}\n")
    os.chmod(env_file, 0o600)
    try:
        command = [
                "docker",
                "run",
                "--rm",
                "--network",
                network,
                "--env-file",
                str(env_file),
                "-v",
                f"{repo_root}:{repo_root}",
                "-v",
                f"{deploy_root}:{deploy_root}",
                "-w",
                str(service_root),
        ]
        for source, destination, readonly in mounts:
            command.extend(
                [
                    "-v",
                    f"{source}:{destination}" + (":ro" if readonly else ""),
                ]
            )
        command.extend(["golang:1.24-bookworm", "go", *arguments])
        return _run(
            command,
            cwd=repo_root,
            environment=os.environ.copy(),
        )
    finally:
        env_file.unlink(missing_ok=True)


def _run_runtime_publisher(
    *,
    repo_root: Path,
    service_root: Path,
    output_root: Path,
    publication_ref: str,
    config_version: str,
    environment: dict[str, str],
    network: str,
    mounts: list[tuple[str, str, bool]],
) -> subprocess.CompletedProcess[str]:
    binary = (
        repo_root
        / ".qwq_output/env/alpha/local/assistant-skill-package-publisher"
        / "assistant-skill-package-publish"
    )
    binary.parent.mkdir(parents=True, exist_ok=True)
    _run_go(
        [
            "build",
            "-buildvcs=false",
            "-o",
            str(binary),
            "./services/assistant-service/cmd/skill-package-publish",
        ],
        repo_root=repo_root,
        service_root=service_root,
        environment={
            **environment,
            "CGO_ENABLED": "0",
            "GOOS": "linux",
            "GOARCH": "arm64",
        },
        network=network,
        mounts=mounts,
    )
    runtime_binary = "/tmp/assistant-skill-package-publish-current"
    runtime_assets = "/tmp/qwq-skill-package-publication"
    subprocess.run(
        ["docker", "exec", CONTAINER, "rm", "-rf", runtime_binary, runtime_assets],
        check=False,
        capture_output=True,
    )
    try:
        _run(
            ["docker", "cp", str(binary), f"{CONTAINER}:{runtime_binary}"],
            cwd=repo_root,
            environment=os.environ.copy(),
            timeout=60,
        )
        _run(
            [
                "docker",
                "cp",
                str(output_root) + "/.",
                f"{CONTAINER}:{runtime_assets}",
            ],
            cwd=repo_root,
            environment=os.environ.copy(),
            timeout=60,
        )
        return _run(
            [
                "docker",
                "exec",
                CONTAINER,
                runtime_binary,
                "--env",
                ENVIRONMENT,
                "--config-root",
                "/etc/qwq-config",
                "--config-version",
                config_version,
                "--asset-root",
                runtime_assets,
                "--publication-ref",
                publication_ref,
                "--timeout-seconds",
                "180",
            ],
            cwd=repo_root,
            environment=os.environ.copy(),
            timeout=240,
        )
    finally:
        subprocess.run(
            [
                "docker",
                "exec",
                CONTAINER,
                "rm",
                "-rf",
                runtime_binary,
                runtime_assets,
            ],
            check=False,
            capture_output=True,
        )


def publish_alpha_test_live(report_dir: Path) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    service_root = repo_root / "quwoquan_service"
    source_root = (
        service_root
        / "services/assistant-service/resources/skill_packages/official"
    )
    source_digest = _source_digest(source_root)
    keys = prepare_local_assistant_skill_package_keys(ENVIRONMENT, TARGET)
    runtime_environment, config_root, network, mounts = _container_runtime()
    if (
        runtime_environment.get(
            "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON"
        )
        != keys.public_keys_json
    ):
        raise RuntimeError(
            "Alpha Assistant runtime trust root does not match target-scoped publisher"
        )
    public_key_digest = "sha256:" + hashlib.sha256(
        keys.public_keys_json.encode()
    ).hexdigest()
    build_id = (
        "alpha-test-live-"
        + source_digest.removeprefix("sha256:")[:16]
        + "-"
        + public_key_digest.removeprefix("sha256:")[:12]
        + "-b2"
    )
    output_root = deployment_target_path(
        TARGET,
        "artifacts",
        "assistant-skill-package",
    )
    publication_ref = f"releases/{build_id}/publication.json"
    publication_path = output_root / publication_ref
    command_id = "assistant-skill-package-" + build_id
    environment = dict(runtime_environment)
    environment[
        "ASSISTANT_SKILL_PACKAGE_SIGNING_PRIVATE_KEY_BASE64"
    ] = _private_key_base64(keys.private_key_path, keys.public_keys_json)
    build_report: dict[str, Any]
    if publication_path.exists():
        build_report = {
            "buildId": build_id,
            "publicationRef": publication_ref,
            "replayed": True,
        }
    else:
        head = _run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            environment=environment,
            timeout=30,
        ).stdout.strip()
        # Mongo BSON preserves milliseconds. Whole-second provenance keeps the
        # signed digest stable across the mandatory Stage/GetRelease roundtrip.
        built_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        built = _run_go(
            [
                "run",
                "./services/assistant-service/cmd/skill-package-build",
                "--source-root",
                str(source_root),
                "--output-root",
                str(output_root),
                "--package-version",
                "0.0."
                + str(int(source_digest.removeprefix("sha256:")[:8], 16)),
                "--build-id",
                build_id,
                "--source-repository",
                "quwoquan",
                "--source-revision",
                head + "+" + source_digest,
                "--built-at",
                built_at,
                "--key-id",
                KEY_ID,
                "--command-id",
                command_id,
                "--expected-revision",
                "0",
                "--activated-by",
                PUBLISHER,
            ],
            repo_root=repo_root,
            service_root=service_root,
            environment=environment,
            network=network,
            mounts=mounts,
        )
        build_report = json.loads(built.stdout)
        build_report["replayed"] = False
    publication_digest = "sha256:" + hashlib.sha256(
        publication_path.read_bytes()
    ).hexdigest()
    published = _run_runtime_publisher(
        repo_root=repo_root,
        service_root=service_root,
        output_root=output_root,
        publication_ref=publication_ref,
        config_version=runtime_environment.get("CONFIG_VERSION", ""),
        environment=environment,
        network=network,
        mounts=mounts,
    )
    activation = json.loads(published.stdout)
    receipt = {
        "schema": SCHEMA,
        "target": TARGET,
        "environment": ENVIRONMENT,
        "publisherIdentity": PUBLISHER,
        "signingKeyId": KEY_ID,
        "publicKeyDigest": public_key_digest,
        "privateKeyPath": str(keys.private_key_path),
        "sourceRoot": str(source_root),
        "sourceDigest": source_digest,
        "build": build_report,
        "publicationRef": publication_ref,
        "publicationDigest": publication_digest,
        "activation": activation,
        "nonPromotable": True,
        "promotionEligibility": "GATE_BLOCK",
        "immutableCandidateAuthority": False,
        "prodAuthority": False,
        "createdAt": utc_now(),
    }
    write_json(report_dir / "assistant-skill-package-publication.json", receipt)
    return receipt
