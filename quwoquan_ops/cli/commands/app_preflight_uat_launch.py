"""Private immutable source projection and canonical launch controls for App UAT."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands import (
    app_preflight_uat_launch_projection_seal as _projection_seal,
)
from quwoquan_ops.cli.lib.package_reuse.input_capsule import (
    _digest_record,
    verify_package_input_capsule,
)

ProjectionBuildSeal = _projection_seal.ProjectionBuildSeal
seal_projection_build = _projection_seal.seal_projection_build
FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID = (
    _projection_seal.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID
)
FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID = (
    _projection_seal.FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID
)

_DIGEST_PREFIX = "sha256:"
_REQUIRED_LAUNCH_ROOTS = {
    "quwoquan_app",
    "quwoquan_ops/cli",
    "quwoquan_ops/environments",
}
_PROJECTION_EVIDENCE_FIELDS = {
    "schema",
    "candidateDigest",
    "packageDigest",
    "sourceRevision",
    "sourceCapsuleDigest",
    "sourceCapsuleWorkspaceStatusDigest",
    "sourceCapsuleManifestDigest",
    "sourceCapsuleManifestRef",
    "sourceProjectionRoot",
    "sourceProjectionDigest",
    "sourceProjectionFileCount",
}
_BUILD_PROJECTION_SEAL_FIELDS = {
    "schema",
    "policyId",
    "sourceProjectionDigest",
    "sourceEntryCount",
    "derivedOutputDigest",
    "derivedOutputPolicyDigest",
    "derivedEntryCount",
    "buildProjectionDigest",
}


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def _valid_digest(value: object) -> bool:
    raw = str(value or "")
    if not raw.startswith(_DIGEST_PREFIX) or len(raw) != 71:
        return False
    try:
        bytes.fromhex(raw.removeprefix(_DIGEST_PREFIX))
    except ValueError:
        return False
    return True


def _fresh_path_under(path: Path, root: Path, *, label: str) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = Path(path.expanduser().absolute())
    if not candidate.is_absolute() or candidate.exists() or candidate.is_symlink():
        raise ValueError(f"App content UAT {label} must be fresh and absolute")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    try:
        candidate.parent.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError(f"App content UAT {label} escapes QWQ_OUTPUT_ROOT") from exc
    return candidate


def _atomic_private_json(path: Path, value: Mapping[str, Any]) -> str:
    encoded = (
        json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("private App UAT evidence write made no progress")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        # link(2) is the portable same-filesystem no-replace publish primitive:
        # it fails when a regular file or symlink appears after the freshness
        # check, while readers can only observe the fully fsynced document.
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return _canonical_digest(value)


def write_app_content_projection_build_seal(
    *,
    seal: ProjectionBuildSeal,
    output_root: Path,
    seal_path: Path,
) -> dict[str, Any]:
    """Persist one fresh post-process projection seal as private evidence."""

    payload = seal.as_dict()
    if set(payload) != _BUILD_PROJECTION_SEAL_FIELDS:
        raise ValueError("App content UAT build projection seal fields mismatch")
    seal_ref = _fresh_path_under(
        seal_path,
        output_root,
        label="build projection seal evidence",
    )
    evidence_digest = _atomic_private_json(seal_ref, payload)
    return {
        **payload,
        "buildProjectionSealDigest": evidence_digest,
        "buildProjectionSealRef": str(seal_ref),
    }


def write_app_content_launch_report(
    *,
    report: Mapping[str, Any],
    output_root: Path,
    report_path: Path,
) -> dict[str, str]:
    """Publish one fresh canonical launch report without replacing any path."""

    if report.get("schema") != "quwoquan_app.test_live_launch":
        raise ValueError("App content UAT launch report schema is invalid")
    report_ref = _fresh_path_under(
        report_path,
        output_root,
        label="launch report",
    )
    return {
        "launchReportDigest": _atomic_private_json(report_ref, report),
        "launchReportRef": str(report_ref),
    }


def verify_app_content_projection_build_seal(
    *,
    manifest_path: Path,
    projection_root: Path,
    output_root: Path,
    seal_path: Path,
    expected_seal_digest: str,
    expected_policy_id: str,
) -> dict[str, Any]:
    """Reread one seal and prove that it still identifies the whole tree."""

    root = output_root.expanduser().resolve()
    candidate = Path(seal_path).expanduser()
    absolute = Path(candidate.absolute())
    if absolute.is_symlink() or not absolute.is_file():
        raise ValueError("App content UAT build projection seal evidence is missing")
    try:
        resolved = absolute.resolve()
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "App content UAT build projection seal evidence escapes QWQ_OUTPUT_ROOT"
        ) from exc
    payload = json.loads(
        _read_regular_file_nofollow(
            resolved,
            label="build projection seal evidence",
        ).decode("utf-8")
    )
    if not isinstance(payload, Mapping) or set(payload) != _BUILD_PROJECTION_SEAL_FIELDS:
        raise ValueError("App content UAT build projection seal fields mismatch")
    if (
        not _valid_digest(expected_seal_digest)
        or _canonical_digest(payload) != expected_seal_digest
    ):
        raise ValueError("App content UAT build projection seal digest drifted")
    if payload.get("policyId") != expected_policy_id:
        raise ValueError("App content UAT build projection policy drifted")
    recomputed = seal_projection_build(
        manifest_path,
        projection_root,
        policy_id=expected_policy_id,
        expected_build_projection_digest=str(payload.get("buildProjectionDigest") or ""),
    )
    if recomputed.as_dict() != dict(payload):
        raise ValueError("App content UAT build projection seal drifted")
    return {
        **dict(payload),
        "buildProjectionSealDigest": expected_seal_digest,
        "buildProjectionSealRef": str(resolved),
    }


def _read_regular_file_nofollow(path: Path, *, label: str) -> bytes:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("App content UAT source projection requires O_NOFOLLOW")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ValueError(f"App content UAT {label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"App content UAT {label} is not a regular file")
        content = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError(f"App content UAT {label} changed during read")
    finally:
        os.close(descriptor)
    return bytes(content)


def _projection_manifest_entries(
    manifest: Mapping[str, Any],
    *,
    capsule_root: Path,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()
    capsule_root = capsule_root.resolve()
    for raw in manifest.get("entries") or []:
        if not isinstance(raw, Mapping):
            raise TypeError("App content UAT source capsule entry is invalid")
        capsule_relative = Path(str(raw.get("capsulePath") or ""))
        if not capsule_relative.parts or capsule_relative.parts[0] != "repo":
            continue
        repo_relative = Path(*capsule_relative.parts[1:])
        if (
            not repo_relative.parts
            or any(part in {"", ".", "..", ".git"} for part in repo_relative.parts)
            or repo_relative in seen
        ):
            raise ValueError("App content UAT source projection path is unsafe")
        if str(raw.get("logicalPath") or "") != repo_relative.as_posix():
            raise ValueError("App content UAT source projection logical path drifted")
        seen.add(repo_relative)
        kind = str(raw.get("kind") or "")
        source = capsule_root / capsule_relative
        if kind == "file":
            content = _read_regular_file_nofollow(
                source,
                label=f"capsule file {repo_relative.as_posix()}",
            )
            capsule_mode = raw.get("mode")
            if capsule_mode not in {0o444, 0o555}:
                raise ValueError("App content UAT source capsule file mode is invalid")
            projection_mode = 0o755 if capsule_mode & 0o111 else 0o644
        elif kind == "symlink":
            try:
                metadata = source.lstat()
            except OSError as exc:
                raise ValueError("App content UAT source capsule symlink is missing") from exc
            if not stat.S_ISLNK(metadata.st_mode) or raw.get("mode") != 0:
                raise ValueError("App content UAT source capsule symlink drifted")
            resolved = source.resolve(strict=True)
            if not resolved.is_relative_to(capsule_root):
                raise ValueError("App content UAT source capsule symlink escapes capsule")
            content = os.readlink(source).encode("utf-8")
            projection_mode = 0
        else:
            raise ValueError("App content UAT source capsule entry kind is invalid")
        if (
            raw.get("size") != len(content)
            or raw.get("digest")
            != _DIGEST_PREFIX + hashlib.sha256(content).hexdigest()
        ):
            raise ValueError("App content UAT source capsule entry CAS mismatch")
        entries.append(
            {
                "logicalPath": str(raw["logicalPath"]),
                "repoRelative": repo_relative,
                "kind": kind,
                "content": content,
                "projectionMode": projection_mode,
                "source": source,
            }
        )
    if not entries:
        raise ValueError("App content UAT source projection entry set is empty")
    return entries


def _safe_projection_parent(projection: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    projection_resolved = projection.resolve()
    if not destination.parent.resolve().is_relative_to(projection_resolved):
        raise ValueError("App content UAT source projection destination escapes build root")
    relative_parent = destination.parent.relative_to(projection)
    current = projection
    for part in relative_parent.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("App content UAT source projection parent is a symlink")


def _copy_projection_regular_file(
    *,
    source: Path,
    destination: Path,
    expected_content: bytes,
    mode: int,
) -> None:
    content = _read_regular_file_nofollow(source, label="capsule projection input")
    if content != expected_content:
        raise ValueError("App content UAT source capsule changed during projection copy")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
        0o600,
    )
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("App content UAT source projection write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        copied = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    source_metadata = source.lstat()
    if (source_metadata.st_dev, source_metadata.st_ino) == (
        copied.st_dev,
        copied.st_ino,
    ):
        raise ValueError("App content UAT source projection hardlink is forbidden")
    destination.chmod(mode)


def _projection_cas(
    *,
    manifest: Mapping[str, Any],
    capsule_root: Path,
    projection_root: Path,
    reject_unmanifested: bool,
) -> tuple[str, int]:
    projection = projection_root.resolve()
    expected = _projection_manifest_entries(
        manifest,
        capsule_root=capsule_root,
    )
    digest_entries: list[tuple[str, str, bytes]] = []
    expected_paths: set[Path] = set()
    for entry in expected:
        relative = entry["repoRelative"]
        expected_paths.add(relative)
        path = projection / relative
        kind = str(entry["kind"])
        expected_content = bytes(entry["content"])
        if kind == "file":
            content = _read_regular_file_nofollow(
                path,
                label=f"projected file {relative.as_posix()}",
            )
            metadata = path.lstat()
            if stat.S_IMODE(metadata.st_mode) != int(entry["projectionMode"]):
                raise ValueError("App content UAT source projection file mode drifted")
        else:
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise ValueError("App content UAT source projection symlink is missing") from exc
            if not stat.S_ISLNK(metadata.st_mode):
                raise ValueError("App content UAT source projection symlink kind drifted")
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(projection):
                raise ValueError("App content UAT source projection symlink escapes build root")
            content = os.readlink(path).encode("utf-8")
        if content != expected_content:
            raise ValueError("App content UAT source projection entry CAS mismatch")
        digest_entries.append((str(entry["logicalPath"]), kind, content))
    if reject_unmanifested:
        actual_paths = {
            path.relative_to(projection_root)
            for path in projection_root.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        if actual_paths != expected_paths:
            raise ValueError("App content UAT source projection contains undeclared bytes")
    return _digest_record(digest_entries)


def verify_app_content_launch_projection(
    *,
    projection_root: Path,
    evidence_path: Path,
    reject_unmanifested: bool,
) -> dict[str, Any]:
    """Re-read the source-only projection CAS at a launch/build boundary."""

    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise ValueError("App content UAT source projection evidence is missing")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict) or set(evidence) != _PROJECTION_EVIDENCE_FIELDS:
        raise ValueError("App content UAT source projection evidence fields mismatch")
    projection = projection_root.expanduser().resolve()
    if str(projection) != evidence.get("sourceProjectionRoot"):
        raise ValueError("App content UAT source projection root drifted")
    manifest_ref = Path(str(evidence.get("sourceCapsuleManifestRef") or ""))
    manifest = verify_package_input_capsule(manifest_ref.parent)
    if _canonical_digest(manifest) != evidence.get("sourceCapsuleManifestDigest"):
        raise ValueError("App content UAT source capsule manifest drifted")
    digest, count = _projection_cas(
        manifest=manifest,
        capsule_root=manifest_ref.parent,
        projection_root=projection,
        reject_unmanifested=reject_unmanifested,
    )
    if (
        digest != evidence.get("sourceProjectionDigest")
        or count != evidence.get("sourceProjectionFileCount")
    ):
        raise ValueError("App content UAT source projection CAS drifted")
    return evidence


def materialize_app_content_launch_projection(
    *,
    runtime_binding: Mapping[str, Any],
    output_root: Path,
    projection_root: Path,
    evidence_path: Path,
) -> dict[str, Any]:
    """Copy the active candidate's verified capsule into one writable build root."""

    manifest_ref = Path(
        str(runtime_binding.get("sourceCapsuleManifestRef") or "")
    ).expanduser()
    if manifest_ref.is_symlink() or not manifest_ref.is_file():
        raise ValueError("App content UAT source capsule manifest is missing")
    manifest = verify_package_input_capsule(manifest_ref.parent)
    expected = {
        "baselineId": runtime_binding.get("candidateDigest"),
        "sourceRevision": runtime_binding.get("sourceRevision"),
        "workspaceStatusDigest": runtime_binding.get(
            "sourceCapsuleWorkspaceStatusDigest"
        ),
        "deploymentInputDigest": runtime_binding.get("sourceCapsuleDigest"),
    }
    if any(not value or manifest.get(field) != value for field, value in expected.items()):
        raise ValueError("App content UAT candidate/source capsule identity drifted")
    candidate_digest = str(runtime_binding.get("candidateDigest") or "")
    package_digest = str(runtime_binding.get("packageDigest") or "")
    if not candidate_digest.startswith(_DIGEST_PREFIX) or not package_digest.startswith(
        _DIGEST_PREFIX
    ):
        raise ValueError("App content UAT candidate/package identity is invalid")
    roots = {str(value) for value in manifest.get("deploymentInputRoots") or []}
    if not _REQUIRED_LAUNCH_ROOTS.issubset(roots):
        raise ValueError("App content UAT source capsule lacks canonical launch closure")

    projection = _fresh_path_under(
        projection_root,
        output_root,
        label="source projection",
    )
    projection.mkdir(mode=0o700)
    try:
        projection_entries = _projection_manifest_entries(
            manifest,
            capsule_root=manifest_ref.parent,
        )
        for entry in projection_entries:
            repo_relative = entry["repoRelative"]
            destination = projection / repo_relative
            _safe_projection_parent(projection, destination)
            kind = str(entry["kind"])
            if kind == "file":
                _copy_projection_regular_file(
                    source=entry["source"],
                    destination=destination,
                    expected_content=entry["content"],
                    mode=int(entry["projectionMode"]),
                )
            else:
                destination.symlink_to(bytes(entry["content"]).decode("utf-8"))
        for required in ("quwoquan_app/run.sh", "quwoquan_ops/cli/stackctl.py"):
            path = projection / required
            if path.is_symlink() or not path.is_file():
                raise ValueError(
                    f"App content UAT source projection lacks {required}"
                )
        if (projection / ".git").exists() or (projection / ".git").is_symlink():
            raise ValueError("App content UAT source projection must not depend on .git")
        projection_digest, projection_count = _projection_cas(
            manifest=manifest,
            capsule_root=manifest_ref.parent,
            projection_root=projection,
            reject_unmanifested=True,
        )
    except BaseException:
        shutil.rmtree(projection, ignore_errors=True)
        raise

    manifest_digest = _canonical_digest(manifest)
    evidence = {
        "schema": "quwoquan_ops.app_content_uat_source_projection.v1",
        "candidateDigest": candidate_digest,
        "packageDigest": package_digest,
        "sourceRevision": str(runtime_binding.get("sourceRevision") or ""),
        "sourceCapsuleDigest": str(runtime_binding.get("sourceCapsuleDigest") or ""),
        "sourceCapsuleWorkspaceStatusDigest": str(
            runtime_binding.get("sourceCapsuleWorkspaceStatusDigest") or ""
        ),
        "sourceCapsuleManifestDigest": manifest_digest,
        "sourceCapsuleManifestRef": str(manifest_ref.resolve()),
        "sourceProjectionRoot": str(projection.resolve()),
        "sourceProjectionDigest": projection_digest,
        "sourceProjectionFileCount": projection_count,
    }
    evidence_ref = _fresh_path_under(
        evidence_path,
        output_root,
        label="source projection evidence",
    )
    evidence_digest = _atomic_private_json(evidence_ref, evidence)
    return {
        **evidence,
        "sourceProjectionEvidenceDigest": evidence_digest,
        "sourceProjectionEvidenceRef": str(evidence_ref),
    }


