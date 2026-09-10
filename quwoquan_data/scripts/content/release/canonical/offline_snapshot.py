"""显式 canonical cohort → 完整 Alpha 离线包；独立下游派生，不调用 producer。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re

from content.release.canonical.offline_snapshot_contract import (
    OfflineSnapshotError, PublicContractValidator, canonical_bytes, digest, digest_bytes, safe_path, validate_bundle, validate_selection,
)
from content.release.canonical.offline_snapshot_projection import (
    ENTITY_ROOT, IMPORT_ROOT, project_configuration, project_creators, project_homepages, project_post,
)
from content.release.canonical.offline_snapshot_source import CanonicalSource, capture_closure, capture_media


@dataclass
class OfflineBundle:
    manifest: dict
    media_bytes: dict[str, bytes]


def build_bundle(*, repo: Path, publish_root: Path, selection: dict, source_revision: str,
                 library_root: Path | None = None, carried_root: Path | None = None) -> OfflineBundle:
    validate_selection(selection)
    if re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
        raise OfflineSnapshotError("OFFLINE.SOURCE_REVISION_INVALID")
    source = CanonicalSource(publish_root)
    post_refs = selection["objectRefs"]
    entities, creators, tags = capture_closure(source, post_refs)
    owners = post_refs + ["entities/" + ref for ref in entities] + ["creators/" + ref for ref in creators]
    media, bodies = capture_media(source, owners, library=library_root, carried=carried_root)
    media_by_id = {m["assetId"]: m for m in media}
    validator = PublicContractValidator(repo)
    posts = [project_post(source, ref, media_by_id, validator) for ref in post_refs]
    configuration = project_configuration(validator)
    selected_at = selection["selectedAt"]
    author_views = project_creators(source, creators, media_by_id, posts, selected_at)
    homepage_views = project_homepages(source, entities, media_by_id, selected_at, validator)
    for row in author_views:
        validator.validate_type(row["projection"], "PersonaProfileView")
    for row in homepage_views:
        validator.validate_homepage(row["projection"])
    tag_views = [{"tagRef": ref, "definition": source.json(f"tags/{ref}/_definition.json")} for ref in tags]
    source.assert_unchanged()
    files = source.file_facts()
    cohort_digest = digest({"objectRefs": post_refs, "sourceFiles": files})
    selection_digest = digest(selection)
    post_ids = {p["sourceObjectRef"]: p["projection"]["postId"] for p in posts}
    channels = [{"channelId": row["channelId"], "orderedPostIds": [post_ids[ref] for ref in row["orderedObjectRefs"]],
                 "selectionDigest": selection_digest} for row in selection["channels"]]
    counts = {"posts": len(posts), **{kind: sum(p["projection"]["contentType"] == kind for p in posts) for kind in ("article", "image", "video")},
              "creators": len(creators), "homepages": len(entities), "tags": len(tags), "media": len(bodies), "mediaBytes": sum(len(b) for b in bodies.values())}
    # importer 身份/投影实现也绑定源字节；禁止构建期悄悄漂移而沿用旧 manifest pin。
    for ref in (f"{IMPORT_ROOT}/runtime.go", f"{IMPORT_ROOT}/loader.go", f"{IMPORT_ROOT}/article_summary_projection.go",
                f"{ENTITY_ROOT}/domain/model/homepage.go", f"{ENTITY_ROOT}/infrastructure/homepageimport/loader.go",
                "quwoquan_data/schema/release/offline_content_bundle.schema.json", "quwoquan_data/schema/release/offline_operator_selection.schema.json",
                "quwoquan_data/schema/content/post_manifest.schema.json", "quwoquan_data/scripts/core/article_package.py", "quwoquan_data/scripts/core/media_asset_url.py",
                *(f"quwoquan_data/scripts/content/release/canonical/{name}.py" for name in ("offline_snapshot", "offline_snapshot_source", "offline_snapshot_projection", "offline_snapshot_contract"))):
        validator.files[ref] = safe_path(repo, ref).read_bytes()
    contract_files = [{"ref": ref, "sha256": digest_bytes(raw), "byteLength": len(raw)} for ref, raw in sorted(validator.files.items())]
    provenance = {"kind": "explicit_canonical_cohort", "purpose": "alpha_offline_engineering", "sourceRevision": source_revision,
                  "operatorSelection": selection, "sourceFiles": files, "contractFiles": contract_files,
                  "sourceAttributions": [{"sourceObjectRef": ref, "document": source.json(ref + "/manifest.json")["sourceAttribution"]} for ref in post_refs + ["entities/" + e for e in entities]],
                  "projectionPolicy": "canonical_import_initial_public_read_v1"}
    bundle = {"schema": "quwoquan.offline_content_bundle", "version": 1, "sourceOwner": "qwq_data", "provenance": provenance,
              "cohortDigest": cohort_digest, "selectionDigest": selection_digest, "configurationDigest": digest(configuration),
              "posts": posts, "channels": channels, "creators": author_views, "homepages": homepage_views, "tags": tag_views,
              "configuration": configuration, "media": media, "counts": counts}
    bundle["bundleId"] = "alpha-" + digest(bundle).removeprefix("sha256:")
    validate_bundle(bundle, validator)
    source.assert_unchanged()
    for ref, raw in validator.files.items():
        if safe_path(repo, ref).read_bytes() != raw:
            raise OfflineSnapshotError("OFFLINE.CONTRACT_CHANGED_DURING_CAPTURE")
    return OfflineBundle(bundle, bodies)


def _atomic_file(path: Path, raw: bytes) -> None:
    if path.exists() and path.read_bytes() == raw:
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    # exclusive 创建只属于本次输出；不覆盖其他 session 的临时文件。
    created = False
    try:
        with temporary.open("xb") as handle:
            created = True
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if created and temporary.exists():
            temporary.unlink()


def export_bundle(bundle: OfflineBundle, output_dir: Path, *, check: bool = False) -> dict:
    if any(path.is_symlink() for path in (output_dir, *output_dir.parents)):
        raise OfflineSnapshotError("OFFLINE.OUTPUT_SYMLINK_FORBIDDEN")
    manifest = bundle.manifest
    expected_id = "alpha-" + digest({k: v for k, v in manifest.items() if k != "bundleId"}).removeprefix("sha256:")
    if manifest.get("bundleId") != expected_id:
        raise OfflineSnapshotError("OFFLINE.BUNDLE_IDENTITY_DRIFT")
    # 输出前逐项复验所有媒体，任何失败不暴露新 manifest。
    destinations = {}
    for row in manifest["media"]:
        key = row["assetPath"]
        raw = bundle.media_bytes.get(key)
        if raw is None or len(raw) != row["byteLength"] or digest_bytes(raw) != row["sha256"]:
            raise OfflineSnapshotError("OFFLINE.MEDIA_EXPORT_DRIFT")
        path = safe_path(output_dir, "media/" + Path(key).name)
        if path.exists() and path.read_bytes() != raw:
            raise OfflineSnapshotError("OFFLINE.IMMUTABLE_MEDIA_OUTPUT_CONFLICT")
        if check and not path.is_file():
            raise OfflineSnapshotError("OFFLINE.MEDIA_EXPORT_MISSING")
        destinations[path] = raw
    safe_path(output_dir, "manifest.json")
    safe_path(output_dir, "bundle_identity.json")
    if not check:
        for path, raw in destinations.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_file(path, raw)
    # manifest 无 self-digest；此独立结果必须由 build artifact/编译常量固定才形成信任根。
    raw_manifest = canonical_bytes(manifest) + b"\n"
    result = {"schema": "quwoquan.offline_content_bundle_identity", "version": 1,
              "bundleId": manifest["bundleId"], "manifestAssetPath": "assets/content/alpha/manifest.json",
              "manifestDigest": digest_bytes(raw_manifest), "cohortDigest": manifest["cohortDigest"],
              "selectionDigest": manifest["selectionDigest"], "configurationDigest": manifest["configurationDigest"], "counts": manifest["counts"]}
    if check:
        for name, expected in (("bundle_identity.json", canonical_bytes(result) + b"\n"), ("manifest.json", raw_manifest)):
            path = output_dir / name
            if not path.is_file() or path.read_bytes() != expected:
                raise OfflineSnapshotError("OFFLINE.EXPORT_DRIFT")
    else:
        _atomic_file(output_dir / "bundle_identity.json", canonical_bytes(result) + b"\n")
        _atomic_file(output_dir / "manifest.json", raw_manifest)
    return result


def write_dart_identity(result: dict, path: Path, *, check: bool = False) -> None:
    """把独立校验结果固定进制品；运行时不能读取可改写 JSON 自证摘要。"""
    import json
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise OfflineSnapshotError("OFFLINE.IDENTITY_OUTPUT_SYMLINK_FORBIDDEN")
    source = (
        "// Code generated by release export-offline. DO NOT EDIT.\n\n"
        "const String offlineContentManifestAssetPath = "
        + json.dumps(result["manifestAssetPath"]) + ";\n"
        "const String offlineContentManifestDigest = "
        + json.dumps(result["manifestDigest"]) + ";\n"
    ).encode("utf-8")
    if check:
        if not path.is_file() or path.read_bytes() != source:
            raise OfflineSnapshotError("OFFLINE.IDENTITY_OUTPUT_DRIFT")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_file(path, source)
