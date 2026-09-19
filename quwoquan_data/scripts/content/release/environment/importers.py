"""Release-bound service importer execution and report validation."""

from __future__ import annotations

import os
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
    "quwoquan.content_import_report": ("release", "import_report"),
    "quwoquan.tag_import_report": ("release", "tag_import_report"),
    "quwoquan.user_creator_import_report": ("release", "creator_import_report"),
    "quwoquan_service.homepage_import_report": ("release", "homepage_import_report"),
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
    "quwoquan.content_release_candidate_receipt": ("release", "content_release_candidate_receipt"),
    "quwoquan.content_release_active_receipt": ("release", "content_release_active_receipt"),
    "quwoquan.content_release_activation_receipt": ("release", "content_release_activation_receipt"),
    "quwoquan.tag_release_candidate_receipt": ("release", "tag_release_candidate_receipt"),
    "quwoquan.creator_release_candidate_receipt": ("release", "creator_release_candidate_receipt"),
    "quwoquan.homepage_release_candidate_receipt": ("release", "homepage_release_candidate_receipt"),
}

_OWNER_RELEASE_CONTROL = {
    "content": ("content-service", "quwoquan.content_release_candidate_receipt"),
    "tag": ("tag-service", "quwoquan.tag_release_candidate_receipt"),
    "creator": ("user-service", "quwoquan.creator_release_candidate_receipt"),
    "homepage": ("entity-service", "quwoquan.homepage_release_candidate_receipt"),
}

# All release-control commands intentionally share one service-root cwd and one
# flag surface. Mongo URI remains argv-only and is never included in failures.

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
    receipt_schema_target = _RELEASE_RECEIPT_SCHEMAS.get(schema)
    if not receipt_schema_target or document.get("schema") != schema:
        raise RuntimeError(
            "Content release receipt schema 不一致："
            f"expected={schema} actual={document.get('schema')}"
        )
    assert_valid(document, *receipt_schema_target, label=f"{receipt_schema_target[1]}:{label}")
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



