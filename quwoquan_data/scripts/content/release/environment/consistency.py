"""自治 canonical + immutable release overlay 一致性扫描。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json, write_json
from core.media_asset_url import build_release_media_manifest
from core.paths import PUBLISH_ROOT
from core.release_layout import payload_file

DESIRED_SCHEMA = "quwoquan_data.release_desired_state/1"


def _issue(code: str, message: str, ref: str = "") -> dict[str, str]:
    return {"severity": "blocking", "code": code, "message": message, "ref": ref}


def _tag_exists(root: Path, ref: str) -> bool:
    if not _safe_local_ref(ref):
        return False
    tag = root / "tags" / ref
    return (tag / "_definition.json").is_file()


def _creator_exists(root: Path, ref: str) -> bool:
    return bool(ref) and (root / "creators" / ref / "_creator.json").is_file()


def _safe_local_ref(ref: str) -> bool:
    candidate = Path(ref)
    return bool(ref) and not candidate.is_absolute() and ".." not in candidate.parts


def _creator_issues(root: Path, ref: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not _safe_local_ref(ref):
        return [_issue("unsafe_creator_ref", "creator desired ref 非法", ref)]
    creator_root = root / "creators" / ref
    header_path = creator_root / "_creator.json"
    if not header_path.is_file():
        return [_issue("desired_creator_missing", "creator object 不存在", ref)]
    header = read_json(header_path)
    if (
        header.get("schemaVersion") != "quwoquan_data.creator_object/1"
        or str(header.get("creatorId") or "") != Path(ref).name
    ):
        issues.append(_issue("creator_identity_mismatch", "creatorId/schema 与 desired ref 不一致", ref))
    local_paths: dict[str, Path] = {}
    for key in ("profileRef", "assetsRef", "worksRefsRef"):
        local_ref = str(header.get(key) or "")
        if not _safe_local_ref(local_ref):
            issues.append(_issue("invalid_creator_local_ref", f"{key} 非法", ref))
            continue
        local_path = creator_root / local_ref
        if not local_path.is_file():
            issues.append(_issue("creator_local_ref_missing", f"{key} 不可解析", ref))
            continue
        local_paths[key] = local_path
    profile_path = local_paths.get("profileRef")
    if profile_path is not None:
        profile = read_json(profile_path)
        if str(profile.get("userId") or "") != str(header.get("creatorId") or ""):
            issues.append(_issue("creator_profile_identity_mismatch", "profile.userId 与 creatorId 不一致", ref))
    assets_path = local_paths.get("assetsRef")
    if assets_path is not None:
        issues.extend(_cas_issues(root, read_json(assets_path), ref))
    works_path = local_paths.get("worksRefsRef")
    if works_path is not None:
        for line_number, line in enumerate(works_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                work = json.loads(line)
            except json.JSONDecodeError:
                issues.append(_issue("invalid_creator_work_ref", f"works refs 第 {line_number} 行不是 JSON", ref))
                continue
            work_ref = str(work.get("ref") or "")
            if work_ref and (not _safe_local_ref(work_ref) or not (root / work_ref).is_dir()):
                issues.append(_issue("dangling_creator_work_ref", work_ref, ref))
    for tag_ref in header.get("tagRefs") or []:
        if not _tag_exists(root, str(tag_ref)):
            issues.append(_issue("dangling_creator_tag_ref", str(tag_ref), ref))
    for entity_ref in header.get("entityRefs") or []:
        if not (root / "entities" / str(entity_ref)).is_dir():
            issues.append(_issue("dangling_creator_entity_ref", str(entity_ref), ref))
    return issues


def _cas_issues(root: Path, value: Any, source: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if isinstance(value, dict):
        key = value.get("objectKey")
        if isinstance(key, str):
            candidate = Path(key)
            if candidate.is_absolute() or ".." in candidate.parts:
                issues.append(_issue("asset_ref_path_escape", "asset ref 发生路径逃逸", source))
            elif not key.startswith("media/objects/sha256/"):
                issues.append(_issue("non_cas_asset_ref", "asset ref 不是 canonical CAS", source))
            elif not (root / key).is_file():
                issues.append(_issue("dangling_asset_ref", f"CAS object 不存在: {key}", source))
        for child in value.values():
            issues.extend(_cas_issues(root, child, source))
    elif isinstance(value, list):
        for child in value:
            issues.extend(_cas_issues(root, child, source))
    return issues


def _load_object_manifest(root: Path, kind: str, ref: str) -> tuple[Path, dict[str, Any]] | None:
    object_root = root / kind / ref.removeprefix(f"{kind}/")
    manifest = object_root / "manifest.json"
    if not manifest.is_file():
        return None
    return object_root, read_json(manifest)


def _release_media_issues(
    *,
    contract: Mapping[str, Any],
    canonical: Path,
    release_root: Path,
) -> list[dict[str, str]]:
    release_id = str(contract.get("releaseId") or "")
    desired = contract.get("desiredRefs") if isinstance(contract.get("desiredRefs"), Mapping) else {}
    expected = build_release_media_manifest(
        release_id=release_id,
        post_refs=sorted({str(ref) for ref in desired.get("posts") or [] if str(ref).strip()}),
        entity_refs=sorted({str(ref) for ref in desired.get("entities") or [] if str(ref).strip()}),
        publish_root=canonical,
    )
    issues: list[dict[str, str]] = []
    for message in expected["issues"]:
        issues.append(_issue("release_media_closure_invalid", str(message), release_id))
    path = payload_file(release_root, "media_manifest.json")
    if not path.is_file():
        return issues
    actual = read_json(path)
    if actual.get("schemaVersion") != "quwoquan_data.release_media_manifest/1":
        issues.append(_issue("release_media_schema_invalid", "media_manifest schemaVersion 非法", release_id))
    if str(actual.get("releaseId") or "") != release_id:
        issues.append(_issue("release_media_identity_mismatch", "media_manifest releaseId 不一致", release_id))
    actual_assets = actual.get("assets")
    if not isinstance(actual_assets, list):
        issues.append(_issue("release_media_assets_invalid", "media_manifest assets 必须为数组", release_id))
    elif actual_assets != expected["assets"]:
        issues.append(
            _issue(
                "release_media_closure_mismatch",
                "media_manifest 必须精确等于 desired objects 的 CAS 闭包，禁止携带无关 canonical media",
                release_id,
            )
        )
    return issues


def scan_release_contract(
    contract: Mapping[str, Any],
    *,
    publish_root: Path | None = None,
    release_root: Path | None = None,
    env_run_root: Path | None = None,
    phase: str = "preflight",
    metadata_root: Path | None = None,
) -> dict[str, Any]:
    del metadata_root
    canonical = publish_root or PUBLISH_ROOT
    issues: list[dict[str, str]] = []
    if contract.get("schemaVersion") != DESIRED_SCHEMA:
        issues.append(
            _issue(
                "legacy_release_contract_rejected",
                f"只接受 {DESIRED_SCHEMA}；禁止 v1/v2 dual-read",
            )
        )
    forbidden = {"env", "environment", "sampleRatio", "activatedAt", "importRun"}
    for key in forbidden:
        if key in contract:
            issues.append(_issue("release_not_environment_neutral", f"release 含环境字段: {key}"))
    desired = contract.get("desiredRefs") or {}
    posts = sorted({str(ref) for ref in desired.get("posts") or []})
    entities = sorted({str(ref) for ref in desired.get("entities") or []})
    creators = sorted({str(ref) for ref in desired.get("creators") or []})
    tags = sorted({str(ref) for ref in desired.get("tags") or []})
    required_tags: set[str] = set()
    actions = {
        (str(row.get("kind")), str(row.get("ref"))): row
        for row in contract.get("actions") or []
        if isinstance(row, dict)
    }
    for kind, refs in (("posts", posts), ("entities", entities)):
        for ref in refs:
            loaded = _load_object_manifest(canonical, kind, ref)
            if loaded is None:
                issues.append(_issue("desired_object_missing", f"{kind} object 不存在", ref))
                continue
            object_root, manifest = loaded
            final_ref = str(manifest.get("finalContentRef") or "")
            if not final_ref or Path(final_ref).is_absolute() or ".." in Path(final_ref).parts:
                issues.append(_issue("invalid_final_content_ref", "finalContentRef 非法", ref))
            elif not (object_root / final_ref).is_file():
                issues.append(_issue("final_content_missing", "final content 不存在", ref))
            for evidence_ref in ("sourceCatalogRef", "rightsRef", "creatorRefsRef", "tagRefsRef", "assetRefsRef"):
                rel = str(manifest.get(evidence_ref) or "")
                if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts or not (object_root / rel).is_file():
                    issues.append(_issue("object_evidence_missing", f"{evidence_ref} 不可解析", ref))
            creator_refs_path = object_root / str(manifest.get("creatorRefsRef") or "")
            if creator_refs_path.is_file():
                creator_refs = read_json(creator_refs_path).get("creatorRefs") or []
                for creator_ref in creator_refs:
                    if not _creator_exists(canonical, str(creator_ref)):
                        issues.append(_issue("dangling_creator_ref", str(creator_ref), ref))
            tag_refs_path = object_root / str(manifest.get("tagRefsRef") or "")
            if tag_refs_path.is_file():
                for tag_ref in read_json(tag_refs_path).get("tagRefs") or []:
                    tag_ref = str(tag_ref)
                    required_tags.add(tag_ref)
                    if not _tag_exists(canonical, tag_ref):
                        issues.append(_issue("dangling_tag_ref", tag_ref, ref))
            asset_refs_path = object_root / str(manifest.get("assetRefsRef") or "")
            if asset_refs_path.is_file():
                issues.extend(_cas_issues(canonical, read_json(asset_refs_path), ref))
            action = actions.get((kind[:-1], ref)) or actions.get((kind, ref))
            if action is not None and not action.get("sourceHash"):
                issues.append(_issue("missing_source_hash", "release action 缺少 sourceHash", ref))
    for ref in creators:
        issues.extend(_creator_issues(canonical, ref))
        header_path = canonical / "creators" / ref / "_creator.json"
        if header_path.is_file():
            required_tags.update(
                str(item)
                for item in read_json(header_path).get("tagRefs") or []
                if str(item).strip()
            )
    if tags != sorted(required_tags):
        issues.append(
            _issue(
                "release_tag_closure_mismatch",
                "desiredRefs.tags 必须精确等于 desired consumer objects 的 tagRefs 闭包",
                ",".join(sorted(required_tags)),
            )
        )
    for ref in tags:
        if not _tag_exists(canonical, ref):
            issues.append(_issue("desired_tag_missing", "tag snapshot 不存在", ref))
            continue
        if release_root is not None:
            release_snapshot = payload_file(release_root, f"objects/tags/{ref}/_definition.json")
            canonical_snapshot = canonical / "tags" / ref / "_definition.json"
            if not release_snapshot.is_file():
                issues.append(_issue("release_tag_snapshot_missing", "release 缺 tag snapshot", ref))
            elif release_snapshot.read_bytes() != canonical_snapshot.read_bytes():
                issues.append(_issue("release_tag_snapshot_mismatch", "release tag snapshot 与 canonical 不一致", ref))
    if release_root is not None:
        for name in ("release.json", "desired_state.json", "sample_bundle.json", "media_manifest.json", "index/objects.json"):
            if not payload_file(release_root, name).is_file():
                issues.append(_issue("release_artifact_missing", name, str(release_root)))
        issues.extend(
            _release_media_issues(
                contract=contract,
                canonical=canonical,
                release_root=release_root,
            )
        )
    if env_run_root is not None and phase != "preflight":
        required = {
            "post-write": "import.json",
            "post-write-pre-activation": "import.json",
            "post-activation": "activation-smoke.json",
        }.get(phase)
        if required and not (env_run_root / required).is_file():
            issues.append(_issue("environment_evidence_missing", required, str(env_run_root)))
    return {
        "schemaVersion": "quwoquan_data.release_consistency_report/2",
        "releaseId": contract.get("releaseId"),
        "phase": phase,
        "status": "failed" if issues else "passed",
        "blockingIssues": issues,
        "warnings": [],
        "danglingRefs": [
            issue
            for issue in issues
            if issue["code"].startswith("dangling") or issue["code"] == "desired_object_missing"
        ],
        "counts": {
            "blockingIssues": len(issues),
            "warnings": 0,
            "desiredPosts": len(posts),
            "desiredEntities": len(entities),
            "desiredCreators": len(creators),
            "desiredTags": len(tags),
            "danglingRefs": sum(
                issue["code"].startswith("dangling") or issue["code"] == "desired_object_missing"
                for issue in issues
            ),
        },
    }


def scan_release_file(
    path: Path,
    *,
    publish_root: Path | None = None,
    release_root: Path | None = None,
    env_run_root: Path | None = None,
    phase: str = "preflight",
    metadata_root: Path | None = None,
) -> dict[str, Any]:
    return scan_release_contract(
        read_json(path),
        publish_root=publish_root,
        release_root=release_root or path.parent,
        env_run_root=env_run_root,
        phase=phase,
        metadata_root=metadata_root,
    )


def write_consistency_report(report: Mapping[str, Any], out: Path) -> Path:
    write_json(out, dict(report))
    return out


def report_to_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"[data-release-consistency] release={report.get('releaseId')} "
        f"phase={report.get('phase')} status={report.get('status')}"
    ]
    for issue in report.get("blockingIssues") or []:
        lines.append(f"  BLOCK {issue.get('code')}: {issue.get('ref')} {issue.get('message')}")
    return "\n".join(lines)
