# Code generated from contracts/metadata/_shared/types.yaml. DO NOT EDIT.
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType

COMPILED_CONTENT_PRESENTATION_COLLECTIONS = MappingProxyType({
    "contentTypes": ("article","image","video"),
    "listObjectKinds": ("entity_homepage","post"),
    "openSurfaces": ("article_reader","home_feed","homepage_detail","media_immersive","profile_works"),
    "presentationRecipes": ("article_excerpt_card","cover_media_card","homepage_summary_card"),
})
COMPILED_CONTENT_PRESENTATION_CONTRACT_DIGEST = "sha256:8ef3b67169b934c19c9ac825b73085c4aa0cdb809ef82429b4b1e1e2d0bfca05"

MISSING_DECLARATION_CONTENT_PRESENTATION_COLLECTIONS = MappingProxyType({
    "contentTypes": ("article","image","video"),
    "listObjectKinds": ("post",),
    "openSurfaces": ("article_reader","media_immersive"),
    "presentationRecipes": ("article_excerpt_card","cover_media_card"),
})
MISSING_DECLARATION_CONTENT_PRESENTATION_CONTRACT_DIGEST = "sha256:cf070afb148dc07d723c9eb76ec9e87fafcffcd16c07ad6a22f367d393de9281"

_MAX_ITEMS = {
    "contentTypes": 32,
    "listObjectKinds": 32,
    "openSurfaces": 32,
    "presentationRecipes": 32,
}

def canonical_client_content_presentation_contract(value: Mapping[str, object]) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("client presentation contract must be an object")
    fields = set(COMPILED_CONTENT_PRESENTATION_COLLECTIONS)
    if set(value) not in (fields, fields | {"contractDigest"}):
        raise ValueError("expected exactly the four capability collections")
    normalized = {}
    for field, allowed in COMPILED_CONTENT_PRESENTATION_COLLECTIONS.items():
        values = value[field]
        if not isinstance(values, list) or len(values) > _MAX_ITEMS[field]:
            raise ValueError(f"{field}: expected bounded non-null array")
        seen = set()
        for member in values:
            if not isinstance(member, str) or member not in allowed or member in seen:
                raise ValueError(f"{field}: invalid or duplicate capability member")
            seen.add(member)
        normalized[field] = sorted(values, key=lambda member: member.encode("utf-8"))
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_client_content_presentation_contract(value: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(canonical_client_content_presentation_contract(value)).hexdigest()


def validate_client_content_presentation_contract(value: Mapping[str, object]) -> dict[str, object]:
    # 仅核验完整性；授权仍须逐维检查实际集合，不能只比较摘要。
    expected = digest_client_content_presentation_contract(value)
    if value.get("contractDigest") != expected:
        raise ValueError("client presentation contract digest mismatch")
    normalized = json.loads(canonical_client_content_presentation_contract(value))
    return {**normalized, "contractDigest": expected}


def compiled_content_presentation_contract() -> dict[str, object]:
    return {**{key: list(values) for key, values in COMPILED_CONTENT_PRESENTATION_COLLECTIONS.items()},
            "contractDigest": COMPILED_CONTENT_PRESENTATION_CONTRACT_DIGEST}


def missing_declaration_content_presentation_contract() -> dict[str, object]:
    return {**{key: list(values) for key, values in MISSING_DECLARATION_CONTENT_PRESENTATION_COLLECTIONS.items()},
            "contractDigest": MISSING_DECLARATION_CONTENT_PRESENTATION_CONTRACT_DIGEST}


def decode_client_content_presentation_contract(raw: bytes | None) -> dict[str, object]:
    # None 或无字节表示整个声明缺席；JSON null、空对象和非法声明不能降级。
    if raw is None or raw == b"":
        return missing_declaration_content_presentation_contract()
    def unique_object(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate capability field")
            out[key] = value
        return out
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    return validate_client_content_presentation_contract(value)