def _candidate_binary_command(
    *,
    image_ref: str,
    binary: str,
    arguments: list[str],
    path_mappings: tuple[tuple[Path, str, bool], ...],
) -> list[str]:
    """Execute one packaged binary with host paths projected into the container."""
    image = image_ref.strip()
    if not image:
        raise RuntimeError(f"candidate-packaged {binary} image is required")

    mappings: list[tuple[str, str, bool]] = []
    for source, destination, read_only in path_mappings:
        host_path = str(source.resolve())
        if any(existing == host_path for existing, _target, _ro in mappings):
            raise ValueError(f"candidate path mapping source 重复：{host_path}")
        mappings.append((host_path, destination, read_only))

    def container_argument(value: str) -> str:
        for source, destination, _read_only in mappings:
            if value == source:
                return destination
            prefix = source.rstrip("/") + "/"
            if value.startswith(prefix):
                return destination.rstrip("/") + "/" + value[len(prefix):]
        return value

    command = [
        "docker", "run", "--rm", "--network", "host",
        "--user", f"{os.geteuid()}:{os.getegid()}",
    ]
    for source, destination, read_only in mappings:
        mode = ":ro" if read_only else ""
        command.extend(("-v", f"{source}:{destination}{mode}"))
    command.extend((
        "--entrypoint", f"/usr/local/bin/{binary}", image,
        *(container_argument(value) for value in arguments),
    ))
    return command

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
    importer_image_ref: str,
) -> OwnerReleaseEvidence:
    """Query one service-owned immutable candidate without reading latest."""

    try:
        _service, schema = _OWNER_RELEASE_CONTROL[owner]
    except KeyError as exc:
        raise ValueError(f"未知 release owner：{owner}") from exc
    release_id = _strict_release_control_identity(release_id, label="releaseId")
    if _SHA256_DIGEST.fullmatch(manifest_digest) is None:
        raise ValueError("manifest_digest 必须是规范 sha256 digest")
    arguments = [
        "--operation", "query-candidate",
        "--mongo-uri", mongo_uri,
        "--env", env,
        "--source-owner", "qwq_data",
        "--report", str(report_path),
        "--release-id", release_id,
        "--manifest-digest", manifest_digest,
    ]
    command = _candidate_binary_command(
        image_ref=importer_image_ref, binary=f"{owner}-release-control",
        arguments=arguments, path_mappings=((output_root, "/run/quwoquan/release-control-output", False),),
    )
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
    importer_image_ref: str,
) -> OwnerReleaseEvidence:
    """Read one owner projection at an explicit Content visibility fence."""

    if owner not in _OWNER_RELEASE_CONTROL:
        raise ValueError(f"未知 release owner：{owner}")
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
    arguments = [
        "--operation", "readback-at-content-fence",
        "--mongo-uri", mongo_uri,
        "--env", env,
        "--source-owner", "qwq_data",
        "--report", str(report_path),
        "--release-id", required["releaseId"],
        "--manifest-digest", required["manifestDigest"],
        "--content-revision", str(required["revision"]),
    ]
    command = _candidate_binary_command(
        image_ref=importer_image_ref, binary=f"{owner}-release-control",
        arguments=arguments, path_mappings=((output_root, "/run/quwoquan/release-control-output", False),),
    )
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
    importer_image_ref: str,
) -> OwnerReleaseEvidence:
    return query_owner_release_candidate(
        owner="content",
        env=env,
        mongo_uri=mongo_uri,
        release_id=release_id,
        manifest_digest=manifest_digest,
        report_path=report_path,
        output_root=output_root,
        importer_image_ref=importer_image_ref,
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
    importer_image_ref: str,
) -> ContentReleaseEvidence:
    arguments = [
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
    command = _candidate_binary_command(
        image_ref=importer_image_ref,
        binary="content-release-control",
        arguments=arguments,
        path_mappings=((output_root, "/run/quwoquan/release-control-output", False),),
    )
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
    importer_image_ref: str,
) -> ContentReleaseEvidence:
    if _SHA256_DIGEST.fullmatch(manifest_digest) is None:
        raise ValueError("manifest_digest 必须是规范 sha256 digest")
    arguments = [
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
        arguments.extend(
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
        arguments.append("--expected-active-empty")
    command = _candidate_binary_command(
        image_ref=importer_image_ref,
        binary="content-release-control",
        arguments=arguments,
        path_mappings=((output_root, "/run/quwoquan/release-control-output", False),),
    )
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
    import_schema_target = _IMPORT_REPORT_SCHEMAS.get(schema)
    if not import_schema_target:
        raise SystemExit(
            f"[ship] 未登记 Schema import report：{schema or '<missing>'} "
            f"({source or '<memory>'})"
        )
    assert_valid(
        payload, *import_schema_target, label=f"import_report:{source or '<memory>'}"
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


def _validate_homepage_mapping_input(
    *, release: Path, environment: str, report_path: Path, candidate_path: Path,
) -> None:
    """只认证既有 Entity report；candidate 摘要不能由裸 report 自证。"""
    import hashlib
    import json

    manifest_digest = payload_digest(release)
    candidate = _validate_release_control_receipt(
        candidate_path, schema="quwoquan.homepage_release_candidate_receipt",
        environment=environment, release_id=release.name, manifest_digest=manifest_digest,
    )
    report = assert_import_report_contract(
        report_path, expected_release_id=release.name,
        expected_manifest_digest=manifest_digest,
    )
    expected = set(read_json(payload_file(release, "desired_state.json"))["desiredRefs"]["entities"])
    mapping = report.get("entityRefToHomepageId")
    if (candidate.get("status") != "found" or report.get("dryRun") is not False
            or report.get("env") != environment or report.get("issues")
            or not isinstance(mapping, dict) or set(mapping) != expected
            or any(not isinstance(value, str) or not value or value != value.strip() for value in mapping.values())
            or len(set(mapping.values())) != len(mapping)):
        raise RuntimeError("homepage mapping proof identity/closure mismatch")
    counts = candidate["counts"]
    if (counts["expected"] != len(expected) or counts["projected"] != len(expected)
            or report["expected"] != len(expected) or report["projected"] != len(expected)
            or report["projectionVersion"] != candidate["projectionVersion"]
            or report["closureDigest"] != candidate["closureDigest"]):
        raise RuntimeError("homepage mapping proof candidate projection drift")
    entries = [{"entityRef": ref, "homepageId": mapping[ref]} for ref in sorted(mapping)]
    # 匹配 Entity 的 json.Marshal（包括 HTML / U+2028 / U+2029 escape），仅核对映射摘要。
    encoded = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    for char, escaped in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                          ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        encoded = encoded.replace(char, escaped)
    digest = "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if digest != report["entityRefMappingDigest"] or digest != candidate["entityRefMappingDigest"]:
        raise RuntimeError("homepage mapping proof mapping digest drift")


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
    homepage_import_report: Path,
    homepage_candidate_receipt: Path | None,
    mongo_database: str = "quwoquan_content",
    post_safety_material_root: Path | None = None,
    post_safety_current_binding_ref: str = "",
    post_safety_recovery_evidence_ref: str = "",
    post_safety_hmac_secret_ref: str = "",
    runtime_auth_env_ref: Path | None = None,
    runtime_auth_issuer: str = "",
    runtime_auth_audience: str = "",
    runtime_auth_token_version: str = "",
    account_security_authority_base_url: str = "",
    account_security_authority_timeout_ms: int = 0,
    importer_image_ref: str = "",
) -> Path:
    """Stage exactly one Content candidate; activation uses release-control."""

    if dry_run:
        if homepage_candidate_receipt is not None:
            raise RuntimeError("dry-run must not consume a homepage candidate mapping")
    else:
        if homepage_candidate_receipt is None:
            raise RuntimeError("Content stage requires exact homepage candidate proof")
        _validate_homepage_mapping_input(
            release=release, environment=env, report_path=homepage_import_report,
            candidate_path=homepage_candidate_receipt,
        )
    report_path = run / "import.json"
    creator_proof = creator_candidate_receipt
    arguments = [
        "--release-root",
        str(release),
        "--mongo-uri",
        mongo_uri,
        "--posts-db",
        mongo_database,
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
        "--homepage-report",
        str(homepage_import_report),
    ]
    if homepage_candidate_receipt is not None:
        arguments.extend(["--homepage-candidate-receipt", str(homepage_candidate_receipt)])
    if not dry_run:
        locators = {
            "--post-safety-material-root": str(post_safety_material_root or ""),
            "--post-safety-current-binding-ref": post_safety_current_binding_ref,
            "--post-safety-recovery-evidence-ref": post_safety_recovery_evidence_ref,
            "--post-safety-hmac-secret-ref": post_safety_hmac_secret_ref,
            "--runtime-auth-env-ref": str(runtime_auth_env_ref or ""),
            "--runtime-auth-issuer": runtime_auth_issuer,
            "--runtime-auth-audience": runtime_auth_audience,
            "--runtime-auth-token-version": runtime_auth_token_version,
            "--account-security-authority-base-url": account_security_authority_base_url,
        }
        missing_locators = [name for name, value in locators.items() if not value.strip()]
        if missing_locators:
            raise RuntimeError(
                "Content stage requires canonical Post safety startup locators: "
                + ",".join(missing_locators)
            )
        if account_security_authority_timeout_ms <= 0:
            raise RuntimeError("Content stage requires positive account authority timeout")
        for flag_name, value in locators.items():
            arguments.extend([flag_name, value])
        arguments.extend([
            "--account-security-authority-timeout-ms",
            str(account_security_authority_timeout_ms),
        ])
        if not importer_image_ref.strip():
            raise RuntimeError("Content stage requires candidate-packaged importer image")
        container_release = "/run/quwoquan/release"
        container_run = "/run/quwoquan/import-run"
        container_material = "/run/quwoquan/post-safety"
        container_auth_env = "/run/quwoquan/runtime-auth.env"
        replacements = (
            (str(release), container_release),
            (str(run), container_run),
            (str(post_safety_material_root), container_material),
            (str(runtime_auth_env_ref), container_auth_env),
        )
        def container_value(value: str) -> str:
            for source, destination in replacements:
                if value == source:
                    return destination
                prefix = source.rstrip("/") + "/"
                if value.startswith(prefix):
                    return destination.rstrip("/") + "/" + value[len(prefix):]
            return value
        importer_args = [container_value(value) for value in arguments]
        command = [
            "docker", "run", "--rm", "--network", "host",
            "--user", f"{os.geteuid()}:{os.getegid()}",
            "-v", f"{release}:{container_release}:ro",
            "-v", f"{run}:{container_run}",
            "-v", f"{post_safety_material_root}:{container_material}:ro",
            "-v", f"{runtime_auth_env_ref}:{container_auth_env}:ro",
            "--entrypoint", "/usr/local/bin/content-import",
            importer_image_ref,
            *importer_args,
        ]
    else:
        arguments.append("--dry-run")
        command = _candidate_binary_command(
        image_ref=importer_image_ref,
        binary="content-import",
        arguments=arguments,
        path_mappings=(
            (release, "/run/quwoquan/release", True),
            (run, "/run/quwoquan/import-run", False),
        ),
    )
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
    mongo_database: str = "quwoquan_user",
    importer_image_ref: str = "",
) -> Path:
    """Stage one immutable Creator candidate before Content."""
    report_path = run / "creator-import.json"
    arguments = [
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
        arguments.append("--dry-run")
    command = _candidate_binary_command(
        image_ref=importer_image_ref,
        binary="creator-import",
        arguments=arguments,
        path_mappings=(
            (release, "/run/quwoquan/release", True),
            (run, "/run/quwoquan/import-run", False),
        ),
    )
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
    mongo_database: str = "quwoquan_tag",
    importer_image_ref: str = "",
) -> Path:
    """Stage the exact immutable Tag candidate before dependent objects."""

    report_path = run / "tag-import.json"
    arguments = [
        "--release-root",
        str(release),
        "--release-id",
        release.name,
        "--activation-mode",
        "stage-only",
        "--mongo-uri",
        mongo_uri,
        "--db",
        mongo_database,
        "--env",
        env,
        "--report",
        str(report_path),
    ]
    if dry_run:
        arguments.append("--dry-run")
    command = _candidate_binary_command(
        image_ref=importer_image_ref,
        binary="tag-import",
        arguments=arguments,
        path_mappings=(
            (release, "/run/quwoquan/release", True),
            (run, "/run/quwoquan/import-run", False),
        ),
    )
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
    mongo_database: str = "quwoquan_entity",
    importer_image_ref: str = "",
) -> dict[str, Any]:
    report_path = run / "homepage-import.json"
    arguments = [
        "--release-root",
        str(release),
        "--mongo-uri",
        mongo_uri,
        "--entity-db",
        mongo_database,
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
        arguments.append("--dry-run")
    command = _candidate_binary_command(
        image_ref=importer_image_ref,
        binary="homepage-import",
        arguments=arguments,
        path_mappings=(
            (release, "/run/quwoquan/release", True),
            (run, "/run/quwoquan/import-run", False),
        ),
    )
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
    projected_mismatch = not dry_run and int(report.get("projected", -1)) != len(expected)
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
