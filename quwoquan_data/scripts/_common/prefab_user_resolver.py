"""Dual-track prefab user resolver (creator_pool + legacy)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

PrefabTrack = Literal["creator_pool", "archive", "all"]

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "test_fixtures"
PROVENANCE_PATH = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "prefab_user_provenance.yaml"


@dataclass(frozen=True)
class PrefabUserRecord:
    user_id: str
    sub_account_id: str | None
    prefab_track: PrefabTrack
    slot_role: str | None = None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _provenance() -> dict[str, Any]:
    if not PROVENANCE_PATH.is_file():
        return {}
    data = yaml.safe_load(PROVENANCE_PATH.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _creator_pool_path() -> Path:
    track = ((_provenance().get("tracks") or {}).get("creator_pool") or {})
    rel = str(track.get("fixturePath") or "_shared/test_fixtures/user_pool.creator_pool.travel_photo_1k_v1.json")
    return REPO_ROOT / "quwoquan_service/contracts/metadata" / rel


def _creator_manifest_path() -> Path:
    track = ((_provenance().get("tracks") or {}).get("creator_pool") or {})
    rel = str(track.get("manifestPath") or "_shared/test_fixtures/user_pool.manifest.travel_photo_1k_v1.json")
    return REPO_ROOT / "quwoquan_service/contracts/metadata" / rel


@lru_cache(maxsize=1)
def _creator_index() -> dict[str, PrefabUserRecord]:
    path = _creator_pool_path()
    if not path.is_file():
        return {}
    payload = _load_json(path)
    index: dict[str, PrefabUserRecord] = {}
    for user in payload.get("users") or []:
        if not isinstance(user, dict):
            continue
        record = PrefabUserRecord(
            user_id=str(user.get("userId") or ""),
            sub_account_id=str(user.get("subAccountId") or user.get("subAccountRefs", [None])[0] or "") or None,
            prefab_track="creator_pool",
            slot_role=user.get("slotRole"),
        )
        if record.user_id:
            index[record.user_id] = record
        if record.sub_account_id:
            index[record.sub_account_id] = record
    return index


@lru_cache(maxsize=1)
def _legacy_aliases() -> dict[str, str]:
    return {}


def resolve_user_id(user_id: str, *, track: PrefabTrack = "all") -> str:
    """Resolve user id: creator track first, then legacy alias, then passthrough."""
    normalized = user_id.strip()
    if not normalized:
        return normalized
    aliases = _legacy_aliases()
    if normalized in aliases:
        normalized = aliases[normalized]
    creator = _creator_index()
    if track in ("all", "creator_pool") and normalized in creator:
        return creator[normalized].user_id
    if track == "creator_pool":
        return normalized
    return normalized


def resolve_sub_account_id(sub_account_id: str) -> str:
    creator = _creator_index()
    aliases = _legacy_aliases()
    normalized = aliases.get(sub_account_id, sub_account_id)
    if normalized in creator and creator[normalized].sub_account_id:
        return creator[normalized].sub_account_id  # type: ignore[return-value]
    if sub_account_id in creator and creator[sub_account_id].sub_account_id:
        return creator[sub_account_id].sub_account_id  # type: ignore[return-value]
    return sub_account_id


def current_user_variant_sub_account_id() -> str:
    manifest_path = _creator_manifest_path()
    if manifest_path.is_file():
        slot = _load_json(manifest_path).get("currentUserVariant") or {}
        sub = str(slot.get("subAccountId") or "")
        if sub:
            return sub
    creator = _creator_index()
    for record in creator.values():
        if record.slot_role == "currentUserVariant" and record.sub_account_id:
            return record.sub_account_id
    return "fixture_sub_current"


def list_users(*, track: PrefabTrack = "all") -> list[PrefabUserRecord]:
    creator = list({r.user_id: r for r in _creator_index().values() if r.user_id}.values())
    if track == "creator_pool":
        return creator
    if track == "archive":
        legacy_path = FIXTURES_DIR / "user_pool.json"
        if not legacy_path.is_file():
            return []
        users = _load_json(legacy_path).get("users") or []
        return [
            PrefabUserRecord(
                user_id=str(u.get("userId") or ""),
                sub_account_id=(u.get("subAccountRefs") or [None])[0],
                prefab_track="archive",
            )
            for u in users
            if isinstance(u, dict) and u.get("userId")
        ]
    return creator


def clear_cache() -> None:
    _provenance.cache_clear()
    _creator_index.cache_clear()
    _legacy_aliases.cache_clear()
