"""发布物理位置的纯函数；逻辑身份、内容版本与目录编号各自独立。"""
from __future__ import annotations

import json
import re
import unicodedata
from fractions import Fraction
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


class PublishLayoutError(ValueError):
    """不可通过补默认身份或猜测地域修复的布局错误。"""


@dataclass(frozen=True)
class LayoutPolicy:
    max_entries: int
    max_bytes: int
    video_max_bytes: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in (self.max_entries, self.max_bytes, self.video_max_bytes)):
            raise PublishLayoutError("DATA.LAYOUT.POLICY_INVALID")


@dataclass(frozen=True)
class ObjectPlacement:
    path: str
    object_id: str
    version: int
    logical_ref: str
    logical_bytes: int


_PARTITION = re.compile(r"p[0-9]{4,}$")
_GEO_PREFIX = "Topic/地理/行政区/"


def load_layout_policy() -> LayoutPolicy:
    from core.paths import REPO_DATA_ROOT
    from core.schema import assert_valid

    raw = json.loads((REPO_DATA_ROOT / "control_plane/_shared/publish_layout.policy.json").read_bytes())
    assert_valid(raw, "publish", "layout_policy")
    return LayoutPolicy(raw["maxEntries"], raw["maxBytes"], raw["videoMaxBytes"])


def path_component(value: object) -> str:
    if not isinstance(value, str):
        raise PublishLayoutError("DATA.LAYOUT.NAME_INVALID: expected string")
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise PublishLayoutError("DATA.LAYOUT.NAME_INVALID: control character")
    normalized = " ".join(unicodedata.normalize("NFC", value).split())
    if (not normalized or normalized in {".", ".."} or any(char in normalized for char in "/\\")
            or normalized.startswith(".") or normalized.endswith(".") or len(normalized.encode("utf-8")) > 240):
        raise PublishLayoutError("DATA.LAYOUT.NAME_INVALID: unsafe or oversized component")
    return normalized


