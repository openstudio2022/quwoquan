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
from .openssl3_resolver import OpenSSL3Executable, resolve_openssl3
from .output_paths import deployment_target_path

SCHEMA = "stackctl.local_assistant_skill_package_publication.v1"
PACKAGED_RELEASE_SCHEMA = "stackctl.assistant_skill_package_release.v1"
TARGET = "alpha-local"
ENVIRONMENT = "alpha"
CONTAINER = "quwoquan_alpha_test_live-assistant-service-1"
PUBLISHER = "service:local-managed-assistant-skill-publisher:alpha-local"
_REQUIRED_ASSET_KINDS = frozenset(
    {
        "manifest",
        "catalog",
        "activation",
        "input",
        "input_schema",
        "context",
        "capability",
        "orchestration",
        "trigger",
        "memory",
        "presentation",
        "presentation_template",
        "evaluation",
        "prompt",
        "replay",
    }
)


def _validated_public_keys(public_keys_json: str) -> dict[str, bytes]:
    try:
        payload = json.loads(public_keys_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("assistant Skill package trusted public keys are invalid") from exc
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError("assistant Skill package trusted public keys are empty")
    decoded: dict[str, bytes] = {}
    for key_id, encoded in payload.items():
        if not isinstance(key_id, str) or not key_id.strip() or not isinstance(encoded, str):
            raise RuntimeError("assistant Skill package trusted public key identity is invalid")
        try:
            public_key = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise RuntimeError("assistant Skill package trusted public key is invalid") from exc
        if len(public_key) != 32:
            raise RuntimeError("assistant Skill package trusted public key is invalid")
        decoded[key_id.strip()] = public_key
    return decoded


def derive_official_skill_package_release_identity(
    *,
    environment: str,
    target: str,
    source_digest: str,
    source_revision: str,
    public_keys_json: str,
    signing_key_id: str = KEY_ID,
) -> dict[str, str]:
    valid_target = (
        environment in {"alpha", "beta", "gamma"}
        and target == f"{environment}-local"
    ) or (environment == "prod" and target == "prod-hosted")
    if not valid_target:
        raise RuntimeError("assistant Skill package release target identity is invalid")
    if not source_digest.startswith("sha256:") or len(source_digest) != 71:
        raise RuntimeError("assistant Skill package source digest is invalid")
    revision = source_revision.strip()
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise RuntimeError("assistant Skill package source revision is invalid")
    trusted = _validated_public_keys(public_keys_json)
    signing_key_id = signing_key_id.strip()
    if not signing_key_id or signing_key_id not in trusted:
        raise RuntimeError("assistant Skill package signing key is absent from the trust root")
    trust_digest = "sha256:" + hashlib.sha256(public_keys_json.encode("utf-8")).hexdigest()
    build_id = "-".join(
        (
            environment,
            source_digest.removeprefix("sha256:")[:16],
            revision[:12],
            trust_digest.removeprefix("sha256:")[:12],
            hashlib.sha256(signing_key_id.encode("utf-8")).hexdigest()[:8],
        )
    )
    return {
        "buildId": build_id,
        "commandId": "official-bootstrap-" + build_id,
        "signingKeyId": signing_key_id,
        "trustedPublicKeysDigest": trust_digest,
    }


def materialize_packaged_official_skill_release(
    *,
    output_root: Path,
    environment: str,
    target: str,
    source_digest: str,
    source_revision: str,
    public_keys_json: str,
    build_report: dict[str, Any],
    signing_key_id: str = KEY_ID,
) -> dict[str, str]:
    identity = derive_official_skill_package_release_identity(
        environment=environment,
        target=target,
        source_digest=source_digest,
        source_revision=source_revision,
        public_keys_json=public_keys_json,
        signing_key_id=signing_key_id,
    )
    build_id = identity["buildId"]
    publication_ref = f"releases/{build_id}/publication.json"
    if build_report.get("buildId") != build_id or build_report.get("publicationRef") != publication_ref:
        raise RuntimeError("assistant Skill package build report identity drifted")
    publication_path = output_root / publication_ref
    if publication_path.is_symlink() or not publication_path.is_file():
        raise RuntimeError("assistant Skill package publication is missing or unsafe")
    try:
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("assistant Skill package publication is unreadable") from exc
    release = publication.get("release") if isinstance(publication, dict) else None
    if not isinstance(release, dict):
        raise RuntimeError("assistant Skill package release descriptor is missing")
    if (
        publication.get("commandId") != identity["commandId"]
        or release.get("packageId") != "assistant.session.skills"
        or release.get("releaseDigest") != build_report.get("releaseDigest")
        or (release.get("provenance") or {}).get("buildId") != build_id
        or (release.get("provenance") or {}).get("sourceRevision") != source_revision
        or (release.get("signature") or {}).get("keyId") != identity["signingKeyId"]
    ):
        raise RuntimeError("assistant Skill package release identity drifted")
    assets = release.get("assets")
    if not isinstance(assets, list) or not assets:
        raise RuntimeError("assistant Skill package release assets are empty")
    kinds: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise RuntimeError("assistant Skill package asset descriptor is invalid")
        locator = str(asset.get("locator") or "")
        prefix = "skill-package://official/"
        if not locator.startswith(prefix):
            raise RuntimeError("assistant Skill package asset locator is invalid")
        relative = locator.removeprefix(prefix)
        asset_path = output_root / relative
        if (
            asset_path.is_symlink()
            or not asset_path.is_file()
            or asset_path.resolve().parent == output_root.resolve()
            or not asset_path.resolve().is_relative_to(output_root.resolve())
        ):
            raise RuntimeError("assistant Skill package asset path is missing or unsafe")
        digest = "sha256:" + hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if digest != asset.get("assetDigest"):
            raise RuntimeError("assistant Skill package asset digest mismatch")
        kinds.add(str(asset.get("kind") or ""))
    if kinds != _REQUIRED_ASSET_KINDS:
        raise RuntimeError("assistant Skill package required asset kinds are incomplete")
    trusted_path = output_root / "trusted_public_keys.json"
    trusted_path.write_text(public_keys_json + "\n", encoding="utf-8")
    os.chmod(trusted_path, 0o644)
    metadata = {
        "schema": PACKAGED_RELEASE_SCHEMA,
        "environment": environment,
        "target": target,
        "packageId": "assistant.session.skills",
        "buildId": build_id,
        "publicationRef": publication_ref,
        "releaseDigest": str(release["releaseDigest"]),
        "sourceDigest": source_digest,
        "sourceRevision": source_revision,
        "signingKeyId": identity["signingKeyId"],
        "trustedPublicKeysDigest": identity["trustedPublicKeysDigest"],
        "trustedPublicKeysRef": "trusted_public_keys.json",
    }
    write_json(output_root / "release.json", metadata)
    return metadata


def load_packaged_assistant_skill_package_trust(
    *,
    candidate_root: Path,
    environment: str,
    target: str,
) -> str:
    package_root = (
        candidate_root
        / "packages"
        / "services"
        / "assistant-service"
        / "skill-packages"
    )
    metadata_path = package_root / "release.json"
    trusted_path = package_root / "trusted_public_keys.json"
    if (
        package_root.is_symlink()
        or metadata_path.is_symlink()
        or trusted_path.is_symlink()
        or not metadata_path.is_file()
        or not trusted_path.is_file()
    ):
        raise RuntimeError("packaged assistant Skill release trust material is missing or unsafe")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("packaged assistant Skill release identity is unreadable") from exc
    required = {
        "schema",
        "environment",
        "target",
        "packageId",
        "buildId",
        "publicationRef",
        "releaseDigest",
        "sourceDigest",
        "sourceRevision",
        "signingKeyId",
        "trustedPublicKeysDigest",
        "trustedPublicKeysRef",
    }
    if not isinstance(metadata, dict) or set(metadata) != required:
        raise RuntimeError("packaged assistant Skill release identity fields mismatch")
    if (
        metadata.get("schema") != PACKAGED_RELEASE_SCHEMA
        or metadata.get("environment") != environment
        or metadata.get("target") != target
        or metadata.get("packageId") != "assistant.session.skills"
        or not str(metadata.get("signingKeyId") or "").strip()
        or metadata.get("trustedPublicKeysRef") != "trusted_public_keys.json"
    ):
        raise RuntimeError("packaged assistant Skill release target identity mismatch")
    public_keys_json = trusted_path.read_text(encoding="utf-8").strip()
    trusted = _validated_public_keys(public_keys_json)
    signing_key_id = str(metadata["signingKeyId"])
    if signing_key_id not in trusted:
        raise RuntimeError("packaged assistant Skill release trust root is incomplete")
    actual_digest = "sha256:" + hashlib.sha256(public_keys_json.encode("utf-8")).hexdigest()
    if actual_digest != metadata.get("trustedPublicKeysDigest"):
        raise RuntimeError("packaged assistant Skill release trust root digest mismatch")
    publication_path = package_root / str(metadata["publicationRef"])
    if publication_path.is_symlink() or not publication_path.is_file():
        raise RuntimeError("packaged assistant Skill publication is missing or unsafe")
    publication = json.loads(publication_path.read_text(encoding="utf-8"))
    release = publication.get("release") if isinstance(publication, dict) else None
    if (
        not isinstance(release, dict)
        or publication.get("commandId")
        != "official-bootstrap-" + str(metadata["buildId"])
        or release.get("releaseDigest") != metadata.get("releaseDigest")
        or (release.get("signature") or {}).get("keyId") != signing_key_id
    ):
        raise RuntimeError("packaged assistant Skill publication identity drifted")
    kinds: set[str] = set()
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            raise RuntimeError("packaged assistant Skill asset descriptor is invalid")
        locator = str(asset.get("locator") or "")
        prefix = "skill-package://official/"
        if not locator.startswith(prefix):
            raise RuntimeError("packaged assistant Skill asset locator is invalid")
        asset_path = package_root / locator.removeprefix(prefix)
        if (
            asset_path.is_symlink()
            or not asset_path.is_file()
            or not asset_path.resolve().is_relative_to(package_root.resolve())
        ):
            raise RuntimeError("packaged assistant Skill asset is missing or unsafe")
        actual_asset_digest = "sha256:" + hashlib.sha256(
            asset_path.read_bytes()
        ).hexdigest()
        if actual_asset_digest != asset.get("assetDigest"):
            raise RuntimeError("packaged assistant Skill asset digest mismatch")
        kinds.add(str(asset.get("kind") or ""))
    if kinds != _REQUIRED_ASSET_KINDS:
        raise RuntimeError("packaged assistant Skill asset kind closure is incomplete")
    try:
        signature = base64.b64decode(
            str((release.get("signature") or {}).get("value") or ""),
            validate=True,
        )
    except (ValueError, base64.binascii.Error) as exc:
        raise RuntimeError("packaged assistant Skill signature is invalid") from exc
    if len(signature) != 64:
        raise RuntimeError("packaged assistant Skill signature is invalid")
    return public_keys_json


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


def _private_key_base64(
    private_pem: Path,
    public_keys_json: str,
    *,
    openssl: OpenSSL3Executable | None = None,
) -> str:
    selected = openssl or resolve_openssl3()
    result = subprocess.run(
        selected.argv("pkey", "-in", str(private_pem), "-outform", "DER"),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or len(result.stdout) < 32:
        raise RuntimeError("local-managed Assistant Skill private key is invalid")
    seed = result.stdout[-32:]
    trusted = _validated_public_keys(public_keys_json)
    public = trusted.get(KEY_ID)
    if public is None:
        raise RuntimeError("local-managed Assistant Skill public key is absent")
    private_key = seed + public
    if len(private_key) != 64:
        raise RuntimeError("local-managed Assistant Skill private key material is invalid")
    return base64.b64encode(private_key).decode("ascii")


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
    openssl = resolve_openssl3()
    keys = prepare_local_assistant_skill_package_keys(
        ENVIRONMENT, TARGET, openssl=openssl
    )
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
    ] = _private_key_base64(
        keys.private_key_path, keys.public_keys_json, openssl=openssl
    )
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
