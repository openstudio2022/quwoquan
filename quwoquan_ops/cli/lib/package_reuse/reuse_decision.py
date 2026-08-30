"""package fingerprint 写入与 package 复用判定（逐字迁自原单文件）。

四个 deployment package 目录解析函数与 ``active_deployment_candidate``、
``verify_package_input_capsule``、``workspace_snapshot``、``package_content_digest``、
``validate_candidate_manifest``、``_expected_service_packages`` 经包属性
（``_pkg.``）消费，保持测试对包属性 monkeypatch 的既有语义。
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Sequence
from pathlib import Path

import quwoquan_ops.cli.lib.package_reuse as _pkg

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    RELEASE_INPUT_CLASSIFICATIONS,
    RUNTIME_CANDIDATE_TYPE,
)
from quwoquan_ops.cli.lib.output_paths import (
    PACKAGE_ROOT_OVERRIDE_ENV,
)

from .constants import (
    _DEPLOYMENT_INPUT_FIELDS,
    _DIGEST_FIELDS,
    _FINGERPRINT_FIELDS,
    CURRENTNESS_TIMEOUT_DETAIL_PREFIX,
    CURRENTNESS_TIMEOUT_SECONDS,
    FINGERPRINT_NAME,
    FINGERPRINT_SCHEMA,
    PACKAGE_INPUT_CAPSULE_DIRECTORY,
    PACKAGE_VALIDATION_PURPOSES,
)
from .fingerprint_store import _atomic_write_fingerprint, fingerprint_path
from .input_capsule import _digest_record, _normalized_input_roots, _path_entry
from .workspace_inputs import (
    _normalized_service_packages,
    deployment_input_roots,
)


def _candidate_service_packages(candidate_root: Path) -> list[str]:
    root = candidate_root / "packages" / "services"
    if not root.is_dir():
        raise ValueError("candidate service package root is missing")
    values = sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and not path.is_symlink()
    )
    return _normalized_service_packages(values)


def _package_roots(
    env_name: str,
    target_name: str,
    service_packages: Sequence[str],
    *,
    candidate_root: Path | None = None,
) -> list[tuple[str, Path]]:
    if candidate_root is not None:
        package_root = candidate_root / "packages"
        roots = [
            ("app", package_root / "app"),
            ("runtime-shared", package_root / "runtime-shared"),
        ]
        legal_static = package_root / "legal-static"
        if legal_static.is_dir():
            roots.append(("legal-static", legal_static))
        roots.extend(
            (f"services/{service}", package_root / "services" / service)
            for service in service_packages
        )
        return roots

    roots = [
        (
            "app",
            _pkg.app_deployment_package_dir(env_name, target=target_name),
        ),
        (
            "runtime-shared",
            _pkg.runtime_shared_deployment_package_dir(
                env_name,
                target=target_name,
            ),
        ),
    ]
    legal_static = _pkg.legal_static_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if legal_static.is_dir():
        roots.append(("legal-static", legal_static))
    roots.extend(
        (
            f"services/{service}",
            _pkg.service_deployment_package_dir(
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
    candidate_root: Path | None = None,
) -> tuple[str, int]:
    def entries() -> Iterable[tuple[str, str, bytes]]:
        for logical_root, root in _package_roots(
            env_name,
            target_name,
            service_packages,
            candidate_root=candidate_root,
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
    release_input_classification: str,
    contract_graph_digest: str,
    graphql_read_registry: dict[str, object],
    app_launch_bundle: dict[str, object] | None = None,
    service_packages: Sequence[str] | None = None,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
    expected_snapshot: dict[str, object] | None = None,
    candidate_root: Path | None = None,
) -> Path:
    del details
    if not str(report_dir).strip():
        raise ValueError("package fingerprint requires a report reference")
    if not include_services:
        raise ValueError("runtime package fingerprint requires all services")
    if release_input_classification not in RELEASE_INPUT_CLASSIFICATIONS:
        raise ValueError("package fingerprint releaseInputClassification is invalid")
    if (
        not isinstance(contract_graph_digest, str)
        or len(contract_graph_digest) != 71
        or not contract_graph_digest.startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in contract_graph_digest[7:]
        )
    ):
        raise ValueError("package fingerprint contractGraphDigest is invalid")
    packages = _normalized_service_packages(
        service_packages
        if service_packages is not None
        else _pkg._expected_service_packages()
    )
    roots = deployment_input_roots(
        env_name,
        target_name,
        packages,
        release_attestation=release_attestation,
        rollback_release_attestation=rollback_release_attestation,
    )
    snapshot = expected_snapshot or _pkg.workspace_snapshot(deployment_roots=roots)
    snapshot_roots = _normalized_input_roots(
        list(snapshot.get("deploymentInputRoots") or roots)
    )
    if snapshot_roots != roots:
        raise ValueError("package snapshot deployment input closure mismatch")
    input_digest = str(snapshot["deploymentInputDigest"])
    input_count = int(snapshot["deploymentInputFileCount"])
    selected_candidate_root = (
        candidate_root
        if candidate_root is not None
        else _pkg.app_deployment_package_dir(env_name, target=target_name).parent.parent
    )
    _pkg.verify_package_input_capsule(
        selected_candidate_root / PACKAGE_INPUT_CAPSULE_DIRECTORY,
        expected_snapshot=snapshot,
    )
    content_digest, content_count = _pkg.package_content_digest(
        env_name,
        target_name,
        service_packages=packages,
        candidate_root=candidate_root,
    )
    path = fingerprint_path(env_name, target_name)
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
            "roots": snapshot_roots,
            "capsuleRef": PACKAGE_INPUT_CAPSULE_DIRECTORY,
            "digest": input_digest,
            "fileCount": input_count,
        },
        "packageContent": {
            "digest": content_digest,
            "fileCount": content_count,
        },
        "releaseInputClassification": release_input_classification,
        "contractGraphDigest": contract_graph_digest,
        "graphqlReadRegistry": graphql_read_registry,
        "appLaunchBundle": app_launch_bundle,
    }
    _atomic_write_fingerprint(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
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
    purpose: str = "self_verify",
    currentness_timeout_seconds: float = CURRENTNESS_TIMEOUT_SECONDS,
    candidate_root: Path | None = None,
    verify_source_capsule: bool = True,
) -> tuple[bool, str]:
    if not include_services:
        return False, "runtime package reuse requires all services"
    if purpose not in PACKAGE_VALIDATION_PURPOSES:
        return False, "runtime package validation purpose is invalid"
    if not isinstance(verify_source_capsule, bool):
        return False, "runtime package source capsule validation mode is invalid"
    if purpose == "currentness" and not verify_source_capsule:
        return False, "runtime package currentness requires source capsule verification"

    override = os.environ.get(PACKAGE_ROOT_OVERRIDE_ENV, "").strip()
    active_candidate: dict[str, str] | None
    if candidate_root is None:
        if override:
            return (
                False,
                (
                    "deployment package root override is forbidden for active "
                    "candidate reuse"
                ),
            )
        try:
            active_candidate = _pkg.active_deployment_candidate(target_name)
        except ValueError as exc:
            return False, f"active candidate rejected: {exc}"
        if active_candidate is None:
            return False, f"missing active candidate: {target_name}"
        active_root = str(active_candidate.get("candidateDir") or "").strip()
        if not active_root:
            return False, "active candidate rejected: candidateDir is missing"
        selected_candidate_root = Path(active_root)
    else:
        active_candidate = None
        selected_candidate_root = Path(candidate_root).expanduser()
        if not selected_candidate_root.is_absolute():
            return False, "explicit candidate root must be absolute"
        if override:
            override_root = Path(override).expanduser()
            if not override_root.is_absolute():
                return False, "deployment package root override must be absolute"
            if override_root != selected_candidate_root / "packages":
                return (
                    False,
                    (
                        "deployment package root override does not match explicit "
                        "candidate root"
                    ),
                )

    path = selected_candidate_root / "packages" / "app" / FINGERPRINT_NAME
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
        classification = payload.get("releaseInputClassification")
        if classification not in RELEASE_INPUT_CLASSIFICATIONS:
            raise ValueError("fingerprint releaseInputClassification is invalid")
        contract_graph_digest = payload.get("contractGraphDigest")
        if (
            not isinstance(contract_graph_digest, str)
            or len(contract_graph_digest) != 71
            or not contract_graph_digest.startswith("sha256:")
            or any(
                character not in "0123456789abcdef"
                for character in contract_graph_digest[7:]
            )
        ):
            raise ValueError("fingerprint contractGraphDigest is invalid")
        graphql_read_registry = payload.get("graphqlReadRegistry")
        if not isinstance(graphql_read_registry, dict):
            raise ValueError("fingerprint graphqlReadRegistry is invalid")
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
            else packages
        )
        if packages != expected_packages:
            raise ValueError("fingerprint servicePackages mismatch")
        if packages != _candidate_service_packages(selected_candidate_root):
            raise ValueError("fingerprint servicePackages mismatch")

        deployment_inputs = payload.get("deploymentInputs")
        expected_input_digest, expected_input_count = _digest_payload(
            deployment_inputs,
            fields=_DEPLOYMENT_INPUT_FIELDS,
            label="deploymentInputs",
        )
        declared_roots = deployment_inputs.get("roots")
        if not isinstance(declared_roots, list) or any(
            not isinstance(value, str) for value in declared_roots
        ):
            raise ValueError("deploymentInputs roots mismatch")
        normalized_roots = _normalized_input_roots(declared_roots)
        if declared_roots != normalized_roots:
            raise ValueError("deploymentInputs roots are not canonical")
        if deployment_inputs.get("capsuleRef") != PACKAGE_INPUT_CAPSULE_DIRECTORY:
            raise ValueError("deploymentInputs capsuleRef mismatch")
        capsule_root = selected_candidate_root / PACKAGE_INPUT_CAPSULE_DIRECTORY
        capsule_manifest = (
            _pkg.verify_package_input_capsule(capsule_root)
            if verify_source_capsule
            else _pkg._read_capsule_manifest(capsule_root)
        )
        if (
            capsule_manifest.get("baselineId") != payload.get("baselineId")
            or capsule_manifest.get("sourceRevision") != payload.get("sourceRevision")
            or capsule_manifest.get("workspaceStatusDigest")
            != payload.get("workspaceStatusDigest")
            or capsule_manifest.get("deploymentInputRoots") != normalized_roots
            or capsule_manifest.get("deploymentInputDigest") != expected_input_digest
            or capsule_manifest.get("deploymentInputFileCount") != expected_input_count
        ):
            raise ValueError("deployment input capsule fingerprint binding mismatch")
        if purpose == "currentness":
            snapshot = _pkg.workspace_snapshot(
                deployment_roots=normalized_roots,
                timeout_seconds=currentness_timeout_seconds,
            )
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
        actual_content_digest, actual_content_count = _pkg.package_content_digest(
            env_name,
            target_name,
            service_packages=packages,
            candidate_root=selected_candidate_root,
        )
        if (
            actual_content_digest != expected_content_digest
            or actual_content_count != expected_content_count
        ):
            raise ValueError("package content digest mismatch")
        candidate_manifest_path = selected_candidate_root / "manifest.json"
        candidate_manifest = json.loads(
            candidate_manifest_path.read_text(encoding="utf-8")
        )
        validated_candidate = _pkg.validate_candidate_manifest(
            candidate_manifest,
            expected_environment=env_name,
            expected_target=target_name,
            require_full=True,
            candidate_root=selected_candidate_root,
            purpose=purpose,
            currentness_timeout_seconds=currentness_timeout_seconds,
        )
        manifest_bindings = {
            "baselineId": payload["baselineId"],
            "sourceRevision": payload["sourceRevision"],
            "workspaceStatusDigest": payload["workspaceStatusDigest"],
            "workspaceDigest": expected_input_digest,
            "packageDigest": expected_content_digest,
            "releaseInputClassification": classification,
            "contractGraphDigest": contract_graph_digest,
            "graphqlReadRegistry": graphql_read_registry,
            "appLaunchBundle": payload.get("appLaunchBundle"),
        }
        for field, expected in manifest_bindings.items():
            if validated_candidate.get(field) != expected:
                raise ValueError(f"deployment candidate {field} mismatch")
    except TimeoutError as exc:
        return (
            False,
            f"{CURRENTNESS_TIMEOUT_DETAIL_PREFIX} fingerprint rejected: {exc}",
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        detail = str(exc)
        lowered = detail.lower()
        if purpose == "currentness" and "currentness" in lowered and (
            "timed out" in lowered or "timeout" in lowered
        ):
            return (
                False,
                f"{CURRENTNESS_TIMEOUT_DETAIL_PREFIX} fingerprint rejected: {detail}",
            )
        return False, f"fingerprint rejected: {detail}"
    return (
        True,
        f"reuse ok fingerprint={path} reportRef={payload['reportRef']}",
    )
