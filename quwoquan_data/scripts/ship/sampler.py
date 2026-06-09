"""按环境内容采样器（确定性、可重跑、可审计）。

输入：publish/ 主线索引（posts/entities ndjson）+ content_sampling_manifest.yaml。
输出：sample bundle（桥契约）—— 选中的 postRef / entityRef 列表 + 计数，写到
publish/sample_bundles/{env}.json，供服务侧 importer 消费灌入运行库。

确定性：rank = sha1(salt|ref) 映射到 [0,1)；rank < sampleRatio 入选；再按 bucket cap
与 max 截断（按 rank 升序保留，保证稳定）。prod ratio=1.0 即全量。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import yaml

from _common.io import write_json
from _common.paths import DATA_ROOT, PUBLISH_ROOT

SAMPLING_MANIFEST = DATA_ROOT.parent / "deploy" / "shared" / "content_sampling_manifest.yaml"
SAMPLE_BUNDLE_DIR = PUBLISH_ROOT / "sample_bundles"


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


def _read_ndjson_dir(d: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.ndjson")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_publish_records(publish_root: Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = publish_root or PUBLISH_ROOT
    posts = _read_ndjson_dir(root / "index" / "posts")
    entities = _read_ndjson_dir(root / "index" / "entities")
    return posts, entities


def _post_bucket(rec: Mapping[str, Any]) -> str:
    return f"{rec.get('contentType', 'article')}__{rec.get('angle', 'unknown')}"


def _entity_bucket(rec: Mapping[str, Any]) -> str:
    return f"{rec.get('domain', '')}__{rec.get('etype', '')}"


def build_sample_bundle(
    env: str,
    manifest: Mapping[str, Any],
    posts: Sequence[Mapping[str, Any]],
    entities: Sequence[Mapping[str, Any]],
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
    # 引用闭包：post 一旦进入环境，所引用且已发布的 entity 必须同批进入。
    # 否则内容详情、实体主页和推荐条件画像会在目标环境产生悬挂引用。
    known_entities = {str(e.get("entityRef")) for e in entities if e.get("entityRef")}
    selected_posts = {str(ref) for ref in post_refs}
    required_entities: set[str] = set()
    for post in posts:
        if str(post.get("postRef") or "") not in selected_posts:
            continue
        for entity_ref in post.get("entityRefs") or []:
            ref = str(entity_ref)
            if ref in known_entities:
                required_entities.add(ref)
    entity_refs = sorted(set(entity_refs) | required_entities)
    return {
        "schemaVersion": "quwoquan.content_sample_bundle",
        "environment": env,
        "sampleRatio": ratio,
        "salt": salt,
        "posts": post_refs,
        "entities": entity_refs,
        "counts": {
            "posts": len(post_refs),
            "entities": len(entity_refs),
            "postsTotal": len({str(p.get("postRef")) for p in posts if p.get("postRef")}),
            "entitiesTotal": len({str(e.get("entityRef")) for e in entities if e.get("entityRef")}),
        },
    }


def write_sample_bundle(bundle: Mapping[str, Any], publish_root: Path | None = None) -> Path:
    root = publish_root or PUBLISH_ROOT
    out = root / "sample_bundles" / f"{bundle['environment']}.json"
    write_json(out, dict(bundle))
    return out