def _safe_ref(value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise PublishLayoutError("DATA.LAYOUT.REF_INVALID")
    parts = value.split("/")
    if any(part in {"", ".", ".."} or any(unicodedata.category(c).startswith("C") for c in part) for part in parts):
        raise PublishLayoutError("DATA.LAYOUT.REF_INVALID")
    return value


def entity_namespace(manifest: Mapping[str, Any]) -> PurePosixPath:
    domain = path_component(manifest.get("domain"))
    entity_type = _safe_ref(manifest.get("type"))
    types = [path_component(part) for part in entity_type.split("/")]
    mode = manifest.get("geographyMode")
    base = PurePosixPath("entities", domain)
    if mode == "none":
        if manifest.get("geoTagRef") or manifest.get("geoTagRefs"):
            raise PublishLayoutError("DATA.LAYOUT.GEOGRAPHY_CONFLICT")
        return base.joinpath(*types)
    if mode != "administrative":
        raise PublishLayoutError("DATA.LAYOUT.GEOGRAPHY_REQUIRED")
    geo = manifest.get("geoTagRef")
    if not isinstance(geo, str) or not geo.startswith(_GEO_PREFIX):
        raise PublishLayoutError("DATA.LAYOUT.GEOGRAPHY_REQUIRED")
    region = _safe_ref(geo[len(_GEO_PREFIX):])
    if manifest.get("geoTagRefs") and geo not in manifest["geoTagRefs"]:
        raise PublishLayoutError("DATA.LAYOUT.GEOGRAPHY_CONFLICT")
    return base.joinpath(*(path_component(part) for part in region.split("/")), *types)


def post_namespace(manifest: Mapping[str, Any]) -> PurePosixPath:
    carrier = manifest.get("contentType")
    if carrier not in {"article", "image", "video"}:
        raise PublishLayoutError("DATA.LAYOUT.CARRIER_INVALID")
    return PurePosixPath("posts", carrier, path_component(manifest.get("publishAngle")))


def logical_object_ref(manifest: Mapping[str, Any], kind: str) -> str:
    if kind == "entities":
        value = manifest.get("entityRef")
        if not isinstance(value, str) or not value.startswith("/entity/"):
            raise PublishLayoutError("DATA.LAYOUT.IDENTITY_REQUIRED: entityRef")
        return _safe_ref(value.removeprefix("/entity/"))
    if kind == "posts":
        return _safe_ref(manifest.get("objectRef"))
    if kind == "creators":
        return _safe_ref(manifest.get("creatorProfileId") or manifest.get("creatorId") or manifest.get("authorId"))
    raise PublishLayoutError("DATA.LAYOUT.KIND_INVALID")


def _coordinates(path: str, namespace: PurePosixPath) -> tuple[str, str, int] | None:
    parsed = PurePosixPath(_safe_ref(path))
    if parsed.parent.parent.parent != namespace:
        return None
    partition, name, sequence = parsed.parts[-3:]
    if (not _PARTITION.fullmatch(partition) or int(partition[1:]) < 1
            or partition != f"p{int(partition[1:]):04d}"
            or not re.fullmatch(r"[1-9][0-9]*", sequence)):
        raise PublishLayoutError("DATA.LAYOUT.COORDINATES_INVALID")
    return partition, name, int(sequence)


def _partition_loads(
    existing: Sequence[ObjectPlacement], namespace: PurePosixPath, name: str,
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    loads: dict[str, list[int]] = {}
    group: dict[str, list[int]] = {}
    seen_paths: set[str] = set()
    for row in existing:
        if row.path in seen_paths or type(row.logical_bytes) is not int or row.logical_bytes < 0:
            raise PublishLayoutError("DATA.LAYOUT.INVENTORY_INVALID")
        seen_paths.add(row.path)
        coords = _coordinates(row.path, namespace)
        if coords is None:
            continue
        partition, peer_name, sequence = coords
        normalized_peer = path_component(peer_name)
        if normalized_peer.casefold() == name.casefold() and normalized_peer != name:
            raise PublishLayoutError("DATA.LAYOUT.NAME_COLLISION")
        count = loads.setdefault(partition, [0, 0])
        count[0] += 1
        count[1] += row.logical_bytes
        if normalized_peer == name:
            group.setdefault(partition, []).append(sequence)
    if len(group) > 1:
        raise PublishLayoutError("DATA.LAYOUT.GROUP_SPLIT")
    return loads, group


def allocate_object_path(
    manifest: Mapping[str, Any], kind: str, existing: Sequence[ObjectPlacement],
    policy: LayoutPolicy, *, logical_bytes: int = 0,
) -> str:
    """调用方持有发布锁；只分配位置，不创建文件、不决定后继动作。"""
    identity = manifest.get("entityId" if kind == "entities" else "contentId")
    version = manifest.get("version")
    if not isinstance(identity, str) or not identity or type(version) is not int or version < 1:
        raise PublishLayoutError("DATA.LAYOUT.IDENTITY_REQUIRED")
    if type(logical_bytes) is not int or logical_bytes < 0:
        raise PublishLayoutError("DATA.LAYOUT.BYTES_INVALID")
    logical_ref = logical_object_ref(manifest, kind)
    namespace = entity_namespace(manifest) if kind == "entities" else post_namespace(manifest)
    name = path_component(manifest.get("label") if kind == "entities" else manifest.get("publishTitle"))
    if any(row.logical_ref == logical_ref and row.object_id != identity for row in existing):
        raise PublishLayoutError("DATA.LAYOUT.IDENTITY_CONFLICT: logical ref already belongs to another object")
    peers = [row for row in existing if row.object_id == identity and row.version == version]
    if peers:
        if len(peers) != 1 or peers[0].logical_ref != logical_ref:
            raise PublishLayoutError("DATA.LAYOUT.IDENTITY_CONFLICT")
        return _safe_ref(peers[0].path)
    loads, group = _partition_loads(existing, namespace, name)
    if group:
        partition, sequences = next(iter(group.items()))
        return (namespace / partition / name / str(max(sequences) + 1)).as_posix()
    max_bytes = policy.video_max_bytes if manifest.get("contentType") == "video" else policy.max_bytes
    fits = [part for part, (count, size) in loads.items() if count + 1 <= policy.max_entries and size + logical_bytes <= max_bytes]
    if fits:
        partition = min(fits, key=lambda part: (max(Fraction(loads[part][0] + 1, policy.max_entries), Fraction(loads[part][1] + logical_bytes, max_bytes)), int(part[1:])))
    else:
        partition = f"p{max((int(part[1:]) for part in loads), default=0) + 1:04d}"
    return (namespace / partition / name / "1").as_posix()
