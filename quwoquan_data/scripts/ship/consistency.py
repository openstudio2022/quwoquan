"""数据发布一致性扫描器。

本模块先覆盖无需数据库的 preflight / artifact 检查：发布前必须证明
post/entity/tag/author/media 等引用闭包不会在环境中形成悬挂数据。
后续真实环境扫描可复用同一报告结构追加 Mongo/Postgres 查询结果。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from _common.io import read_json, write_json
from _common.media_asset_url import is_cas_media_object_key, sha256_file
from _common.paths import PUBLISH_ROOT

BLOCKING = "blocking"
WARNING = "warning"


def _issue(severity: str, code: str, message: str, ref: str = "") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "ref": ref}


def _tag_exists(publish_root: Path, tag_ref: str) -> bool:
    if not tag_ref:
        return True
    candidates = [
        publish_root / "tags" / tag_ref / "_definition.json",
        publish_root / "tags" / tag_ref / "_group.json",
        publish_root / "v1" / "tags" / tag_ref / "_definition.json",
        publish_root / "v1" / "tags" / tag_ref / "_group.json",
    ]
    return any(p.is_file() for p in candidates)


def _entity_has_page(publish_root: Path, entity_ref: str) -> bool:
    return (publish_root / "entities" / entity_ref / "page.md").is_file()


def _media_manifest_issues(publish_root: Path, contract: Mapping[str, Any]) -> list[dict[str, str]]:
    media = contract.get("mediaManifest")
    if not isinstance(media, Mapping):
        return []
    issues: list[dict[str, str]] = []
    rel_path = str(media.get("path") or "").strip()
    if not rel_path:
        return [_issue(BLOCKING, "missing_media_manifest_path", "mediaManifest 缺少 path")]
    manifest_path = publish_root / rel_path
    if not manifest_path.is_file():
        return [_issue(BLOCKING, "media_manifest_missing", f"media manifest 不存在: {rel_path}")]
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:  # noqa: BLE001 - consistency report should include parse failure.
        return [_issue(BLOCKING, "media_manifest_invalid", f"media manifest 不可解析: {exc}")]
    for issue in manifest.get("issues") or []:
        issues.append(_issue(BLOCKING, "media_manifest_issue", str(issue)))
    seen_sha_to_key: dict[tuple[str, str], str] = {}
    for asset in manifest.get("assets") or []:
        if not isinstance(asset, Mapping):
            issues.append(_issue(BLOCKING, "media_asset_invalid", "media asset 须为对象"))
            continue
        asset_id = str(asset.get("assetId") or "")
        object_key = str(asset.get("objectKey") or "")
        cdn_url = str(asset.get("cdnUrl") or "")
        sha256 = str(asset.get("sha256") or "")
        library_path = str(asset.get("libraryPath") or "")
        kind = str(asset.get("kind") or "image")
        ref = str(asset.get("sourceRef") or asset_id)
        if not object_key:
            issues.append(_issue(BLOCKING, "media_asset_missing_object_key", "media asset 缺少 objectKey", ref))
        elif not is_cas_media_object_key(object_key):
            issues.append(_issue(BLOCKING, "media_asset_non_cas_object_key", f"media asset objectKey 不符合 CAS 规则: {object_key}", ref))
        if not cdn_url.startswith("https://"):
            issues.append(_issue(BLOCKING, "media_asset_invalid_cdn_url", f"media asset cdnUrl 非 HTTPS: {cdn_url}", ref))
        if not (sha256.startswith("sha256:") and len(sha256) == len("sha256:") + 64):
            issues.append(_issue(BLOCKING, "media_asset_invalid_sha256", "media asset 缺少完整 sha256", ref))
        normalized_object_key = object_key.lstrip("/")
        cdn_path = urlparse(cdn_url).path.lstrip("/") if cdn_url else ""
        if cdn_url and normalized_object_key and cdn_path != normalized_object_key:
            issues.append(_issue(BLOCKING, "media_asset_cdn_url_mismatch", f"media asset cdnUrl 与 objectKey 不一致: {cdn_url}", ref))
        variants = asset.get("variants")
        if kind == "image":
            if not isinstance(variants, Mapping):
                issues.append(_issue(BLOCKING, "media_asset_missing_variants", "image asset 缺少 variants", ref))
            else:
                required_profiles = {"thumbnail", "display", "full", "original"}
                missing = sorted(required_profiles - {str(k) for k in variants.keys()})
                if missing:
                    issues.append(_issue(BLOCKING, "media_asset_missing_required_variants", f"image asset 缺少必要 variants: {missing}", ref))
                for profile, raw_variant in variants.items():
                    if not isinstance(raw_variant, Mapping):
                        issues.append(_issue(BLOCKING, "media_variant_invalid", f"variant 必须为对象: {profile}", ref))
                        continue
                    variant_key = str(raw_variant.get("objectKey") or "")
                    variant_url = str(raw_variant.get("cdnUrl") or "")
                    source_sha = str(raw_variant.get("sourceSha256") or raw_variant.get("sha256") or "")
                    if variant_key != object_key:
                        issues.append(_issue(BLOCKING, "media_variant_object_key_drift", f"variant objectKey 与 asset objectKey 不一致: {profile}", ref))
                    if not (source_sha.startswith("sha256:") and len(source_sha) == len("sha256:") + 64):
                        issues.append(_issue(BLOCKING, "media_variant_invalid_sha", f"variant 缺少 sourceSha256: {profile}", ref))
                    if profile == "original":
                        if variant_url:
                            issues.append(_issue(BLOCKING, "media_original_url_exposed", "original variant 不得默认暴露 cdnUrl", ref))
                        if raw_variant.get("requiresAccess") is not True:
                            issues.append(_issue(BLOCKING, "media_original_missing_access_gate", "original variant 必须 requiresAccess=true", ref))
                    elif not variant_url.startswith("https://"):
                        issues.append(_issue(BLOCKING, "media_variant_invalid_cdn_url", f"variant cdnUrl 非 HTTPS: {profile}", ref))
        elif kind == "video":
            if not isinstance(variants, Mapping):
                issues.append(_issue(BLOCKING, "video_asset_missing_variants", "video asset 缺少 variants", ref))
            else:
                required_profiles = {"adaptive", "original"}
                missing = sorted(required_profiles - {str(k) for k in variants.keys()})
                if missing:
                    issues.append(_issue(BLOCKING, "video_asset_missing_required_variants", f"video asset 缺少必要 variants: {missing}", ref))
                original = variants.get("original")
                if isinstance(original, Mapping):
                    if str(original.get("cdnUrl") or ""):
                        issues.append(_issue(BLOCKING, "video_original_url_exposed", "video original variant 不得默认暴露 cdnUrl", ref))
                    if original.get("requiresAccess") is not True:
                        issues.append(_issue(BLOCKING, "video_original_missing_access_gate", "video original variant 必须 requiresAccess=true", ref))
                adaptive = variants.get("adaptive")
                if isinstance(adaptive, Mapping) and not str(adaptive.get("cdnUrl") or "").startswith("https://"):
                    issues.append(_issue(BLOCKING, "video_adaptive_invalid_cdn_url", "video adaptive variant cdnUrl 非 HTTPS", ref))
        if not library_path or not (publish_root / library_path).is_file():
            issues.append(_issue(BLOCKING, "media_asset_library_missing", f"media library 文件不存在: {library_path}", ref))
        else:
            actual_sha256 = sha256_file(publish_root / library_path)
            if actual_sha256 != sha256:
                issues.append(_issue(BLOCKING, "media_asset_library_sha_mismatch", f"media library 文件 sha256 与 manifest 不一致: {library_path}", ref))
        dedupe_key = (kind, sha256)
        old_object_key = seen_sha_to_key.get(dedupe_key)
        if old_object_key and old_object_key != object_key:
            issues.append(_issue(BLOCKING, "media_asset_duplicate_sha_object_key", f"同 kind+sha256 映射多个 objectKey: {sha256}", ref))
        elif object_key:
            seen_sha_to_key[dedupe_key] = object_key
    if int((manifest.get("counts") or {}).get("issues") or 0) > 0:
        issues.append(_issue(BLOCKING, "media_manifest_has_issues", "media manifest 存在未解决 issue"))
    return issues


def _collect_fixture_user_ids(metadata_root: Path) -> set[str]:
    ids: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"userId", "authorId", "subAccountId"} and isinstance(item, str) and item.startswith("fixture_"):
                    ids.add(item)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    user_fixture_root = metadata_root / "user" / "test_fixtures" / "scenarios"
    if not user_fixture_root.is_dir():
        return ids
    for path in sorted(user_fixture_root.glob("*.json")):
        try:
            walk(read_json(path))
        except Exception:  # noqa: BLE001 - scanner reports missing refs; malformed fixtures are covered elsewhere.
            continue
    return ids


def _release_artifact_dir(root: Path, contract: Mapping[str, Any]) -> Path:
    release_id = str(contract.get("releaseId") or "unknown")
    return root / "env_releases" / release_id


def _environment_observability_issues(root: Path, contract: Mapping[str, Any], phase: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    release_dir = _release_artifact_dir(root, contract)
    env = str(contract.get("environment") or "")
    issues: list[dict[str, str]] = []
    observability: dict[str, Any] = {"releaseArtifactDir": str(release_dir), "phase": phase}
    if phase in {"post-write-pre-activation", "post-write"}:
        import_report = release_dir / f"import-report-{env}.json"
        observability["importReport"] = str(import_report)
        if not import_report.is_file():
            issues.append(_issue(BLOCKING, "missing_post_write_import_report", "post-write 阶段缺少 importer report", str(import_report)))
        else:
            report = read_json(import_report)
            observability["importReportStatus"] = report.get("status") or "present"
            if str(report.get("releaseId") or "") not in {"", str(contract.get("releaseId") or "")}:
                issues.append(_issue(BLOCKING, "import_report_release_mismatch", "import report releaseId 与 contract 不一致", str(import_report)))
    if phase == "post-activation":
        active_report = release_dir / f"activation-smoke-{env}.json"
        observability["activationSmokeReport"] = str(active_report)
        if not active_report.is_file():
            issues.append(_issue(BLOCKING, "missing_activation_smoke_report", "post-activation 阶段缺少 activeReleaseId/API smoke 报告", str(active_report)))
        else:
            smoke = read_json(active_report)
            observability["activeReleaseId"] = smoke.get("activeReleaseId")
            if smoke.get("activeReleaseId") != contract.get("releaseId"):
                issues.append(_issue(BLOCKING, "active_release_mismatch", "API activeReleaseId 与 contract releaseId 不一致", str(active_report)))
            failed = [s for s in smoke.get("apiSmoke") or [] if not s.get("passed")]
            if failed:
                issues.append(_issue(BLOCKING, "api_smoke_failed", f"post-activation API smoke failed: {len(failed)}", str(active_report)))
    return issues, observability


def scan_release_contract(
    contract: Mapping[str, Any],
    *,
    publish_root: Path | None = None,
    metadata_root: Path | None = None,
    phase: str = "preflight",
) -> dict[str, Any]:
    root = publish_root or PUBLISH_ROOT
    meta_root = metadata_root or root.parent.parent / "quwoquan_service" / "contracts" / "metadata"
    fixture_user_ids = _collect_fixture_user_ids(meta_root)
    desired = contract.get("desiredRefs") or {}
    active_entities = {str(ref) for ref in desired.get("entities") or []}
    active_posts = {str(ref) for ref in desired.get("posts") or []}
    issues: list[dict[str, str]] = []
    dangling_refs: list[dict[str, str]] = []

    if contract.get("environment") == "prod" and contract.get("deletePolicy") == "hard-delete" and not contract.get("approvedBy"):
        issues.append(_issue(BLOCKING, "prod_hard_delete_without_approval", "生产硬删除缺少 approvedBy"))
    issues.extend(_media_manifest_issues(root, contract))
    obs_issues, observability = _environment_observability_issues(root, contract, phase)
    issues.extend(obs_issues)

    for action in contract.get("actions") or []:
        kind = str(action.get("kind") or "")
        ref = str(action.get("ref") or "")
        if not action.get("sourceHash"):
            issues.append(_issue(BLOCKING, "missing_source_hash", "action 缺少 sourceHash", ref))
        if kind == "entity" and not _entity_has_page(root, ref):
            issues.append(_issue(WARNING, "entity_page_missing", "entity 缺少 page.md，可能影响实体主页", ref))
        if kind != "post":
            continue
        if ref not in active_posts:
            issues.append(_issue(BLOCKING, "post_action_not_in_desired_refs", "post action 不在 desiredRefs.posts 中", ref))
        for entity_ref in action.get("entityRefs") or []:
            entity_ref = str(entity_ref)
            if entity_ref not in active_entities:
                dangling_refs.append({"from": ref, "to": entity_ref, "type": "post_entity"})
                issues.append(_issue(BLOCKING, "dangling_post_entity_ref", f"post 引用未入本 release 的 entity: {entity_ref}", ref))
        for tag_ref in action.get("tagRefs") or []:
            tag_ref = str(tag_ref)
            if not _tag_exists(root, tag_ref):
                dangling_refs.append({"from": ref, "to": tag_ref, "type": "post_tag"})
                issues.append(_issue(BLOCKING, "dangling_post_tag_ref", f"post 引用不存在的 tag: {tag_ref}", ref))
        author_id = str(action.get("authorId") or "")
        if author_id.startswith("fixture_") and author_id not in fixture_user_ids:
            dangling_refs.append({"from": ref, "to": author_id, "type": "post_fixture_user"})
            issues.append(_issue(BLOCKING, "dangling_post_fixture_author", f"post 引用不存在的 fixture user: {author_id}", ref))

    blocking = [i for i in issues if i["severity"] == BLOCKING]
    warnings = [i for i in issues if i["severity"] == WARNING]
    return {
        "schemaVersion": "quwoquan.data_release_consistency_report.v1",
        "releaseId": contract.get("releaseId"),
        "environment": contract.get("environment"),
        "phase": phase,
        "status": "failed" if blocking else "passed",
        "blockingIssues": blocking,
        "warnings": warnings,
        "danglingRefs": dangling_refs,
        "dirtyRows": [],
        "orphanReadModels": [],
        "sourceOwnerDrift": [],
        "observability": observability,
        "counts": {
            "blockingIssues": len(blocking),
            "warnings": len(warnings),
            "danglingRefs": len(dangling_refs),
        },
    }


def scan_release_file(path: Path, *, publish_root: Path | None = None, metadata_root: Path | None = None, phase: str = "preflight") -> dict[str, Any]:
    return scan_release_contract(read_json(path), publish_root=publish_root, metadata_root=metadata_root, phase=phase)


def write_consistency_report(report: Mapping[str, Any], out: Path) -> Path:
    write_json(out, dict(report))
    return out


def report_to_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"[data-release-consistency] release={report.get('releaseId')} env={report.get('environment')} phase={report.get('phase')} status={report.get('status')}",
        f"  blocking={len(report.get('blockingIssues') or [])} warnings={len(report.get('warnings') or [])} dangling={len(report.get('danglingRefs') or [])}",
    ]
    for issue in report.get("blockingIssues") or []:
        lines.append(f"  BLOCK {issue.get('code')}: {issue.get('ref')} {issue.get('message')}")
    for issue in report.get("warnings") or []:
        lines.append(f"  WARN {issue.get('code')}: {issue.get('ref')} {issue.get('message')}")
    return "\n".join(lines)
