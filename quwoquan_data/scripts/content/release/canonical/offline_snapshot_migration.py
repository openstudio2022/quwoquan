"""一次性旧 canonical → 独立当前 schema 输入；不接入普通读取，不发布、不重审。

原池和 execution 只读。只有原 receipt/review/record/source 闭包核验通过才构造
私有 staging；原件保留在 original/，新对象只保留 manifest、sources、media、review、records。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import shutil
import tempfile

from content.release.canonical.offline_snapshot_contract import (
    OfflineSnapshotError, canonical_bytes, digest, digest_bytes, safe_path, validate_selection,
)
from content.release.canonical.offline_snapshot_source import _read_media
from content.release.canonical.pool_cutover import _absolute, _regular_tree, _separate
from content.release.canonical.pool_cutover_inventory import _inspect_content, _sources, convert_creator_profile
from content.release.canonical.pool_cutover_text_conversion import _manifest
from content.release.canonical.post_transaction_assets import canonical_post_asset_row
from content.release.canonical.post_asset_identity import project_canonical_post_asset_paths
from content.release.canonical.post_transaction_sources import project_object_sources, read_object_sources
from core.publish_layout import allocate_object_path, load_layout_policy
from core.schema import assert_valid


def _json(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise OfflineSnapshotError("OFFLINE.MIGRATION_OBJECT_INVALID")
    return value


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)


def _write_json(path: Path, value: dict) -> None:
    _write(path, canonical_bytes(value) + b"\n")


def _facts(files: dict[str, bytes]) -> list[dict]:
    return [{"ref": ref, "sha256": digest_bytes(raw), "byteLength": len(raw)} for ref, raw in sorted(files.items())]


def _capture(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in _regular_tree(root)}


def _closure(root: Path, post_refs: list[str]) -> tuple[list[str], list[str], list[str]]:
    """旧 ref 仅在显式 migration 入口解读；不调用现役逻辑位置 resolver。"""
    entities, creators, tags = set(), set(), set()
    for ref in post_refs:
        manifest = _json(safe_path(root, ref + "/manifest.json"))
        for entity in manifest["entityRefs"]:
            if not entity.startswith("/entity/"):
                raise OfflineSnapshotError("OFFLINE.MIGRATION_ENTITY_REF_INVALID")
            entities.add("entities/" + entity.removeprefix("/entity/"))
    for ref in [*post_refs, *sorted(entities)]:
        directory = safe_path(root, ref)
        manifest = _json(directory / "manifest.json")
        binding = _json(directory / "_entity.json") if ref.startswith("entities/") else manifest
        creators.add("creators/" + binding["creatorProfileId"])
        tags.update(binding["tagRefs"])
    for ref in sorted(creators):
        tags.update(_json(safe_path(root, ref + "/_creator.json"))["tagRefs"])
    return sorted(entities), sorted(creators), sorted(tags)


def _reviewed_surface(execution: Path, ref: str, manifest: dict, assets: dict) -> None:
    if manifest["contentType"] not in {"image", "video"}:
        return
    from content.release.canonical.final_surface_projection import _author_intent, _selected_asset_refs, _source_rows
    from content.release.canonical.post_transaction_assets import source_binding_refs
    carrier = manifest["contentType"]
    intent = _author_intent(object_dir=execution / ref, carrier=carrier, target={},
                            source_rows=_source_rows(execution, execution / ref), asset_index=assets)
    draft = intent["draft"]
    # 明确发布的文字/作者/标签必须来自原 reviewed JSON；不采用 default creator 分支。
    for key in ("title", "caption", "creatorProfileId", "tagRefs"):
        if key not in draft or (sorted(draft[key]) != sorted(manifest[key]) if key == "tagRefs" else draft[key] != manifest[key]):
            raise OfflineSnapshotError("OFFLINE.MIGRATION_REVIEWED_SURFACE_DRIFT: " + key)
    selected = _selected_asset_refs(carrier, intent, draft, execution_root=execution)
    frozen = [source for row in manifest["assets"] for source in source_binding_refs(row)]
    if selected != frozen:
        raise OfflineSnapshotError("OFFLINE.MIGRATION_REVIEWED_MEDIA_DRIFT")


def _convert_media(root: Path, target: Path, manifest: dict, source_assets: dict, *, library: Path, carried: Path) -> list[dict]:
    """只搬运已绑定的媒体字节，保留来源与 acquisition 身份。"""
    refs = _json(root / "asset.refs.json")["assets"]
    if len({row["assetId"] for row in refs}) != len(refs) or {row["assetId"] for row in refs} != {row["assetId"] for row in manifest["assets"]}:
        raise OfflineSnapshotError("OFFLINE.MIGRATION_ASSET_CLOSURE_DRIFT")
    by_id = {row["assetId"]: row for row in refs}
    assets, destinations = [], {}
    for index, original_asset in enumerate(manifest["assets"], 1):
        binding = by_id[original_asset["assetId"]]
        for key in ("sha256", "objectKey", "bytes"):
            if key in original_asset and original_asset[key] != binding[key]:
                raise OfflineSnapshotError("OFFLINE.MIGRATION_ASSET_BINDING_DRIFT")
        suffix = Path(binding["objectKey"]).suffix
        relative = f"media/{index:02d}{suffix}"
        body = _read_media(binding["sha256"], binding["bytes"], suffix, library=library, carried=carried)
        _write(target / relative, body)
        asset = canonical_post_asset_row(
            {**original_asset, "sourceAssetRefs": binding["sourceAssetRefs"]}, asset_source=target / relative,
            mime_type=original_asset["mimeType"], object_key=binding["objectKey"], source_assets_by_ref=source_assets,
        )
        if asset["acquisitionReceiptRefs"] != binding["acquisitionReceiptRefs"]:
            raise OfflineSnapshotError("OFFLINE.MIGRATION_ACQUISITION_DRIFT")
        assets.append(asset)
        destinations[asset["assetId"]] = relative
    return project_canonical_post_asset_paths(assets, destination_paths=destinations)


def _convert_content(root: Path, execution: Path, ref: str, target: Path, *, library: Path, carried: Path) -> dict:
    original = _json(root / "manifest.json")
    _inspect_content(root, execution, ref, original, {})
    entity = _json(root / "_entity.json") if ref.startswith("entities/") else None
    manifest = _manifest(original, entity)
    if entity is not None:
        # 主行政区已由原 entity 明确冻结；不补行政层级或新地域事实。
        manifest = {**entity, **manifest, "geographyMode": "administrative"}
        if not entity.get("geoTagRef", "").startswith("Topic/地理/行政区/"):
            raise OfflineSnapshotError("OFFLINE.MIGRATION_GEOGRAPHY_FACT_MISSING")
    else:
        manifest["objectRef"] = ref.removeprefix("posts/")
    _, source_assets = _sources(execution, ref, {})
    _reviewed_surface(execution, ref, original, source_assets)
    rights = _json(root / "rights.json")["assets"]
    manifest["assets"] = _convert_media(root, target, manifest, source_assets, library=library, carried=carried)
    manifest["sourceRefs"] = project_object_sources(
        execution_root=execution, source_object=execution / ref, object_root=target,
        manifest=manifest, source_assets=source_assets, canonical_assets=manifest["assets"], rights_rows=rights,
    )
    for key in ("sourceCatalogRef", "rightsRef"):
        manifest.pop(key, None)
    final_ref = "page.md" if entity is not None else "article.md" if manifest["contentType"] == "article" else "manifest.json"
    manifest["finalContentRef"] = final_ref
    if final_ref != "manifest.json":
        _write(target / final_ref, safe_path(root, final_ref).read_bytes())
    _write(target / "content_review.json", (root / "content_review.json").read_bytes())
    assert_valid(manifest, "publish" if entity is not None else "content", "entity" if entity is not None else "post_manifest")
    _write_json(target / "manifest.json", manifest)
    read_object_sources(target, manifest)
    # 原 records 不重签，放在 original/；唯一新 record 只转录原状态和新物理包摘要。
    from content.release.canonical.content_pool_record import pool_payload_digest
    records = [_json(path) for path in (root / "_pool/versions").glob("*.json")]
    record = copy.deepcopy(max(records, key=lambda value: value["recordSequence"]))
    record.update(recordSequence=1, contentVersion=manifest["version"], payloadDigest=pool_payload_digest(target),
                  canonicalObjectDigest=pool_payload_digest(target))
    assert_valid(record, "release", "pool_object_record")
    _write_json(target / "records/1.json", record)
    return manifest


def _convert_creator(root: Path, target: Path, authority: Path, *, library: Path, carried: Path) -> dict:
    original = _json(root / "profile.json")
    profile = convert_creator_profile(original, authority)
    assets = _json(root / "assets.refs.json")["assets"]
    if len(assets) != 1 or any(original["avatarAsset"][key] != assets[0][key] for key in ("assetId", "sha256", "kind")):
        raise OfflineSnapshotError("OFFLINE.MIGRATION_AVATAR_BINDING_DRIFT")
    asset = assets[0]
    snapshots = [path for path in (root / "rights_snapshots").glob("*.json") if _json(path).get("assetId") == asset["assetId"]]
    if len(snapshots) != 1:
        raise OfflineSnapshotError("OFFLINE.MIGRATION_AVATAR_EVIDENCE_INVALID")
    snapshot = _json(snapshots[0])
    rights = snapshot["commercialRights"]
    if any(rights["asset"][key] != asset[key] for key in ("sha256", "bytes", "mimeType")):
        raise OfflineSnapshotError("OFFLINE.MIGRATION_AVATAR_EVIDENCE_DRIFT")
    suffix = Path(asset["objectKey"]).suffix
    relative = "media/avatar" + suffix
    _write(target / relative, _read_media(asset["sha256"], asset["bytes"], suffix, library=library, carried=carried))
    source_ref = "sources/avatar/source.json"
    raw = snapshots[0].read_bytes()
    source = {"schema": "quwoquan_data.publish_source", "sourceId": "avatar", "sourceUrl": rights["canonicalFilePage"],
              "sourceUseMode": rights["sourceUseMode"], "fetchedAt": rights["fetchedAt"], "metadata": snapshot,
              "assets": [{**rights, "assetId": asset["assetId"], "sha256": asset["sha256"], "bytes": asset["bytes"]}],
              "evidence": [{"path": "evidence.json", "sha256": digest_bytes(raw), "bytes": len(raw), "kind": "acquisition_receipt"}]}
    assert_valid(source, "publish", "source")
    _write_json(target / source_ref, source)
    _write(target / "sources/avatar/evidence.json", raw)
    profile["avatarAsset"] = {key: asset[key] for key in ("assetId", "kind", "sha256")}
    profile["assets"] = [{key: value for key, value in asset.items() if key != "objectKey"} | {"path": relative, "sourceRefs": [source_ref]}]
    profile["sourceRefs"] = [source_ref]
    _write_json(target / "profile.json", profile)
    _write(target / "_creator.json", (root / "_creator.json").read_bytes())
    read_object_sources(target, profile)
    return profile


def _preserve_originals(root: Path, executions: Path, stage: Path, authority: Path, original_files: dict[str, bytes], inspections: dict) -> None:
    """保存原审核闭包的 exact bytes；不重签、不修补缺失证据。"""
    for ref, raw in original_files.items():
        _write(safe_path(stage / "original/publish", ref), raw)
    _write(stage / "original/author_admission.json", authority.read_bytes())
    for ref, inspection in inspections.items():
        manifest = _json(root / ref / "manifest.json")
        execution = safe_path(executions, manifest["executionId"])
        evidence = inspection["originalReviewAuthority"]
        for binding in [*inspection["sourceEvidence"], evidence["review"], evidence["draft"], *evidence["receipts"]]:
            path = Path(binding["ref"])
            raw = path.read_bytes()
            if digest_bytes(raw) != binding["digest"]:
                raise OfflineSnapshotError("OFFLINE.MIGRATION_EVIDENCE_DRIFT")
            target = stage / "original/executions" / execution.name / path.relative_to(execution)
            if not target.exists():
                _write(target, raw)
    for ref, raw in original_files.items():
        if safe_path(root, ref).read_bytes() != raw:
            raise OfflineSnapshotError("OFFLINE.SOURCE_CHANGED_DURING_CAPTURE")


def migrate_source(*, publish_root: Path, executions_root: Path, author_authority: Path, output_dir: Path,
                   selection: dict, source_revision: str, library_root: Path, carried_root: Path) -> dict:
    validate_selection(selection)
    if re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
        raise OfflineSnapshotError("OFFLINE.SOURCE_REVISION_INVALID")
    root = _absolute(publish_root, kind="tree")
    executions = _absolute(executions_root, kind="tree")
    authority = _absolute(author_authority, kind="file")
    output = output_dir.absolute()
    safe_path(output.parent, output.name)
    from core.paths import PUBLISH_ROOT
    for protected in (root, executions, authority, PUBLISH_ROOT.resolve(), library_root.resolve(), carried_root.resolve()):
        _separate(output, protected)
    if output.exists():
        raise OfflineSnapshotError("OFFLINE.MIGRATION_OUTPUT_EXISTS")
    entities, creators, tags = _closure(root, selection["objectRefs"])
    content = [*selection["objectRefs"], *entities]
    original_files, inspections = {}, {}
    for ref in [*content, *creators]:
        original_files.update({ref + "/" + name: raw for name, raw in _capture(safe_path(root, ref)).items()})
    for ref in tags:
        name = f"tags/{ref}/_definition.json"
        original_files[name] = safe_path(root, name).read_bytes()
    # 所有原链先行；任一事实缺失时还未创建输出父目录或私有 staging。
    for ref in content:
        manifest = _json(root / ref / "manifest.json")
        execution = safe_path(executions, manifest["executionId"])
        inspections[ref] = _inspect_content(root / ref, execution, ref, manifest, {})
    for ref in creators:
        convert_creator_profile(_json(root / ref / "profile.json"), authority)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".offline-source-", dir=output.parent))
    try:
        rows = []
        for ref in content:
            original = _json(root / ref / "manifest.json")
            temporary = stage / "converting"
            manifest = _convert_content(root / ref, safe_path(executions, original["executionId"]), ref, temporary,
                                        library=library_root, carried=carried_root)
            destination = allocate_object_path(manifest, ref.split("/")[0], [], load_layout_policy())
            target = safe_path(stage, destination)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary.rename(target)
            rows.append(_object_fact(ref, destination, original_files[ref + "/manifest.json"], target / "manifest.json"))
        for ref in creators:
            _convert_creator(root / ref, safe_path(stage, ref), authority, library=library_root, carried=carried_root)
            rows.append(_object_fact(ref, ref, original_files[ref + "/profile.json"], stage / ref / "profile.json"))
        for ref in tags:
            name = f"tags/{ref}/_definition.json"
            _write(safe_path(stage, name), original_files[name])
        _preserve_originals(root, executions, stage, authority, original_files, inspections)
        report = {"schema": "quwoquan.offline_source_migration", "version": 1, "purpose": "alpha_offline_engineering",
                  "sourceRevision": source_revision, "selectionDigest": digest(selection), "objects": rows,
                  "originalFiles": _facts(original_files), "convertedFiles": _facts(_capture(stage))}
        assert_valid(report, "release", "offline_source_migration")
        _write_json(stage / "offline_source_migration.json", report)
        # rename 只创建独立新输入；不初始化 Git、不激活、不替换旧 canonical。
        if output.exists():
            raise OfflineSnapshotError("OFFLINE.MIGRATION_OUTPUT_EXISTS")
        stage.rename(output)
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _object_fact(original_ref: str, converted_ref: str, original_raw: bytes, path: Path) -> dict:
    return {"originalRef": original_ref, "convertedRef": converted_ref,
            "originalManifestDigest": digest_bytes(original_raw), "convertedManifestDigest": digest_bytes(path.read_bytes()),
            "originalVersion": json.loads(original_raw)["version"], "convertedVersion": _json(path)["version"]}


def handle_migrate_offline_source(args) -> None:
    import subprocess
    from core.paths import REPO_ROOT, LIBRARY_ROOT, carried_media_root
    try:
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
        if args.source_revision != actual:
            raise OfflineSnapshotError("OFFLINE.SOURCE_REVISION_NOT_CURRENT")
        selection_path = Path(args.selection_file).expanduser().absolute()
        safe_path(selection_path.parent, selection_path.name)
        result = migrate_source(publish_root=Path(args.publish_root).expanduser().absolute(),
                                executions_root=Path(args.executions_root).expanduser().absolute(),
                                author_authority=Path(args.author_authority).expanduser().absolute(),
                                output_dir=Path(args.output_dir).expanduser().absolute(), selection=_json(selection_path),
                                source_revision=args.source_revision, library_root=Path(args.library_root or LIBRARY_ROOT).expanduser(),
                                carried_root=Path(args.carried_root).expanduser() if args.carried_root else carried_media_root())
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        raise SystemExit(f"[release migrate-offline-source] GATE_BLOCK {exc}") from exc
    print(json.dumps({key: value for key, value in result.items() if key not in {"originalFiles", "convertedFiles"}}, ensure_ascii=False, sort_keys=True))
