"""环境数据发布契约。

release contract 是 sample bundle 之后、真实环境 apply 之前的审计边界：
它把本次目标状态、写入模式、删除策略、对象 hash 与引用闭包固定下来，
供 dry-run、importer、consistency scanner 和发布审批共同消费。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.io import write_json
from _common.paths import NOW_ISO, PUBLISH_ROOT

DEFAULT_SOURCE_OWNER = "qwq_data"
DEFAULT_MODE = "upsert"
DEFAULT_DELETE_POLICY = "none"


def normalize_release_id(value: str | None, *, env: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raw = f"data_{env}_{NOW_ISO}"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")
    return safe or f"data_{env}"


def stable_hash(payload: Mapping[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _index_by_ref(records: Sequence[Mapping[str, Any]], ref_key: str) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for rec in records:
        ref = str(rec.get(ref_key) or "").strip()
        if ref:
            out[ref] = rec
    return out


def build_release_contract(
    *,
    env: str,
    bundle: Mapping[str, Any],
    posts: Sequence[Mapping[str, Any]],
    entities: Sequence[Mapping[str, Any]],
    release_id: str | None = None,
    mode: str = DEFAULT_MODE,
    delete_policy: str = DEFAULT_DELETE_POLICY,
    source_owner: str = DEFAULT_SOURCE_OWNER,
    approved_by: str | None = None,
    media_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rid = normalize_release_id(release_id, env=env)
    if env == "prod" and delete_policy == "hard-delete" and not approved_by:
        raise ValueError("prod hard-delete requires approved_by")

    post_idx = _index_by_ref(posts, "postRef")
    entity_idx = _index_by_ref(entities, "entityRef")
    selected_posts = [ref for ref in bundle.get("posts", []) if ref in post_idx]
    selected_entities = [ref for ref in bundle.get("entities", []) if ref in entity_idx]

    actions: list[dict[str, Any]] = []
    for ref in selected_entities:
        rec = entity_idx[ref]
        actions.append({
            "kind": "entity",
            "ref": ref,
            "action": "upsert",
            "sourceHash": stable_hash(rec),
        })
    for ref in selected_posts:
        rec = post_idx[ref]
        actions.append({
            "kind": "post",
            "ref": ref,
            "action": "upsert",
            "sourceHash": stable_hash(rec),
            "entityRefs": list(rec.get("entityRefs") or []),
            "tagRefs": list(rec.get("tagRefs") or []),
            "authorId": rec.get("authorId") or rec.get("subAccountId") or "",
        })

    contract = {
        "schemaVersion": "quwoquan.data_env_release.v1",
        "releaseId": rid,
        "environment": env,
        "mode": mode,
        "deletePolicy": delete_policy,
        "sourceOwner": source_owner,
        "generatedAt": NOW_ISO,
        "approvedBy": approved_by or "",
        "sampleBundle": {
            "schemaVersion": bundle.get("schemaVersion"),
            "environment": bundle.get("environment"),
            "sampleRatio": bundle.get("sampleRatio"),
            "salt": bundle.get("salt"),
            "counts": dict(bundle.get("counts") or {}),
        },
        "desiredRefs": {
            "posts": selected_posts,
            "entities": selected_entities,
        },
        "actions": actions,
        "tombstones": [],
        "counts": {
            "posts": len(selected_posts),
            "entities": len(selected_entities),
            "actions": len(actions),
            "tombstones": 0,
        },
    }
    if media_manifest is not None:
        contract["mediaManifest"] = {
            "schemaVersion": media_manifest.get("schemaVersion"),
            "path": media_manifest.get("path"),
            "assetCount": (media_manifest.get("counts") or {}).get("assets", 0),
            "issueCount": (media_manifest.get("counts") or {}).get("issues", 0),
        }
    return contract


def write_release_contract(contract: Mapping[str, Any], publish_root: Path | None = None) -> Path:
    root = publish_root or PUBLISH_ROOT
    out = root / "env_releases" / str(contract["releaseId"]) / f"{contract['environment']}.json"
    write_json(out, dict(contract))
    return out
