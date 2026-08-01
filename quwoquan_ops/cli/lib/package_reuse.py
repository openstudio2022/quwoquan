"""以当前部署输入和完整 runtime package 摘要判定 package 是否可复用。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Iterable, Sequence

from quwoquan_ops.cli.lib.output_paths import (
    PACKAGE_ROOT_OVERRIDE_ENV,
    active_deployment_candidate,
    app_deployment_package_dir,
    legal_static_deployment_package_dir,
    runtime_shared_deployment_package_dir,
    service_deployment_package_dir,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    RUNTIME_CANDIDATE_TYPE,
    validate_candidate_manifest,
)


ROOT = Path(__file__).resolve().parents[3]
FINGERPRINT_NAME = "package-fingerprint.json"
FINGERPRINT_SCHEMA = "stackctl-package-reuse-fingerprint"
DEPLOYMENT_INPUT_ROOTS = (
    "quwoquan_app",
    "quwoquan_ops",
    "quwoquan_service",
    "quwoquan_data",
    "specs",
    ".github",
    "Makefile",
)
_FINGERPRINT_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "target",
        "candidateType",
        "includeServices",
        "servicePackages",
        "reportRef",
        "baselineId",
        "sourceRevision",
        "workspaceStatusDigest",
        "deploymentInputs",
        "packageContent",
    }
)
_DIGEST_FIELDS = frozenset({"digest", "fileCount"})
_DEPLOYMENT_INPUT_FIELDS = frozenset({"roots", *_DIGEST_FIELDS})


def fingerprint_path(env_name: str, target_name: str) -> Path:
    return app_deployment_package_dir(env_name, target=target_name) / FINGERPRINT_NAME


def _digest_record(
    entries: Iterable[tuple[str, str, bytes]],
) -> tuple[str, int]:
    """Digest logical path, entry kind and bytes without relying on mtimes."""

    digest = hashlib.sha256()
    count = 0
    for logical_path, kind, content in entries:
        path_bytes = logical_path.encode("utf-8")
        kind_bytes = kind.encode("ascii")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(kind_bytes).to_bytes(8, "big"))
        digest.update(kind_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        count += 1
    return f"sha256:{digest.hexdigest()}", count


def _path_entry(path: Path) -> tuple[str, bytes]:
    if path.is_symlink():
        return "symlink", os.readlink(path).encode("utf-8")
    if path.is_file():
        return "file", path.read_bytes()
    if not path.exists():
        return "missing", b""
    raise ValueError(f"deployment input is not a file or symlink: {path}")


def deployment_input_digest() -> tuple[str, int]:
    """Digest tracked and untracked bytes for every managed deployment input."""

    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *DEPLOYMENT_INPUT_ROOTS,
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            "cannot enumerate managed deployment inputs"
            + (f": {detail}" if detail else "")
        )
    relative_paths = sorted(
        os.fsdecode(value)
        for value in result.stdout.split(b"\0")
        if value
    )
    if not relative_paths:
        raise ValueError("managed deployment input set is empty")

    def entries() -> Iterable[tuple[str, str, bytes]]:
        for relative in relative_paths:
            kind, content = _path_entry(ROOT / relative)
            yield relative, kind, content

    return _digest_record(entries())


def workspace_snapshot() -> dict[str, object]:
    """Return one candidate identity bound to HEAD, index/worktree state and bytes."""

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    source_revision = revision.stdout.strip()
    if revision.returncode != 0 or len(source_revision) != 40:
        raise ValueError("cannot resolve workspace source revision")
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--",
            *DEPLOYMENT_INPUT_ROOTS,
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        detail = status.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            "cannot resolve workspace index/worktree state"
            + (f": {detail}" if detail else "")
        )
    input_digest, input_count = deployment_input_digest()
    status_digest = "sha256:" + hashlib.sha256(status.stdout).hexdigest()
    identity_payload = {
        "sourceRevision": source_revision,
        "workspaceStatusDigest": status_digest,
        "deploymentInputDigest": input_digest,
        "deploymentInputFileCount": input_count,
    }
    encoded = json.dumps(
        identity_payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        **identity_payload,
        "baselineId": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def _expected_service_packages() -> list[str]:
    service_root = ROOT / "quwoquan_service" / "services"
    services = sorted(
        path.name for path in service_root.iterdir() if path.is_dir()
    )
    if (
        ROOT
        / "quwoquan_service"
        / "control-plane"
        / "platform-ops"
        / "config"
        / "schema.yaml"
    ).is_file():
        services.append("platform-ops-service")
    if not services:
        raise ValueError("canonical service package set is empty")
    return sorted(services)


def _normalized_service_packages(values: Sequence[str]) -> list[str]:
    normalized = sorted(str(value).strip() for value in values)
    if (
        not normalized
        or any(not value for value in normalized)
        or len(normalized) != len(set(normalized))
    ):
        raise ValueError("service package identity set is invalid")
    return normalized


def _package_roots(
    env_name: str,
    target_name: str,
    service_packages: Sequence[str],
) -> list[tuple[str, Path]]:
    roots = [
        (
            "app",
            app_deployment_package_dir(env_name, target=target_name),
        ),
        (
            "runtime-shared",
            runtime_shared_deployment_package_dir(
                env_name,
                target=target_name,
            ),
        ),
    ]
    legal_static = legal_static_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if legal_static.is_dir():
        roots.append(("legal-static", legal_static))
    roots.extend(
        (
            f"services/{service}",
            service_deployment_package_dir(
                env_name,
                service,
                target=target_name,
            ),
        )
        for service in service_packages
    )
    return roots


def package_content_digest(
    env_name: str,
    target_name: str,
    *,
    service_packages: Sequence[str],
) -> tuple[str, int]:
    def entries() -> Iterable[tuple[str, str, bytes]]:
        for logical_root, root in _package_roots(
            env_name,
            target_name,
            service_packages,
        ):
            if not root.is_dir():
                raise ValueError(f"package root is missing: {root}")
            paths = []
            for path in sorted(root.rglob("*"), key=lambda value: value.as_posix()):
                relative = path.relative_to(root).as_posix()
                if logical_root == "app" and relative == FINGERPRINT_NAME:
                    continue
                if path.is_dir() and not path.is_symlink():
                    continue
                paths.append((relative, path))
            if not paths:
                raise ValueError(f"package root has no payload files: {root}")
            for relative, path in paths:
                kind, content = _path_entry(path)
                yield f"{logical_root}/{relative}", kind, content

    return _digest_record(entries())


def write_package_fingerprint(
    env_name: str,
    target_name: str,
    *,
    report_dir: str,
    include_services: bool,
    details: list[str],
    service_packages: Sequence[str] | None = None,
    expected_snapshot: dict[str, object] | None = None,
) -> Path:
    del details
    if not str(report_dir).strip():
        raise ValueError("package fingerprint requires a report reference")
    if not include_services:
        raise ValueError("runtime package fingerprint requires all services")
    packages = _normalized_service_packages(
        service_packages
        if service_packages is not None
        else _expected_service_packages()
    )
    snapshot = expected_snapshot or workspace_snapshot()
    input_digest = str(snapshot["deploymentInputDigest"])
    input_count = int(snapshot["deploymentInputFileCount"])
    content_digest, content_count = package_content_digest(
        env_name,
        target_name,
        service_packages=packages,
    )
    path = fingerprint_path(env_name, target_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": FINGERPRINT_SCHEMA,
        "environment": env_name,
        "target": target_name,
        "candidateType": RUNTIME_CANDIDATE_TYPE,
        "includeServices": True,
        "servicePackages": packages,
        "reportRef": str(report_dir),
        "baselineId": snapshot["baselineId"],
        "sourceRevision": snapshot["sourceRevision"],
        "workspaceStatusDigest": snapshot["workspaceStatusDigest"],
        "deploymentInputs": {
            "roots": list(DEPLOYMENT_INPUT_ROOTS),
            "digest": input_digest,
            "fileCount": input_count,
        },
        "packageContent": {
            "digest": content_digest,
            "fileCount": content_count,
        },
    }
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _digest_payload(
    value: object,
    *,
    fields: frozenset[str],
    label: str,
) -> tuple[str, int]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} contract fields mismatch")
    digest = value.get("digest")
    file_count = value.get("fileCount")
    if (
        not isinstance(digest, str)
        or len(digest) != 71
        or not digest.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in digest[7:])
    ):
        raise ValueError(f"{label} digest is invalid")
    if (
        not isinstance(file_count, int)
        or isinstance(file_count, bool)
        or file_count <= 0
    ):
        raise ValueError(f"{label} fileCount is invalid")
    return digest, file_count


def can_reuse_package(
    env_name: str,
    target_name: str,
    *,
    include_services: bool = True,
    required_services: list[str] | None = None,
    require_workspace_match: bool = True,
) -> tuple[bool, str]:
    if not include_services:
        return False, "runtime package reuse requires all services"
    active_candidate: dict[str, str] | None = None
    if not os.environ.get(PACKAGE_ROOT_OVERRIDE_ENV, "").strip():
        try:
            active_candidate = active_deployment_candidate(target_name)
        except ValueError as exc:
            return False, f"active candidate rejected: {exc}"
        if active_candidate is None:
            return False, f"missing active candidate: {target_name}"
    path = fingerprint_path(env_name, target_name)
    if not path.is_file():
        return False, f"missing fingerprint: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != _FINGERPRINT_FIELDS:
            raise ValueError("fingerprint contract fields mismatch")
        if payload.get("schema") != FINGERPRINT_SCHEMA:
            raise ValueError("fingerprint schema mismatch")
        if payload.get("environment") != env_name:
            raise ValueError("fingerprint environment mismatch")
        if payload.get("target") != target_name:
            raise ValueError("fingerprint target mismatch")
        if payload.get("candidateType") != RUNTIME_CANDIDATE_TYPE:
            raise ValueError("fingerprint candidateType mismatch")
        if (
            not isinstance(payload.get("includeServices"), bool)
            or payload.get("includeServices") is not True
        ):
            raise ValueError("fingerprint includeServices mismatch")
        report_ref = payload.get("reportRef")
        if not isinstance(report_ref, str) or not report_ref.strip():
            raise ValueError("fingerprint reportRef is invalid")
        snapshot = workspace_snapshot() if require_workspace_match else None
        if snapshot is not None:
            for field in ("baselineId", "sourceRevision", "workspaceStatusDigest"):
                if payload.get(field) != snapshot[field]:
                    raise ValueError(f"fingerprint {field} mismatch")
        if (
            active_candidate is not None
            and payload.get("baselineId") != active_candidate["baselineId"]
        ):
            raise ValueError("fingerprint active candidate mismatch")
        raw_packages = payload.get("servicePackages")
        if not isinstance(raw_packages, list) or any(
            not isinstance(value, str) for value in raw_packages
        ):
            raise ValueError("fingerprint servicePackages is invalid")
        packages = (
            _normalized_service_packages(raw_packages)
        )
        expected_packages = (
            _normalized_service_packages(required_services)
            if required_services is not None
            else _expected_service_packages()
        )
        if packages != expected_packages:
            raise ValueError("fingerprint servicePackages mismatch")

        deployment_inputs = payload.get("deploymentInputs")
        expected_input_digest, expected_input_count = _digest_payload(
            deployment_inputs,
            fields=_DEPLOYMENT_INPUT_FIELDS,
            label="deploymentInputs",
        )
        if deployment_inputs.get("roots") != list(DEPLOYMENT_INPUT_ROOTS):
            raise ValueError("deploymentInputs roots mismatch")
        if snapshot is not None:
            actual_input_digest = str(snapshot["deploymentInputDigest"])
            actual_input_count = int(snapshot["deploymentInputFileCount"])
            if (
                actual_input_digest != expected_input_digest
                or actual_input_count != expected_input_count
            ):
                raise ValueError("deployment input digest mismatch")

        expected_content_digest, expected_content_count = _digest_payload(
            payload.get("packageContent"),
            fields=_DIGEST_FIELDS,
            label="packageContent",
        )
        actual_content_digest, actual_content_count = package_content_digest(
            env_name,
            target_name,
            service_packages=packages,
        )
        if (
            actual_content_digest != expected_content_digest
            or actual_content_count != expected_content_count
        ):
            raise ValueError("package content digest mismatch")
        candidate_manifest_path = path.parents[2] / "manifest.json"
        candidate_manifest = json.loads(
            candidate_manifest_path.read_text(encoding="utf-8")
        )
        validated_candidate = validate_candidate_manifest(
            candidate_manifest,
            expected_environment=env_name,
            expected_target=target_name,
            require_full=True,
        )
        manifest_bindings = {
            "baselineId": payload["baselineId"],
            "sourceRevision": payload["sourceRevision"],
            "workspaceStatusDigest": payload["workspaceStatusDigest"],
            "workspaceDigest": expected_input_digest,
            "packageDigest": expected_content_digest,
        }
        for field, expected in manifest_bindings.items():
            if validated_candidate.get(field) != expected:
                raise ValueError(f"deployment candidate {field} mismatch")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return False, f"fingerprint rejected: {exc}"
    return (
        True,
        f"reuse ok fingerprint={path} reportRef={payload['reportRef']}",
    )
