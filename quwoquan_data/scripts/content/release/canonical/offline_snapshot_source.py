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
    locations: dict[str, str] = field(default_factory=dict)

    def object_path(self, ref: str) -> Path:
        from content.release.canonical.aggregate_release_closure import object_root
        from core.publish_layout import logical_object_ref

        safe_path(self.root, ref)
        if ref not in self.locations:
            kind, logical = ref.split("/", 1)
            from content.release.canonical.object_transaction_contract import ObjectTransactionError
            for candidate in (self.root / kind).rglob("manifest.json"):
                safe_path(self.root, candidate.relative_to(self.root).as_posix())
            try:
                path = object_root(self.root, kind, logical)
            except ObjectTransactionError as exc:
                raise OfflineSnapshotError(str(exc)) from exc
            if kind in {"posts", "entities"}:
                manifest = json.loads(safe_path(self.root, path.relative_to(self.root).as_posix() + "/manifest.json").read_bytes())
                if logical_object_ref(manifest, kind) != logical:
                    raise OfflineSnapshotError("OFFLINE.SOURCE_IDENTITY_DRIFT")
            self.locations[ref] = path.relative_to(self.root).as_posix()
        return safe_path(self.root, self.locations[ref])

    def _path(self, ref: str) -> Path:
        for logical in sorted(self.locations, key=len, reverse=True):
            if ref.startswith(logical + "/"):
                return safe_path(self.root, self.locations[logical] + ref[len(logical):])
        return safe_path(self.root, ref)

    def read(self, ref: str) -> bytes:
        path = self._path(ref)
        raw = path.read_bytes()
        physical_ref = path.relative_to(self.root).as_posix()
        old = self.files.setdefault(physical_ref, raw)
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
        root = self.object_path(ref)
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


def _rights(source: CanonicalSource, owner: str, asset: dict, documents: list[dict]) -> tuple[str, dict, list[dict]]:
    records, snapshots = [], []
    for document in documents:
        if document["ref"] not in asset["sourceRefs"]:
            continue
        matches = [row for row in document["assets"] if row.get("assetId") == asset["assetId"]]
        for row in matches:
            if row.get("sha256") != asset["sha256"] or row.get("bytes") != asset["bytes"]:
                raise OfflineSnapshotError("OFFLINE.RIGHTS_DIGEST_DRIFT")
        if matches:
            ref = f"{owner}/{document['ref']}"
            raw = source.read(ref)
            snapshots.append({"ref": source._path(ref).relative_to(source.root).as_posix(), "sha256": digest_bytes(raw), "document": source.json(ref)})
            records.extend(matches)
    if not records:
        raise OfflineSnapshotError("OFFLINE.RIGHTS_EVIDENCE_MISSING")
    attributions = {row.get("attribution") for row in records}
    if len(attributions) != 1 or not isinstance(next(iter(attributions)), str) or not next(iter(attributions)).strip():
        raise OfflineSnapshotError("OFFLINE.ATTRIBUTION_MISSING_OR_CONFLICTING")
    return next(iter(attributions)), records[0].get("asset", {}), snapshots


def _media_row(source: CanonicalSource, owner: str, metadata: dict, documents: list[dict]) -> tuple[dict, bytes]:
    asset_id, sha256, size = metadata["assetId"], metadata["sha256"], metadata["bytes"]
    relative = metadata["path"]
    if len(Path(relative).parts) != 2 or not relative.startswith("media/"):
        raise OfflineSnapshotError("OFFLINE.MEDIA_PATH_INVALID")
    kind = "avatar" if owner.startswith("creators/") else metadata["kind"]
    mime = metadata["mimeType"]
    attribution, dimensions, snapshots = _rights(source, owner, metadata, documents)
    reference = build_public_media_slice_key(asset_id=asset_id, kind=kind, version=1, content_type=mime)
    if not reference:
        raise OfflineSnapshotError("OFFLINE.PUBLIC_SLICE_INVALID")
    asset_path = f"assets/content/alpha/media/{sha256.removeprefix('sha256:')}{Path(relative).suffix}"
    try:
        raw = source.read(f"{owner}/{relative}")
    except FileNotFoundError as error:
        raise OfflineSnapshotError("OFFLINE.MEDIA_MISSING: " + asset_id) from error
    if len(raw) != size or digest_bytes(raw) != sha256:
        raise OfflineSnapshotError("OFFLINE.MEDIA_HASH_OR_SIZE_DRIFT")
    row = {"assetId": asset_id, "version": 1, "kind": kind, "canonicalReference": reference, "assetPath": asset_path,
           "sha256": sha256, "byteLength": len(raw), "mimeType": mime, "attribution": attribution,
           "redistributionEvidence": {"purpose": "alpha_offline_engineering", "ownerRefs": [owner], "snapshots": snapshots}}
    for key in ("width", "height", "durationMs"):
        value = metadata.get(key, dimensions.get(key))
        if value:
            row[key] = value
    return row, raw


def _source_media(source: CanonicalSource, owner: str) -> tuple[list[dict], list[dict]]:
    from content.release.canonical.post_transaction_sources import read_object_sources
    creator = owner.startswith("creators/")
    header = source.json(f"{owner}/profile.json" if creator else f"{owner}/manifest.json")
    assets = header["assets"]
    if creator:
        avatar = header["avatarAsset"]
        if len(assets) != 1 or any(assets[0].get(key) != avatar.get(key) for key in ("assetId", "kind", "sha256")):
            raise OfflineSnapshotError("OFFLINE.CREATOR_AVATAR_BINDING_DRIFT")
    return assets, read_object_sources(source.object_path(owner), header)


def capture_media(source: CanonicalSource, owners: list[str], *, library: Path | None = None, carried: Path | None = None) -> tuple[list[dict], dict[str, bytes]]:
    rows: dict[str, dict] = {}
    bodies: dict[str, bytes] = {}
    for owner in owners:
        assets, documents = _source_media(source, owner)
        for metadata in assets:
            row, raw = _media_row(source, owner, metadata, documents)
            asset_id, asset_path = row["assetId"], row["assetPath"]
            if asset_id in rows:
                old = rows[asset_id]
                if any(old[k] != row[k] for k in ("canonicalReference", "sha256", "byteLength", "mimeType", "kind")):
                    raise OfflineSnapshotError("OFFLINE.MEDIA_IDENTITY_COLLISION")
                old["redistributionEvidence"]["ownerRefs"].append(owner)
                old["redistributionEvidence"]["snapshots"].extend(row["redistributionEvidence"]["snapshots"])
            else:
                rows[asset_id] = row
            if asset_path in bodies and bodies[asset_path] != raw:
                raise OfflineSnapshotError("OFFLINE.MEDIA_PATH_COLLISION")
            bodies[asset_path] = raw
    return [rows[key] for key in sorted(rows)], bodies
