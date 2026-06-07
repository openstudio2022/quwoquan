"""批次内资产 ID 登记表（仅批内去重，不做全局 registry）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common.asset_identity import asset_token, role_file_token
from _common.io import read_json, write_json
from _common.paths import batch_shared_dir

BATCH_ASSET_REGISTRY_SCHEMA = "quwoquan_data.batch_asset_registry/1"


def batch_asset_registry_path(task_id: str, batch_id: str) -> Path:
    return batch_shared_dir(task_id, batch_id) / "asset_id_registry.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def batch_asset_owner_key(*, global_batch_seq: int | str, entity_name: str, role: str, ref: str) -> str:
    """批内 asset 的稳定 owner key。"""
    return "|".join(
        [
            str(int(global_batch_seq)),
            str(ref or ""),
            asset_token(entity_name),
            role_file_token(role),
        ]
    )


@dataclass
class BatchAssetRegistry:
    """批次内资产 ID 目录。

    `asset_ids` 用于 collision 检测；`entries` 记录 owner_key → assetId，保证同一批次重跑幂等。
    """

    task_id: str
    batch_id: str
    global_batch_seq: int
    path: Path = field(init=False)
    asset_ids: set[str] = field(default_factory=set)
    entries: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path = batch_asset_registry_path(self.task_id, self.batch_id)

    @classmethod
    def load(cls, task_id: str, batch_id: str, global_batch_seq: int) -> "BatchAssetRegistry":
        path = batch_asset_registry_path(task_id, batch_id)
        registry = cls(task_id=task_id, batch_id=batch_id, global_batch_seq=int(global_batch_seq))
        if not path.is_file():
            return registry
        data = read_json(path)
        if isinstance(data, dict):
            if data.get("globalBatchSeq") is not None:
                try:
                    registry.global_batch_seq = int(data["globalBatchSeq"])
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

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            self.path,
            {
                "schemaVersion": BATCH_ASSET_REGISTRY_SCHEMA,
                "taskId": self.task_id,
                "batchId": self.batch_id,
                "globalBatchSeq": int(self.global_batch_seq),
                "assetIds": sorted(self.asset_ids),
                "entries": dict(sorted(self.entries.items())),
                "updatedAt": _now_iso(),
            },
        )
        return self.path

    def as_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": BATCH_ASSET_REGISTRY_SCHEMA,
            "taskId": self.task_id,
            "batchId": self.batch_id,
            "globalBatchSeq": int(self.global_batch_seq),
            "assetIds": sorted(self.asset_ids),
            "entries": dict(sorted(self.entries.items())),
        }


def load_batch_asset_registry(task_id: str, batch_id: str, global_batch_seq: int) -> BatchAssetRegistry:
    return BatchAssetRegistry.load(task_id, batch_id, global_batch_seq)


def allocate_post_asset_id(
    *,
    entity_name: str,
    role: str,
    ref: str,
    global_batch_seq: int,
    registry: BatchAssetRegistry,
    max_nonce: int = 32,
) -> str:
    """在批内登记表中分配唯一 assetId；重复 owner_key 直接复用。"""
    owner_key = batch_asset_owner_key(
        global_batch_seq=global_batch_seq,
        entity_name=entity_name,
        role=role,
        ref=ref,
    )
    existing = registry.resolve(owner_key)
    if existing:
        return existing
    from _common.asset_identity import compute_post_asset_id

    for nonce in range(max_nonce + 1):
        asset_id = compute_post_asset_id(
            entity_name=entity_name,
            role=role,
            global_batch_seq=global_batch_seq,
            ref=ref,
            nonce=nonce,
        )
        if registry.claim(owner_key, asset_id):
            return asset_id
    raise RuntimeError(
        f"asset id allocation exhausted for {entity_name!r}/{role!r} (task={registry.task_id} batch={registry.batch_id})"
    )