def write_app_content_launch_control(
    *,
    runtime_binding: Mapping[str, Any],
    projection: Mapping[str, Any],
    output_root: Path,
    control_path: Path,
    attempt_path: Path,
    report_path: Path,
    terminal_receipt_path: Path,
    platform: str,
    device_id: str,
    build_projection_policy_id: str,
    build_projection_seal_path: Path,
    expected_build_projection_digest: str | None,
) -> dict[str, Any]:
    """Issue a fresh path-bound control file consumed by the internal launcher."""

    policy_by_platform = {
        "android": FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
        "android-physical": FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
        "ios-simulator": FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        "ios-physical": FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
    }
    if policy_by_platform.get(platform) != build_projection_policy_id:
        raise ValueError("App content UAT build projection policy/platform mismatch")
    if expected_build_projection_digest is not None and not _valid_digest(
        expected_build_projection_digest
    ):
        raise ValueError("App content UAT expected build projection digest is invalid")
    seal_ref = _fresh_path_under(
        build_projection_seal_path,
        output_root,
        label="build projection seal evidence",
    )
    control_ref = _fresh_path_under(
        control_path,
        output_root,
        label="canonical launch control",
    )
    control = {
        "schema": "quwoquan_ops.app_content_uat_launch_control.v1",
        "actor": "app-content-uat",
        "environment": str(runtime_binding.get("environment") or ""),
        "target": str(runtime_binding.get("target") or ""),
        "platform": platform,
        "deviceId": device_id,
        "candidateDigest": str(runtime_binding.get("candidateDigest") or ""),
        "packageDigest": str(runtime_binding.get("packageDigest") or ""),
        "sourceRevision": str(runtime_binding.get("sourceRevision") or ""),
        "sourceCapsuleDigest": str(runtime_binding.get("sourceCapsuleDigest") or ""),
        "sourceCapsuleManifestDigest": projection["sourceCapsuleManifestDigest"],
        "sourceCapsuleManifestRef": projection["sourceCapsuleManifestRef"],
        "sourceProjectionRoot": projection["sourceProjectionRoot"],
        "sourceProjectionEvidenceDigest": projection[
            "sourceProjectionEvidenceDigest"
        ],
        "sourceProjectionEvidenceRef": projection["sourceProjectionEvidenceRef"],
        "buildProjectionPolicyId": build_projection_policy_id,
        "buildProjectionSealRef": str(seal_ref),
        "expectedBuildProjectionDigest": expected_build_projection_digest,
        "launchAttemptRef": str(attempt_path.absolute()),
        "launchReportRef": str(report_path.absolute()),
        "startupTerminalReceiptRef": str(terminal_receipt_path.absolute()),
    }
    digest = _atomic_private_json(control_ref, control)
    return {**control, "controlDigest": digest, "controlRef": str(control_ref)}
