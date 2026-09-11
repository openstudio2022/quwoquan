"""离线派生信封与现役公共投影校验；不维护第二套业务字段表。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from core.schema import assert_valid, validate_strict

POST_CONTRACT = "quwoquan_service/services/content-service/contracts/content/post"
SHARED_TYPES = "quwoquan_service/contracts/metadata/_shared/types.yaml"


class OfflineSnapshotError(ValueError):
    """下游离线派生失败，不签发 producer 或环境资格。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def safe_path(root: Path, ref: str) -> Path:
    parts = PurePosixPath(ref).parts
    if not parts or ref.startswith("/") or "\\" in ref or any(p in (".", "..") for p in parts):
        raise OfflineSnapshotError("OFFLINE.INPUT_PATH_INVALID")
    if ref != PurePosixPath(ref).as_posix():
        raise OfflineSnapshotError("OFFLINE.INPUT_PATH_INVALID")
    path = root.joinpath(*parts)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise OfflineSnapshotError("OFFLINE.SYMLINK_FORBIDDEN")
    return path


def validate_selection(selection: dict) -> None:
    assert_valid(selection, "release", "offline_operator_selection")
    selected = set(selection["objectRefs"])
    channels = selection["channels"]
    ids = [row["channelId"] for row in channels]
    if len(ids) != len(set(ids)) or set(ids) != {"recommend", "premium"}:
        raise OfflineSnapshotError("OFFLINE.CHANNEL_SELECTION_INVALID")
    for row in channels:
        if not set(row["orderedObjectRefs"]) <= selected:
            raise OfflineSnapshotError("OFFLINE.CHANNEL_OUTSIDE_COHORT")
        if row["channelId"] == "premium" and any(not ref.startswith("posts/video/") for ref in row["orderedObjectRefs"]):
            raise OfflineSnapshotError("OFFLINE.PREMIUM_ENGINEERING_VIDEO_REQUIRED")


class PublicContractValidator:
    """从 service authoring source 即时派生校验规则，不生成/修改 ContractGraph。"""

    def __init__(self, repo: Path):
        self.repo = repo
        self.files: dict[str, bytes] = {}
        fields = self.load(f"{POST_CONTRACT}/fields.yaml")
        shared = self.load(SHARED_TYPES)
        self.types = {**shared.get("types", {}), **fields.get("value_objects", {}), **fields.get("types", {})}
        self.enums = {**shared.get("enums", {}), **fields.get("enums", {})}
        user = self.load("quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml")
        self.types["PersonaProfileView"] = user["types"]["PersonaProfileView"]
        self.entity_contract = "quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/projections"

    def validate_homepage(self, value: dict) -> None:
        self._validate(value, self.schema_for_type("HomepageIntroduction"), "HomepageIntroduction")

    def load(self, ref: str) -> dict:
        raw = safe_path(self.repo, ref).read_bytes()
        self.files[ref] = raw
        value = yaml.safe_load(raw)
        if not isinstance(value, dict):
            raise OfflineSnapshotError("OFFLINE.CONTRACT_INVALID")
        return value

    def schema_for_fields(self, fields: list[dict], *, projection: bool = False) -> dict:
        properties, required = {}, []
        for field in fields:
            name = field.get("client_wire_name", field["name"])
            nullable = field.get("nullable", False) if projection else "NULLABLE" in field.get("constraints", [])
            schema = self.schema_for_type(field["type"], field.get("enum_ref"))
            properties[name] = {"anyOf": [schema, {"type": "null"}]} if nullable else schema
            if not nullable:
                required.append(name)
        return {"type": "object", "additionalProperties": False, "properties": properties, "required": required}

    def schema_for_type(self, name: str, enum_ref: str | None = None) -> dict:
        if name.startswith("[]"):
            return {"type": "array", "items": self.schema_for_type(name[2:], enum_ref)}
        primitives = {"string": "string", "timestamp": "string", "int": "integer", "int64": "integer", "bool": "boolean", "float64": "number", "decimal": "number", "object": "object", "json": "object"}
        if name in primitives:
            return {"type": primitives[name]}
        if name == "enum":
            enum = self.enums.get(enum_ref)
            if enum is None:
                raise OfflineSnapshotError(f"OFFLINE.CONTRACT_ENUM_UNRESOLVED: {enum_ref}")
            values = enum.get("values", []) if isinstance(enum, dict) else enum
            return {"enum": [v["value"] if isinstance(v, dict) else v for v in values]}
        declared = self.types.get(name)
        if declared is None and name.startswith("Homepage"):
            import re
            filename = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
            declared = self.load(f"{self.entity_contract}/{filename}.yaml")
            return self.schema_for_fields(declared["fields"], projection=True)
        if not isinstance(declared, dict) or "fields" not in declared:
            raise OfflineSnapshotError(f"OFFLINE.CONTRACT_TYPE_UNRESOLVED: {name}")
        return self.schema_for_fields(declared["fields"])

    def validate_projection(self, value: dict, filename: str) -> None:
        declared = self.load(f"{POST_CONTRACT}/projections/{filename}.yaml")
        # 只为在场字段和必填字段展开类型，未使用的大型其他聚合不进入离线闭包。
        fields = [f for f in declared["fields"] if f["name"] in value or not f.get("nullable", False)]
        self._validate(value, self.schema_for_fields(fields, projection=True), filename)

    def validate_type(self, value: dict, name: str) -> None:
        self._validate(value, self.schema_for_type(name), name)

    @staticmethod
    def _validate(value: dict, schema: dict, label: str) -> None:
        errors = validate_strict(value, schema)
        if errors:
            raise OfflineSnapshotError(f"OFFLINE.PUBLIC_PROJECTION_INVALID: {label}: " + "; ".join(errors[:5]))


