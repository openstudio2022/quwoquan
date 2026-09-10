"""只读精确 canonical 闭包和两处媒体持有，不回填、不下载、不发布。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

from content.release.canonical.aggregate_release_closure import reference_closure
from content.release.canonical.aggregate_release_pool_closure import selected_pool_entity_refs
from content.release.canonical.offline_snapshot_contract import OfflineSnapshotError, digest_bytes, safe_path
from core.content_library import library_cas_path
from core.media_asset_url import build_public_media_slice_key, content_addressed_media_object_key
from core.paths import LIBRARY_ROOT, carried_media_root
from core.schema import assert_valid


@dataclass
class CanonicalSource:
    root: Path
    files: dict[str, bytes] = field(default_factory=dict)

    def read(self, ref: str) -> bytes:
        raw = safe_path(self.root, ref).read_bytes()
        old = self.files.setdefault(ref, raw)
        if old != raw:
            raise OfflineSnapshotError("OFFLINE.SOURCE_CHANGED_DURING_CAPTURE")
        return raw

    def json(self, ref: str) -> dict:
        value = json.loads(self.read(ref))
        if not isinstance(value, dict):
            raise OfflineSnapshotError("OFFLINE.SOURCE_OBJECT_INVALID")
        return value

    def capture_object(self, ref: str) -> None:
        # 仅遍历显式选择的对象内文件；不反查 Creator 的所有作品或全池。
        root = safe_path(self.root, ref)
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise OfflineSnapshotError("OFFLINE.SYMLINK_FORBIDDEN")
            if path.is_file():
                self.read(path.relative_to(self.root).as_posix())

    def assert_unchanged(self) -> None:
        for ref, raw in self.files.items():
            if safe_path(self.root, ref).read_bytes() != raw:
                raise OfflineSnapshotError("OFFLINE.SOURCE_CHANGED_DURING_CAPTURE")

    def file_facts(self) -> list[dict]:
        return [{"ref": ref, "sha256": digest_bytes(raw), "byteLength": len(raw)} for ref, raw in sorted(self.files.items())]


def capture_closure(source: CanonicalSource, post_refs: list[str]) -> tuple[list[str], list[str], list[str]]:
    for ref in post_refs:
        source.capture_object(ref)
        manifest = source.json(f"{ref}/manifest.json")
        assert_valid(manifest, "content", "post_manifest", label=ref)
        review = source.json(f"{ref}/content_review.json")
        if manifest.get("status") != "active" or review.get("decision") != "approved":
            raise OfflineSnapshotError("OFFLINE.CANONICAL_POST_NOT_ADMITTED")
        evidence = manifest.get("admission", {})
        if digest_bytes(source.read(f"{ref}/content_review.json")) != evidence.get("evidenceDigest"):
            raise OfflineSnapshotError("OFFLINE.REVIEW_DIGEST_DRIFT")
    relative_posts = {ref.removeprefix("posts/") for ref in post_refs}
    entities = selected_pool_entity_refs(source.root, post_refs=relative_posts)
    creators, tags = reference_closure(source.root, entity_refs=entities, post_refs=relative_posts)
    for ref in sorted(entities):
        source.capture_object(f"entities/{ref}")
        if source.json(f"entities/{ref}/manifest.json").get("status") != "active":
            raise OfflineSnapshotError("OFFLINE.CANONICAL_HOMEPAGE_NOT_ACTIVE")
    for ref in creators:
        source.capture_object(f"creators/{ref}")
        if source.json(f"creators/{ref}/profile.json").get("status") != "active":
            raise OfflineSnapshotError("OFFLINE.CANONICAL_CREATOR_NOT_ACTIVE")
    for ref in tags:
        # 标签只复制本层定义，不带入后代标签。
        source.json(f"tags/{ref}/_definition.json")
    return sorted(entities), creators, tags


def _read_media(sha256: str, size: int, suffix: str, *, library: Path, carried: Path) -> bytes:
    # holder 根是操作者选择的仓外存储挂载，可经系统 symlink 指向持有卷。
    # 在边界解析一次后，仅接受该物理根内部普通文件；禁止叶子/分片 symlink。
    library = library.expanduser().resolve()
    carried = carried.expanduser().resolve()
    primary = library_cas_path("media", sha256, library_root=library)
    backup = carried / (sha256.removeprefix("sha256:") + suffix)
    observed = []
    for path in (primary, backup):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise OfflineSnapshotError("OFFLINE.MEDIA_SYMLINK_FORBIDDEN")
        if not path.exists():
            continue
        if not path.is_file():
            raise OfflineSnapshotError("OFFLINE.MEDIA_NOT_REGULAR")
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise OfflineSnapshotError("OFFLINE.MEDIA_CHANGED_DURING_CAPTURE")
        if before.st_size != size or len(raw) != size or digest_bytes(raw) != sha256:
            # 腐坏持有不能通过另一个副本掩盖；缺席才允许独立随体副本。
            raise OfflineSnapshotError("OFFLINE.MEDIA_HASH_OR_SIZE_DRIFT")
        observed.append(raw)
    if not observed:
        raise OfflineSnapshotError("OFFLINE.MEDIA_HOLDING_MISSING")
    return observed[0]


def _rights(source: CanonicalSource, owner: str, asset_id: str, sha256: str) -> tuple[str, dict, list[dict]]:
    rights = source.json(f"{owner}/rights.json") if not owner.startswith("creators/") else {}
    records = [r for r in rights.get("assets", []) if r.get("assetId") == asset_id]
    snapshots = []
    prefix = owner + "/rights_snapshots/"
    for ref in sorted(source.files):
        if ref.startswith(prefix) and ref.endswith(".json"):
            document = source.json(ref)
            if document.get("assetId") == asset_id:
                bound = document.get("manifestAsset", {}).get("sha256")
                if bound and bound != sha256:
                    raise OfflineSnapshotError("OFFLINE.RIGHTS_DIGEST_DRIFT")
                snapshots.append({"ref": ref, "sha256": digest_bytes(source.files[ref]), "document": document})
                if "commercialRights" in document:
                    records.append(document["commercialRights"])
    if not records or not snapshots:
        raise OfflineSnapshotError("OFFLINE.RIGHTS_EVIDENCE_MISSING")
    record = records[0]
    attribution = record.get("attribution")
    if not isinstance(attribution, str) or not attribution.strip():
        raise OfflineSnapshotError("OFFLINE.ATTRIBUTION_MISSING")
    return attribution, record.get("asset", {}), snapshots


def capture_media(source: CanonicalSource, owners: list[str], *, library: Path | None = None, carried: Path | None = None) -> tuple[list[dict], dict[str, bytes]]:
    rows: dict[str, dict] = {}
    bodies: dict[str, bytes] = {}
    for owner in owners:
        creator = owner.startswith("creators/")
        header = source.json(f"{owner}/profile.json" if creator else f"{owner}/manifest.json")
        manifest_assets = {r["assetId"]: r for r in header.get("assets", [])}
        refs = source.json(f"{owner}/assets.refs.json" if creator else f"{owner}/asset.refs.json")
        for ref in refs["assets"]:
            asset_id, sha256, size = ref["assetId"], ref["sha256"], ref["bytes"]
            metadata = manifest_assets.get(asset_id, ref)
            suffix = Path(ref["objectKey"]).suffix
            kind = "avatar" if creator else metadata["kind"]
            mime = metadata["mimeType"]
            if ref["objectKey"] != content_addressed_media_object_key(sha256, suffix=suffix):
                raise OfflineSnapshotError("OFFLINE.CAS_OBJECT_KEY_DRIFT")
            if metadata.get("sha256", sha256) != sha256:
                raise OfflineSnapshotError("OFFLINE.MANIFEST_ASSET_DIGEST_DRIFT")
            attribution, dimensions, snapshots = _rights(source, owner, asset_id, sha256)
            reference = build_public_media_slice_key(asset_id=asset_id, kind=kind, version=1, content_type=mime)
            if not reference:
                raise OfflineSnapshotError("OFFLINE.PUBLIC_SLICE_INVALID")
            asset_path = f"assets/content/alpha/media/{sha256.removeprefix('sha256:')}{suffix}"
            raw = _read_media(sha256, size, suffix, library=library or LIBRARY_ROOT, carried=carried or carried_media_root())
            row = {"assetId": asset_id, "version": 1, "kind": kind, "canonicalReference": reference, "assetPath": asset_path,
                   "sha256": sha256, "byteLength": len(raw), "mimeType": mime, "attribution": attribution,
                   "redistributionEvidence": {"purpose": "alpha_offline_engineering", "ownerRefs": [owner], "snapshots": snapshots}}
            for key in ("width", "height", "durationMs"):
                value = metadata.get(key, dimensions.get(key))
                if value:
                    row[key] = value
            if asset_id in rows:
                old = rows[asset_id]
                if any(old[k] != row[k] for k in ("canonicalReference", "sha256", "byteLength", "mimeType", "kind")):
                    raise OfflineSnapshotError("OFFLINE.MEDIA_IDENTITY_COLLISION")
                old["redistributionEvidence"]["ownerRefs"].append(owner)
                old["redistributionEvidence"]["snapshots"].extend(snapshots)
            else:
                rows[asset_id] = row
            if asset_path in bodies and bodies[asset_path] != raw:
                raise OfflineSnapshotError("OFFLINE.MEDIA_PATH_COLLISION")
            bodies[asset_path] = raw
    return [rows[key] for key in sorted(rows)], bodies
