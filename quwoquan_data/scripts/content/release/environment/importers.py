"""Release-bound service importer execution and report validation."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import REPO_ROOT
from core.release_layout import payload_digest, payload_file
from core.schema import assert_valid
from content.release.model import DeletePolicy, ImportMode


_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


_IMPORT_REPORT_SCHEMAS = {
    "quwoquan.content_import_report": "import_report",
    "quwoquan.tag_import_report": "tag_import_report",
    "quwoquan.user_creator_import_report": "creator_import_report",
    "quwoquan_service.homepage_import_report": "homepage_import_report",
}


@dataclass(frozen=True)
class OwnerReleaseEvidence:
    document: dict[str, Any]
    path: Path
    ref: str
    digest: str


# Compatibility for existing Content adapter callers and tests.
ContentReleaseEvidence = OwnerReleaseEvidence


_RELEASE_RECEIPT_SCHEMAS = {
    "quwoquan.content_release_candidate_receipt": "content_release_candidate_receipt",
    "quwoquan.content_release_active_receipt": "content_release_active_receipt",
    "quwoquan.content_release_activation_receipt": "content_release_activation_receipt",
    "quwoquan.tag_release_candidate_receipt": "tag_release_candidate_receipt",
    "quwoquan.creator_release_candidate_receipt": "creator_release_candidate_receipt",
    "quwoquan.homepage_release_candidate_receipt": "homepage_release_candidate_receipt",
}

_OWNER_RELEASE_CONTROL = {
    "content": ("content-service", "quwoquan.content_release_candidate_receipt"),
    "tag": ("tag-service", "quwoquan.tag_release_candidate_receipt"),
    "creator": ("user-service", "quwoquan.creator_release_candidate_receipt"),
    "homepage": ("entity-service", "quwoquan.homepage_release_candidate_receipt"),
}

# All release-control commands intentionally share one service-root cwd and one
# flag surface. Mongo URI remains argv-only and is never included in failures.
_OWNER_RELEASE_CONTROL_COMMANDS = {
    "content": "./services/content-service/cmd/release-control",
    "tag": "./services/tag-service/cmd/release-control",
    "creator": "./services/user-service/cmd/creator-release-control",
    "homepage": "./services/entity-service/cmd/homepage-release-control",
}


def _assert_receipt_ref_path(path: Path, *, output_root: Path) -> str:
    try:
        relative = path.relative_to(output_root)
        path.parent.resolve(strict=True).relative_to(output_root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Content release receipt 必须位于 QWQ_OUTPUT_ROOT：{path}"
        ) from exc
    current = path
    while current != output_root:
        if current.is_symlink():
            raise RuntimeError(f"Content release receipt path 不得包含 symlink：{path}")
        if current.parent == current:
            raise RuntimeError(
                f"Content release receipt path 越出 QWQ_OUTPUT_ROOT：{path}"
            )
        current = current.parent
    ref = relative.as_posix()
    if not ref or relative.is_absolute() or ".." in relative.parts or "\\" in ref:
        raise RuntimeError(f"Content release receipt ref 非法：{ref}")
    return ref


def file_byte_digest(path: Path) -> str:
    """Hash the exact receipt bytes after rejecting missing or symlinked files."""

    import hashlib

    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Content release receipt 必须是非 symlink 普通文件：{path}")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt_evidence(path: Path, *, output_root: Path) -> tuple[str, str]:
    ref = _assert_receipt_ref_path(path, output_root=output_root)
    return ref, file_byte_digest(path)


def _strict_release_control_identity(value: object, *, label: str) -> str:
    normalized = str(value or "")
    if not normalized or normalized != normalized.strip():
        raise RuntimeError(f"Content release receipt {label} 为空或不规范")
    return normalized


def _validate_release_control_document(
    payload: Mapping[str, Any],
    *,
    schema: str,
    environment: str,
    release_id: str | None = None,
    manifest_digest: str | None = None,
    label: str = "<memory>",
) -> dict[str, Any]:
    document = dict(payload)
    schema_name = _RELEASE_RECEIPT_SCHEMAS.get(schema)
    if not schema_name or document.get("schema") != schema:
        raise RuntimeError(
            "Content release receipt schema 不一致："
            f"expected={schema} actual={document.get('schema')}"
        )
    assert_valid(document, "release", schema_name, label=f"{schema_name}:{label}")
    identity = document.get("identity")
    bound = identity if isinstance(identity, Mapping) else document
    if bound.get("environment") != environment or bound.get("sourceOwner") != "qwq_data":
        raise RuntimeError("Owner release receipt environment/sourceOwner 不一致")
    if release_id is not None and bound.get("releaseId") != release_id:
        raise RuntimeError("Owner release receipt releaseId 不一致")
    if manifest_digest is not None and bound.get("manifestDigest") != manifest_digest:
        raise RuntimeError("Owner release receipt manifestDigest 不一致")
    return document


def _validate_release_control_receipt(
    path: Path,
    *,
    schema: str,
    environment: str,
    release_id: str | None = None,
    manifest_digest: str | None = None,
) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"Content release receipt 必须是对象：{path}")
    return _validate_release_control_document(
        payload,
        schema=schema,
        environment=environment,
        release_id=release_id,
        manifest_digest=manifest_digest,
        label=str(path),
    )


def load_content_release_receipt(
    path: Path,
    *,
    output_root: Path,
    schema: str,
    environment: str,
    expected_digest: str,
    release_id: str | None = None,
    manifest_digest: str | None = None,
) -> ContentReleaseEvidence:
    """Load one bound receipt only after proving its output-root path and bytes."""

    ref, digest = _receipt_evidence(path, output_root=output_root)
    if digest != expected_digest:
        raise RuntimeError(
            "Content release receipt digest drift："
            f"expected={expected_digest} actual={digest}"
        )
    document = _validate_release_control_receipt(
        path,
        schema=schema,
        environment=environment,
        release_id=release_id,
        manifest_digest=manifest_digest,
    )
    return ContentReleaseEvidence(document, path, ref, digest)


def _run_release_control(command: list[str]) -> None:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT / "quwoquan_service",
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Do not include argv: it contains the Mongo URI.
        raise SystemExit(
            f"[ship] owner release-control failed: exit={result.returncode}"
        )


def load_owner_release_candidate_receipt(
    path: Path,
    *,
    owner: str,
    output_root: Path,
    environment: str,
    release_id: str,
    manifest_digest: str,
    expected_digest: str,
) -> OwnerReleaseEvidence:
    """Load one explicit owner candidate ref and bind its exact bytes."""

    try:
        _service, schema = _OWNER_RELEASE_CONTROL[owner]
    except KeyError as exc:
        raise ValueError(f"未知 release owner：{owner}") from exc
    evidence = load_content_release_receipt(
        path,
        output_root=output_root,
        schema=schema,
        environment=environment,
        release_id=release_id,
        manifest_digest=manifest_digest,
        expected_digest=expected_digest,
    )
    if evidence.document.get("status") != "found":
        raise RuntimeError(f"{owner} verified candidate proof 必须是 found")
    return evidence


def query_owner_release_candidate(
    *,
    owner: str,
    env: str,
    mongo_uri: str,
    release_id: str,
    manifest_digest: str,
    report_path: Path,
    output_root: Path,
    postgres_dsn: str = "",
) -> OwnerReleaseEvidence:
    """Query one service-owned immutable candidate without reading latest."""

    try:
        _service, schema = _OWNER_RELEASE_CONTROL[owner]
        command_path = _OWNER_RELEASE_CONTROL_COMMANDS[owner]
    except KeyError as exc:
        raise ValueError(f"未知 release owner：{owner}") from exc
    release_id = _strict_release_control_identity(release_id, label="releaseId")
    if _SHA256_DIGEST.fullmatch(manifest_digest) is None:
        raise ValueError("manifest_digest 必须是规范 sha256 digest")
    command = [
        "go", "run", command_path,
        "--operation", "query-candidate",
        "--mongo-uri", mongo_uri,
        "--env", env,
        "--source-owner", "qwq_data",
        "--report", str(report_path),
        "--release-id", release_id,
        "--manifest-digest", manifest_digest,
    ]
    if postgres_dsn:
        command.extend(["--postgres-dsn", postgres_dsn])
    _run_release_control(command)
    ref, digest = _receipt_evidence(report_path, output_root=output_root)
    document = _validate_release_control_receipt(
        report_path,
        schema=schema,
        environment=env,
        release_id=release_id,
        manifest_digest=manifest_digest,
    )
    if document.get("status") != "found":
        raise RuntimeError(f"{owner} verified candidate 未找到")
    return OwnerReleaseEvidence(document, report_path, ref, digest)


def query_tag_release_candidate(**kwargs: Any) -> OwnerReleaseEvidence:
    return query_owner_release_candidate(owner="tag", **kwargs)


def query_creator_release_candidate(**kwargs: Any) -> OwnerReleaseEvidence:
    return query_owner_release_candidate(owner="creator", **kwargs)


def query_homepage_release_candidate(**kwargs: Any) -> OwnerReleaseEvidence:
    return query_owner_release_candidate(owner="homepage", **kwargs)


def readback_owner_at_content_fence(
    *,
    owner: str,
    env: str,
    mongo_uri: str,
    fence: Mapping[str, Any],
    report_path: Path,
    output_root: Path,
    postgres_dsn: str = "",
) -> OwnerReleaseEvidence:
    """Read one owner projection at an explicit Content visibility fence."""

    try:
        command_path = _OWNER_RELEASE_CONTROL_COMMANDS[owner]
    except KeyError as exc:
        raise ValueError(f"未知 release owner：{owner}") from exc
    required = {
        "environment": env,
        "sourceOwner": "qwq_data",
        "releaseId": _strict_release_control_identity(fence.get("releaseId"), label="releaseId"),
        "manifestDigest": str(fence.get("manifestDigest") or ""),
        "revision": fence.get("revision"),
    }
    if (
        fence.get("environment") != env
        or fence.get("sourceOwner") != "qwq_data"
        or _SHA256_DIGEST.fullmatch(required["manifestDigest"]) is None
        or type(required["revision"]) is not int
        or required["revision"] <= 0
    ):
        raise ValueError("Content fence 必须是完整 environment/sourceOwner/releaseId/manifestDigest/revision tuple")
    command = [
        "go", "run", command_path,
        "--operation", "readback-at-content-fence",
        "--mongo-uri", mongo_uri,
        "--env", env,
        "--source-owner", "qwq_data",
        "--report", str(report_path),
        "--release-id", required["releaseId"],
        "--manifest-digest", required["manifestDigest"],
        "--content-revision", str(required["revision"]),
    ]
    if postgres_dsn:
        command.extend(["--postgres-dsn", postgres_dsn])
    _run_release_control(command)
    ref, digest = _receipt_evidence(report_path, output_root=output_root)
    payload = read_json(report_path)
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"{owner} fenced readback receipt 必须是对象")
    document = dict(payload)
    if document.get("status") != "passed" or any(
        document.get(field) != value for field, value in required.items()
    ):
        raise RuntimeError(f"{owner} fenced readback identity 不一致")
    return OwnerReleaseEvidence(document, report_path, ref, digest)


def readback_tag_at_content_fence(**kwargs: Any) -> OwnerReleaseEvidence:
    return readback_owner_at_content_fence(owner="tag", **kwargs)


def readback_creator_at_content_fence(**kwargs: Any) -> OwnerReleaseEvidence:
    return readback_owner_at_content_fence(owner="creator", **kwargs)


def readback_homepage_at_content_fence(**kwargs: Any) -> OwnerReleaseEvidence:
    return readback_owner_at_content_fence(owner="homepage", **kwargs)


def readback_content_at_content_fence(**kwargs: Any) -> OwnerReleaseEvidence:
    return readback_owner_at_content_fence(owner="content", **kwargs)


def query_content_release_candidate(
    *,
    env: str,
    mongo_uri: str,
    release_id: str,
    manifest_digest: str,
    report_path: Path,
    output_root: Path,
) -> OwnerReleaseEvidence:
    return query_owner_release_candidate(
        owner="content",
        env=env,
        mongo_uri=mongo_uri,
        release_id=release_id,
        manifest_digest=manifest_digest,
        report_path=report_path,
        output_root=output_root,
    )

def load_content_release_candidate_receipt(
    path: Path,
    *,
    output_root: Path,
    environment: str,
    release_id: str,
    manifest_digest: str,
    expected_digest: str,
) -> OwnerReleaseEvidence:
    return load_owner_release_candidate_receipt(
        path,
        owner="content",
        output_root=output_root,
        environment=environment,
        release_id=release_id,
        manifest_digest=manifest_digest,
        expected_digest=expected_digest,
    )

def query_content_active_release(
    *,
    env: str,
    mongo_uri: str,
    report_path: Path,
    output_root: Path,
) -> ContentReleaseEvidence:
    command = [
        "go",
        "run",
        "./services/content-service/cmd/release-control",
        "--operation",
        "query-active",
        "--mongo-uri",
        mongo_uri,
        "--env",
        env,
        "--source-owner",
        "qwq_data",
        "--report",
        str(report_path),
    ]
    _run_release_control(command)
    ref, digest = _receipt_evidence(report_path, output_root=output_root)
    document = _validate_release_control_receipt(
        report_path,
        schema="quwoquan.content_release_active_receipt",
        environment=env,
    )
    return ContentReleaseEvidence(document, report_path, ref, digest)


def activate_content_release(
    *,
    env: str,
    mongo_uri: str,
    release_id: str,
    manifest_digest: str,
    expected_active: Mapping[str, Any],
    report_path: Path,
    output_root: Path,
) -> ContentReleaseEvidence:
    if _SHA256_DIGEST.fullmatch(manifest_digest) is None:
        raise ValueError("manifest_digest 必须是规范 sha256 digest")
    command = [
        "go",
        "run",
        "./services/content-service/cmd/release-control",
        "--operation",
        "activate",
        "--mongo-uri",
        mongo_uri,
        "--env",
        env,
        "--source-owner",
        "qwq_data",
        "--report",
        str(report_path),
        "--release-id",
        _strict_release_control_identity(release_id, label="releaseId"),
        "--manifest-digest",
        manifest_digest,
    ]
    expected_document = _validate_release_control_document(
        expected_active,
        schema="quwoquan.content_release_active_receipt",
        environment=env,
        label="expected_active",
    )
    found = expected_document.get("status") == "found"
    if found:
        expected_release_id = _strict_release_control_identity(
            expected_document.get("releaseId"), label="expected releaseId"
        )
        expected_digest = str(expected_document.get("manifestDigest") or "")
        expected_revision = expected_document.get("revision")
        if (
            _SHA256_DIGEST.fullmatch(expected_digest) is None
            or type(expected_revision) is not int
            or expected_revision <= 0
        ):
            raise ValueError("expected active receipt 缺少完整 revision-bearing tuple")
        command.extend(
            [
                "--expected-active-release-id",
                expected_release_id,
                "--expected-active-manifest-digest",
                expected_digest,
                "--expected-active-revision",
                str(expected_revision),
            ]
        )
    else:
        command.append("--expected-active-empty")
    _run_release_control(command)
    ref, digest = _receipt_evidence(report_path, output_root=output_root)
    document = _validate_release_control_receipt(
        report_path,
        schema="quwoquan.content_release_activation_receipt",
        environment=env,
    )
    target = document.get("target")
    active = document.get("active")
    expected = document.get("expectedActive")
    previous = document.get("previousActive")
    if not all(
        isinstance(value, Mapping) for value in (target, active, expected, previous)
    ):
        raise RuntimeError("Content activation receipt identity 缺失")
    expected_found = bool(found)
    expected_release = str(expected_document.get("releaseId") or "")
    expected_digest = str(expected_document.get("manifestDigest") or "")
    expected_revision = int(expected_document.get("revision") or 0)
    if (
        target.get("releaseId") != release_id
        or target.get("manifestDigest") != manifest_digest
        or active.get("releaseId") != release_id
        or active.get("manifestDigest") != manifest_digest
        or expected.get("found") is not expected_found
        or expected.get("sourceOwner") != "qwq_data"
        or expected.get("revision") != expected_revision
        or (expected_found and expected.get("releaseId") != expected_release)
        or (expected_found and expected.get("manifestDigest") != expected_digest)
        or (
            not expected_found
            and ("releaseId" in expected or "manifestDigest" in expected)
        )
        or dict(previous) != dict(expected)
        or active.get("revision") != expected_revision + 1
    ):
        raise RuntimeError(
            "Content activation receipt target/expected/active identity 不一致"
        )
    return ContentReleaseEvidence(document, report_path, ref, digest)


def assert_content_release_evidence_unchanged(
    evidence: ContentReleaseEvidence,
) -> None:
    actual = file_byte_digest(evidence.path)
    if actual != evidence.digest:
        raise RuntimeError(
            "Content release receipt digest drift："
            f"expected={evidence.digest} actual={actual}"
        )


def assert_import_report_contract(
    report: Mapping[str, Any] | Path,
    *,
    source: Path | None = None,
    expected_release_id: str | None = None,
    expected_manifest_digest: str | None = None,
    expected_activation_mode: str | None = None,
) -> dict[str, Any]:
    if isinstance(report, Path):
        source = report
        report = read_json(report)
    if not isinstance(report, Mapping):
        raise ValueError(f"import report 必须是对象：{source or '<memory>'}")
    payload = dict(report)
    schema = str(payload.get("schema") or "")
    schema_name = _IMPORT_REPORT_SCHEMAS.get(schema)
    if not schema_name:
        raise SystemExit(
            f"[ship] 未登记 Schema import report：{schema or '<missing>'} "
            f"({source or '<memory>'})"
        )
    assert_valid(
        payload, "release", schema_name, label=f"import_report:{source or '<memory>'}"
    )
    if (
        expected_release_id is not None
        and str(payload.get("releaseId") or "") != expected_release_id
    ):
        raise RuntimeError(
            f"import report releaseId 不一致：expected={expected_release_id} "
            f"actual={payload.get('releaseId')}"
        )
    if (
        expected_manifest_digest is not None
        and payload.get("manifestDigest") != expected_manifest_digest
    ):
        raise RuntimeError(
            "import report manifestDigest 不一致："
            f"expected={expected_manifest_digest} actual={payload.get('manifestDigest')}"
        )
    activation_mode = expected_activation_mode or "stage-only"
    if "activationMode" in payload and payload.get("activationMode") != activation_mode:
        raise RuntimeError(
            "import report activationMode 不一致："
            f"expected={activation_mode} actual={payload.get('activationMode')}"
        )
    return payload


def run_content_importer(
    *,
    release: Path,
    env: str,
    run: Path,
    mongo_uri: str,
    media_avatar_base_url: str,
    media_image_base_url: str,
    media_video_base_url: str,
    dry_run: bool,
    mode: ImportMode = ImportMode.UPSERT,
    delete_policy: DeletePolicy = DeletePolicy.NONE,
    creator_candidate_receipt: Path,
) -> Path:
    """Stage exactly one Content candidate; activation uses release-control."""

    report_path = run / "import.json"
    creator_proof = creator_candidate_receipt
    command = [
        "go",
        "run",
        "./services/content-service/cmd/import",
        "--release-root",
        str(release),
        "--mongo-uri",
        mongo_uri,
        "--media-avatar-base-url",
        media_avatar_base_url,
        "--media-image-base-url",
        media_image_base_url,
        "--media-video-base-url",
        media_video_base_url,
        "--env",
        env,
        "--activation-mode",
        "stage-only",
        "--mode",
        mode,
        "--delete-policy",
        delete_policy,
        "--report",
        str(report_path),
        "--creator-receipt",
        str(creator_proof),
    ]
    if dry_run:
        command.append("--dry-run")
    result = subprocess.run(command, cwd=REPO_ROOT / "quwoquan_service", check=False)
    if result.returncode != 0:
        raise SystemExit(
            f"[ship] Content importer stage-only failed: exit={result.returncode}"
        )
    assert_import_report_contract(
        report_path,
        expected_release_id=release.name,
        expected_manifest_digest=payload_digest(release),
        expected_activation_mode="stage-only",
    )
    return report_path


def run_creator_importer(
    *,
    release: Path,
    env: str,
    run: Path,
    mongo_uri: str,
    postgres_dsn: str,
    media_avatar_base_url: str,
    dry_run: bool,
    mode: ImportMode = ImportMode.UPSERT,
) -> Path:
    """Stage one immutable Creator candidate before Content."""
    report_path = run / "creator-import.json"
    command = [
        "go",
        "run",
        "./services/user-service/cmd/release-import",
        "--release-root",
        str(release),
        "--mongo-uri",
        mongo_uri,
        "--postgres-dsn",
        postgres_dsn,
        "--media-avatar-base-url",
        media_avatar_base_url,
        "--env",
        env,
        "--run-id",
        run.name,
        "--activation-mode",
        "stage-only",
        "--mode",
        mode,
        "--report",
        str(report_path),
    ]
    if dry_run:
        command.append("--dry-run")
    result = subprocess.run(command, cwd=REPO_ROOT / "quwoquan_service", check=False)
    if result.returncode != 0:
        raise SystemExit(f"[ship] creator importer failed: exit={result.returncode}")
    report = assert_import_report_contract(
        report_path,
        expected_release_id=release.name,
        expected_manifest_digest=payload_digest(release),
        expected_activation_mode="stage-only",
    )
    desired = read_json(payload_file(release, "desired_state.json"))
    expected = sorted(
        str(item)
        for item in desired.get("desiredRefs", {}).get("creators", [])
        if str(item).strip()
    )
    if not dry_run and report.get("verifiedCreatorIds") != expected:
        raise SystemExit(
            "[ship] creator importer readback differs from release desired creators"
        )
    return report_path


def run_tag_importer(
    *,
    release: Path,
    env: str,
    run: Path,
    mongo_uri: str,
    dry_run: bool,
) -> Path:
    """Stage the exact immutable Tag candidate before dependent objects."""

    report_path = run / "tag-import.json"
    command = [
        "go",
        "run",
        "./services/tag-service/cmd/import",
        "--release-root",
        str(release),
        "--release-id",
        release.name,
        "--activation-mode",
        "stage-only",
        "--mongo-uri",
        mongo_uri,
        "--env",
        env,
        "--report",
        str(report_path),
    ]
    if dry_run:
        command.append("--dry-run")
    result = subprocess.run(command, cwd=REPO_ROOT / "quwoquan_service", check=False)
    if result.returncode != 0:
        raise SystemExit(f"[ship] tag importer failed: exit={result.returncode}")
    report = assert_import_report_contract(
        report_path,
        expected_release_id=release.name,
        expected_manifest_digest=payload_digest(release),
        expected_activation_mode="stage-only",
    )
    desired = read_json(payload_file(release, "desired_state.json"))
    expected = sorted(
        str(item)
        for item in desired.get("desiredRefs", {}).get("tags", [])
        if str(item).strip()
    )
    if report.get("tagRefs") != expected or report.get("nodeCount") != len(expected):
        raise SystemExit(
            "[ship] tag importer closure differs from release desired tags"
        )
    return report_path


def run_homepage_importer(
    *,
    release: Path,
    env: str,
    run: Path,
    run_id: str,
    mongo_uri: str,
    media_image_base_url: str,
    dry_run: bool,
    mode: ImportMode,
) -> dict[str, Any]:
    report_path = run / "homepage-import.json"
    command = [
        "go",
        "run",
        "./cmd/homepage-import",
        "--release-root",
        str(release),
        "--mongo-uri",
        mongo_uri,
        "--media-image-base-url",
        media_image_base_url,
        "--env",
        env,
        "--run-id",
        run_id,
        "--manifest-digest",
        payload_digest(release),
        "--report",
        str(report_path),
    ]
    if dry_run:
        command.append("--dry-run")
    result = subprocess.run(
        command,
        cwd=REPO_ROOT / "quwoquan_service" / "services" / "entity-service",
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"[ship] homepage importer failed: exit={result.returncode}")
    report = assert_import_report_contract(
        report_path,
        expected_release_id=release.name,
        expected_manifest_digest=payload_digest(release),
        expected_activation_mode="stage-only",
    )
    desired = read_json(payload_file(release, "desired_state.json"))
    expected = set(desired.get("desiredRefs", {}).get("entities", []))
    imported = set(report.get("entityRefToHomepageId", {}))
    missing = sorted(expected - imported) if not dry_run else []
    projected_mismatch = int(report.get("projected", -1)) != len(expected)
    if report.get("issues") or report.get("skipped") or missing:
        raise SystemExit(
            "[ship] homepage importer closure failed: "
            f"issues={len(report.get('issues', []))} "
            f"skipped={len(report.get('skipped', []))} missing={missing[:5]}"
        )
    if projected_mismatch:
        raise SystemExit(
            "[ship] homepage importer projection mismatch: "
            f"expected={len(expected)} projected={report.get('projected')}"
        )
    return report


__all__ = [
    "ContentReleaseEvidence",
    "OwnerReleaseEvidence",
    "activate_content_release",
    "assert_content_release_evidence_unchanged",
    "assert_import_report_contract",
    "file_byte_digest",
    "load_content_release_candidate_receipt",
    "load_owner_release_candidate_receipt",
    "load_content_release_receipt",
    "query_content_active_release",
    "query_content_release_candidate",
    "query_owner_release_candidate",
    "query_tag_release_candidate",
    "query_creator_release_candidate",
    "query_homepage_release_candidate",
    "readback_owner_at_content_fence",
    "readback_tag_at_content_fence",
    "readback_creator_at_content_fence",
    "readback_homepage_at_content_fence",
    "readback_content_at_content_fence",
    "run_tag_importer",
    "run_creator_importer",
    "run_content_importer",
    "run_homepage_importer",
]