def validate_bundle(bundle: dict, validator: PublicContractValidator) -> None:
    assert_valid(bundle, "release", "offline_content_bundle")
    for row in bundle["posts"]:
        validator.validate_projection(row["projection"], "content_post_projection")
        validator.validate_projection(row["detail"], "content_post_detail_slice")
    validator.validate_type(bundle["configuration"]["content"], "ContentAppConfig")
    for creator in bundle["creators"]:
        validator.validate_type(creator["projection"], "PersonaProfileView")
    for homepage in bundle["homepages"]:
        validator.validate_homepage(homepage["projection"])
    ids = [p["projection"]["postId"] for p in bundle["posts"]]
    if len(ids) != len(set(ids)):
        raise OfflineSnapshotError("OFFLINE.DUPLICATE_POST_ID")
    for row in bundle["channels"]:
        if not set(row["orderedPostIds"]) <= set(ids) or row["selectionDigest"] != bundle["selectionDigest"]:
            raise OfflineSnapshotError("OFFLINE.CHANNEL_BINDING_INVALID")
    media = bundle["media"]
    for key in ("assetId", "canonicalReference"):
        if len({m[key] for m in media}) != len(media):
            raise OfflineSnapshotError("OFFLINE.DUPLICATE_MEDIA_ID")
    if digest(bundle["provenance"]["operatorSelection"]) != bundle["selectionDigest"]:
        raise OfflineSnapshotError("OFFLINE.SELECTION_DIGEST_INVALID")
    if digest(bundle["configuration"]) != bundle["configurationDigest"]:
        raise OfflineSnapshotError("OFFLINE.CONFIGURATION_DIGEST_INVALID")
    selection = bundle["provenance"]["operatorSelection"]
    validate_selection(selection)
    expected_cohort = digest({"objectRefs": selection["objectRefs"], "sourceFiles": bundle["provenance"]["sourceFiles"]})
    if expected_cohort != bundle["cohortDigest"]:
        raise OfflineSnapshotError("OFFLINE.COHORT_DIGEST_INVALID")
    if [row["sourceObjectRef"] for row in bundle["posts"]] != selection["objectRefs"]:
        raise OfflineSnapshotError("OFFLINE.POST_SELECTION_DRIFT")
    media_by_id = {m["assetId"]: m for m in media}
    for row in bundle["posts"]:
        if row["projection"]["postId"] != row["detail"]["postId"]:
            raise OfflineSnapshotError("OFFLINE.POST_DETAIL_IDENTITY_DRIFT")
        for view in (row["projection"], row["detail"]):
            avatar = media_by_id.get(view.get("authorAvatarAssetId"))
            if avatar is None or view.get("authorAvatarUrl") != avatar["canonicalReference"] or view.get("authorAvatarAccessMode") != "public":
                raise OfflineSnapshotError("OFFLINE.AVATAR_BINDING_INVALID")
            for item in view.get("mediaItems", []):
                bound = media_by_id.get(item.get("mediaAssetId"))
                if bound is None or item["url"] != bound["canonicalReference"] or item.get("accessMode") != "public":
                    raise OfflineSnapshotError("OFFLINE.MEDIA_BINDING_INVALID")
                if item.get("coverAssetId"):
                    cover = media_by_id.get(item["coverAssetId"])
                    if cover is None or item.get("coverUrl") != cover["canonicalReference"]:
                        raise OfflineSnapshotError("OFFLINE.POSTER_BINDING_INVALID")
