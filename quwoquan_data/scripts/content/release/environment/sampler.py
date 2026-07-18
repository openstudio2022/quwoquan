"""按环境内容采样器（确定性、可重跑、可审计）。

输入：自治 publish object packages + content_sampling_manifest.yaml。
输出：immutable release overlay 的 sample_bundle.json；不读写 canonical 派生索引。

确定性：rank = sha1(salt|ref) 映射到 [0,1)；rank < sampleRatio 入选；再按 bucket cap
与 max 截断（按 rank 升序保留，保证稳定）。prod ratio=1.0 即全量。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import yaml

from core.io import write_json
from core.paths import PUBLISH_ROOT, RELEASE_ROOT, REPO_ROOT

# content_sampling_manifest.yaml 是受版本控制的跨工程部署契约，必须挂 code-anchored 的
# REPO_ROOT；禁止用 DATA_ROOT.parent 推导（隔离根/沙箱下会漂移到 $HOME/deploy 而丢失契约）。
SAMPLING_MANIFEST = REPO_ROOT / "quwoquan_ops" / "environments" / "content_sampling_manifest.yaml"


def load_sampling_manifest(path: Path | None = None) -> dict[str, Any]:
    p = path or SAMPLING_MANIFEST
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def rank01(salt: str, ref: str) -> float:
    digest = hashlib.sha1(f"{salt}|{ref}".encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) / 0xFFFFFFFF


def sample_records(
    records: Sequence[Mapping[str, Any]],
    *,
    salt: str,
    ratio: float,
    cap_per_bucket: int,
    max_total: int,
    ref_key: str,
    bucket_key: Callable[[Mapping[str, Any]], str],
) -> list[str]:
    """确定性采样，返回选中的 ref 列表（稳定排序）。"""
    scored: list[tuple[float, str, str]] = []
    seen: set[str] = set()
    for rec in records:
        ref = str(rec.get(ref_key) or "")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        r = rank01(salt, ref)
        if r < ratio:
            scored.append((r, bucket_key(rec), ref))
    scored.sort(key=lambda x: (x[1], x[0], x[2]))

    bucket_counts: dict[str, int] = {}
    selected: list[str] = []
    for r, bucket, ref in scored:
        if cap_per_bucket and bucket_counts.get(bucket, 0) >= cap_per_bucket:
            continue
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        selected.append(ref)
    selected.sort()
    if max_total and len(selected) > max_total:
        # 按 rank 全局截断（保持确定性）
        ranked = sorted(selected, key=lambda ref: rank01(salt, ref))[:max_total]
        selected = sorted(ranked)
    return selected


def _scan_objects(root: Path, kind: str, anchor: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    base = root / kind
    if not base.is_dir():
        return records
    for path in sorted(base.rglob(anchor)):
        doc = json.loads(path.read_text(encoding="utf-8"))
        rel = path.parent.relative_to(base).as_posix()
        if kind == "posts":
            doc["postRef"] = f"posts/{rel}"
        else:
            doc["entityRef"] = rel
            doc.setdefault("etype", doc.get("type"))
        records.append(doc)
    return records


def load_publish_records(publish_root: Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = publish_root or PUBLISH_ROOT
    posts = _scan_objects(root, "posts", "manifest.json")
    entities = _scan_objects(root, "entities", "_entity.json")
    return posts, entities


def _post_bucket(rec: Mapping[str, Any]) -> str:
    return f"{rec.get('contentType', 'article')}__{rec.get('angle', 'unknown')}"


def _entity_bucket(rec: Mapping[str, Any]) -> str:
    return f"{rec.get('domain', '')}__{rec.get('etype', '')}"


def _normalize_entity_ref(raw_ref: Any) -> str:
    raw = str(raw_ref or "").strip()
    if not raw:
        return ""
    parts = [part for part in raw.strip("/").split("/") if part]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    if len(parts) >= 3:
        return "/".join(parts[:3])
    return "/".join(parts)


def _post_entity_refs(post: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("entityRef", "normalizedEntityRef"):
        value = post.get(key)
        if value:
            refs.append(str(value))
    for key in ("entityRefs", "normalizedEntityRefs"):
        for value in post.get(key) or []:
            if value:
                refs.append(str(value))
    return refs


def build_sample_bundle(
    env: str,
    manifest: Mapping[str, Any],
    posts: Sequence[Mapping[str, Any]],
    entities: Sequence[Mapping[str, Any]],
    *,
    forced_post_refs: Sequence[str] | None = None,
    forced_entity_refs: Sequence[str] | None = None,
    isolate_forced_sample: bool = False,
) -> dict[str, Any]:
    envs = manifest.get("environments") or {}
    if env not in envs:
        raise KeyError(f"environment '{env}' not in content_sampling_manifest")
    # defaults 提供环境缺省（比例 10% / 上限 1000）；env 显式键覆盖。
    defaults = manifest.get("defaults") or {}
    cfg = {**defaults, **(envs[env] or {})}
    salt = str(manifest.get("salt") or "")
    ratio = float(cfg.get("sampleRatio", 1.0))

    post_refs = sample_records(
        posts,
        salt=salt,
        ratio=ratio,
        cap_per_bucket=int(cfg.get("postCapPerBucket", 0)),
        max_total=int(cfg.get("maxPosts", 0)),
        ref_key="postRef",
        bucket_key=_post_bucket,
    )
    entity_refs = sample_records(
        entities,
        salt=salt,
        ratio=ratio,
        cap_per_bucket=int(cfg.get("entityCapPerBucket", 0)),
        max_total=int(cfg.get("maxEntities", 0)),
        ref_key="entityRef",
        bucket_key=_entity_bucket,
    )
    known_posts = {str(p.get("postRef")) for p in posts if p.get("postRef")}
    known_entity_by_ref = {
        _normalize_entity_ref(e.get("entityRef")): str(e.get("entityRef")).strip()
        for e in entities
        if _normalize_entity_ref(e.get("entityRef"))
    }
    known_entities = set(known_entity_by_ref.values())
    forced_posts = sorted(
        {
            str(ref).strip()
            for ref in (forced_post_refs or [])
            if str(ref).strip() and str(ref).strip() in known_posts
        }
    )
    forced_entities = sorted(
        {
            known_entity_by_ref.get(_normalize_entity_ref(ref), _normalize_entity_ref(ref))
            for ref in (forced_entity_refs or [])
            if _normalize_entity_ref(ref) in known_entity_by_ref
        }
    )
    # 受控发布可显式把当前批次对象纳入环境样本。默认仍保留环境采样；
    # isolate_forced_sample 用于百/千级试跑，避免历史 publish 主线污染样本。
    if isolate_forced_sample:
        post_refs = forced_posts
        entity_refs = forced_entities
    else:
        post_refs = sorted(set(post_refs) | set(forced_posts))
        entity_refs = sorted(set(entity_refs) | set(forced_entities))

    # 引用闭包：post 一旦进入环境，所引用且已发布的 entity 必须同批进入。
    # 否则内容详情、实体主页和推荐条件画像会在目标环境产生悬挂引用。
    selected_posts = {str(ref) for ref in post_refs}
    required_entities: set[str] = set()
    for post in posts:
        if str(post.get("postRef") or "") not in selected_posts:
            continue
        for entity_ref in _post_entity_refs(post):
            ref = _normalize_entity_ref(entity_ref)
            if ref in known_entity_by_ref:
                required_entities.add(known_entity_by_ref[ref])
    entity_refs = sorted(set(entity_refs) | required_entities)
    return {
        "schema": "quwoquan.content_sample_bundle",
        "environment": env,
        "sampleRatio": ratio,
        "salt": salt,
        "posts": post_refs,
        "entities": entity_refs,
        "forcedPosts": forced_posts,
        "forcedEntities": forced_entities,
        "isolatedForcedSample": bool(isolate_forced_sample),
        "counts": {
            "posts": len(post_refs),
            "entities": len(entity_refs),
            "postsTotal": len({str(p.get("postRef")) for p in posts if p.get("postRef")}),
            "entitiesTotal": len({str(e.get("entityRef")) for e in entities if e.get("entityRef")}),
        },
    }


def write_sample_bundle(
    bundle: Mapping[str, Any],
    *,
    release_id: str,
    release_root: Path | None = None,
) -> Path:
    root = (release_root or RELEASE_ROOT) / release_id
    from core.release_layout import payload_file

    out = payload_file(root, "sample_bundle.json")
    payload = {
        "schema": "quwoquan_data.release_sample",
        "releaseId": release_id,
        "posts": sorted({str(ref) for ref in bundle.get("posts") or []}),
        "entities": sorted({str(ref) for ref in bundle.get("entities") or []}),
        "samplingAttestation": {
            "algorithm": "sha1-salted-deterministic",
            "saltSha256": hashlib.sha256(str(bundle.get("salt") or "").encode("utf-8")).hexdigest(),
        },
    }
    if out.exists():
        existing = json.loads(out.read_text(encoding="utf-8"))
        if existing != payload:
            raise FileExistsError(f"release create-once conflict: {out}")
        return out
    write_json(out, payload)
    return out
