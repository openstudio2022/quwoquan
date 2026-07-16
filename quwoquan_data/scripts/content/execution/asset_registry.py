"""执行内资产 ID 登记表（仅执行内去重，不做全局 registry）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.asset_identity import asset_token, role_file_token
from core.io import read_json, write_json
from core.paths import execution_shared_dir

EXECUTION_ASSET_REGISTRY_SCHEMA = "quwoquan_data.execution_asset_registry/1"


def execution_asset_registry_path(execution_id: str) -> Path:
    return execution_shared_dir(execution_id) / "asset_id_registry.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def execution_asset_owner_key(*, execution_sequence: int | str, entity_name: str, role: str, ref: str) -> str:
    """执行内 asset 的稳定 owner key。"""
    return "|".join(
        [
            str(int(execution_sequence)),
            str(ref or ""),
            asset_token(entity_name),
            role_file_token(role),
        ]
    )


@dataclass
class ExecutionAssetRegistry:
    """执行内资产 ID 目录。

    `asset_ids` 用于 collision 检测；`entries` 记录 owner_key → assetId，保证同一执行重跑幂等。
    """

    execution_id: str
    execution_sequence: int
    path: Path = field(init=False)
    asset_ids: set[str] = field(default_factory=set)
    entries: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path = execution_asset_registry_path(self.execution_id)

    @classmethod
    def load(cls, execution_id: str, execution_sequence: int) -> "ExecutionAssetRegistry":
        path = execution_asset_registry_path(execution_id)
        registry = cls(execution_id=execution_id, execution_sequence=int(execution_sequence))
        if not path.is_file():
            return registry
        data = read_json(path)
        if isinstance(data, dict):
            if data.get("executionSequence") is not None:
                try:
                    registry.execution_sequence = int(data["executionSequence"])
                except (TypeError, ValueError):
                    pass
            asset_ids = data.get("assetIds") or []
            if isinstance(asset_ids, list):
                registry.asset_ids.update(str(a) for a in asset_ids if str(a or "").strip())
            entries = data.get("entries") or {}
            if isinstance(entries, dict):
                for owner_key, asset_id in entries.items():
                    key = str(owner_key or "").strip()
                    aid = str(asset_id or "").strip()
                    if key and aid:
                        registry.entries[key] = aid
                        registry.asset_ids.add(aid)
        return registry

    def resolve(self, owner_key: str) -> str | None:
        key = str(owner_key or "").strip()
        if not key:
            return None
        return self.entries.get(key)

    def claim(self, owner_key: str, asset_id: str) -> bool:
        key = str(owner_key or "").strip()
        aid = str(asset_id or "").strip()
        if not key or not aid:
            return False
        existing = self.entries.get(key)
        if existing:
            return existing == aid
        if aid in self.asset_ids:
            return False
        self.entries[key] = aid
        self.asset_ids.add(aid)
        self.save()
        return True

    def rename_asset_id(self, old_id: str, new_id: str) -> bool:
        """把已登记的 assetId 原位改名（owner_key 不变）。

        成稿阶段 fold_to_simplified 会折叠繁体图注段（见
        build/homepage.py `_fold_homepage_manifest_assets`）；manifest 与
        磁盘文件名折叠后，registry 必须同步改名，否则登记表留下孤儿
        繁体 ID，目录证据链门会判 registry↔manifest 断链。
        """
        old = str(old_id or "").strip()
        new = str(new_id or "").strip()
        if not old or not new or old == new:
            return False
        if old not in self.asset_ids:
            return False
        if new in self.asset_ids:
            raise RuntimeError(
                f"asset id rename collision: {new!r} already registered "
                f"(execution={self.execution_id})"
            )
        changed = False
        for owner_key, asset_id in self.entries.items():
            if asset_id == old:
                self.entries[owner_key] = new
                changed = True
        if not changed:
            return False
        self.asset_ids.discard(old)
        self.asset_ids.add(new)
        self.save()
        return True

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            self.path,
            {
                "schemaVersion": EXECUTION_ASSET_REGISTRY_SCHEMA,
                "executionId": self.execution_id,
                "executionSequence": int(self.execution_sequence),
                "assetIds": sorted(self.asset_ids),
                "entries": dict(sorted(self.entries.items())),
                "updatedAt": _now_iso(),
            },
        )
        return self.path

    def as_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": EXECUTION_ASSET_REGISTRY_SCHEMA,
            "executionId": self.execution_id,
            "executionSequence": int(self.execution_sequence),
            "assetIds": sorted(self.asset_ids),
            "entries": dict(sorted(self.entries.items())),
        }


def load_execution_asset_registry(execution_id: str, execution_sequence: int) -> ExecutionAssetRegistry:
    return ExecutionAssetRegistry.load(execution_id, execution_sequence)


def allocate_post_asset_id(
    *,
    entity_name: str,
    role: str,
    ref: str,
    execution_sequence: int,
    registry: ExecutionAssetRegistry,
    max_nonce: int = 32,
    caption: str = "",
    section_slug: str = "",
    ordinal: int = 0,
) -> str:
    """在执行内登记表中分配唯一 assetId；重复 owner_key 直接复用。

    owner key 不含图注（幂等优先）：同一 owner 重跑即使图注文案调整，
    也复用首次登记的 assetId，保证执行内文件名稳定。
    """
    owner_key = execution_asset_owner_key(
        execution_sequence=execution_sequence,
        entity_name=entity_name,
        role=role,
        ref=ref,
    )
    existing = registry.resolve(owner_key)
    if existing:
        return existing
    from core.asset_identity import compute_post_asset_id

    for nonce in range(max_nonce + 1):
        asset_id = compute_post_asset_id(
            entity_name=entity_name,
            role=role,
            execution_sequence=execution_sequence,
            ref=ref,
            nonce=nonce,
            caption=caption,
            section_slug=section_slug,
            ordinal=ordinal,
        )
        if registry.claim(owner_key, asset_id):
            return asset_id
    raise RuntimeError(
        f"asset id allocation exhausted for {entity_name!r}/{role!r} (execution={registry.execution_id})"
    )
