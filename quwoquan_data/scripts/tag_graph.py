"""基于 tagRef 共现度生成隐式关系图谱

扫描 publish/v1 中所有 entity 和 post 的 tagRefs，统计标签共现关系。
生成三类产物：
  1. cooccur/tag_to_tag.ndjson     - 标签-标签共现
  2. cooccur/entity_to_entity.ndjson - 实体-实体共现（共享标签）
  3. inverted_index/tag_objects.ndjson - 标签→对象反向索引

输出: publish/v1/relations/

用法:
  python3 tag_graph.py
  python3 tag_graph.py --min-cooccur 2   # 最低共现次数
  python3 tag_graph.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, NOW_ISO

V1_ROOT = PUBLISH_ROOT / "v1"
REL_ROOT = V1_ROOT / "relations"


def collect_tag_sets() -> tuple[list[dict], list[dict]]:
    """收集所有 entity 和 post 的 tagRefs。"""
    entities: list[dict] = []
    posts: list[dict] = []

    for ef in V1_ROOT.rglob("_entity.json"):
        try:
            data = json.loads(ef.read_text(encoding="utf-8"))
        except Exception:
            continue
        tags = data.get("tagRefs", [])
        geo = data.get("geoTagRef", "")
        if geo:
            tags = tags + [geo]
        rel = str(ef.parent.relative_to(V1_ROOT))
        entities.append({"id": rel, "type": "entity", "tags": tags})

    for mf in V1_ROOT.rglob("manifest.json"):
        if "entities" in str(mf):
            continue
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        tags = data.get("tagRefs", [])
        rel = str(mf.parent.relative_to(V1_ROOT))
        posts.append({"id": rel, "type": "post", "tags": tags})

    return entities, posts


def compute_tag_cooccurrence(
    objects: list[dict], min_cooccur: int
) -> list[dict]:
    """统计标签对共现次数。"""
    pair_counter: Counter[tuple[str, str]] = Counter()
    for obj in objects:
        tags = sorted(set(obj["tags"]))
        for a, b in combinations(tags, 2):
            pair_counter[(a, b)] += 1

    results: list[dict] = []
    for (a, b), count in pair_counter.most_common():
        if count < min_cooccur:
            break
        results.append({"tagA": a, "tagB": b, "cooccurCount": count})
    return results


def compute_entity_cooccurrence(
    entities: list[dict], min_shared: int = 2
) -> list[dict]:
    """两个实体共享标签数 >= min_shared 则建立边。"""
    results: list[dict] = []
    for i, e1 in enumerate(entities):
        for e2 in entities[i + 1:]:
            shared = set(e1["tags"]) & set(e2["tags"])
            if len(shared) >= min_shared:
                results.append({
                    "entityA": e1["id"],
                    "entityB": e2["id"],
                    "sharedTags": sorted(shared),
                    "sharedCount": len(shared),
                })
    return results


def build_inverted_index(objects: list[dict]) -> list[dict]:
    """标签→引用该标签的对象列表。"""
    idx: dict[str, list[str]] = defaultdict(list)
    for obj in objects:
        for tag in set(obj["tags"]):
            idx[tag].append(obj["id"])

    results: list[dict] = []
    for tag in sorted(idx):
        results.append({
            "tag": tag,
            "objectCount": len(idx[tag]),
            "objects": idx[tag][:50],
        })
    return results


def write_ndjson(path: Path, records: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="标签共现关系图谱生成")
    parser.add_argument("--min-cooccur", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    entities, posts = collect_tag_sets()
    all_objects = entities + posts

    print(f"数据源: {len(entities)} 实体, {len(posts)} 篇 post")

    tag_cooccur = compute_tag_cooccurrence(all_objects, args.min_cooccur)
    entity_cooccur = compute_entity_cooccurrence(entities)
    inverted = build_inverted_index(all_objects)

    print(f"标签共现: {len(tag_cooccur)} 对")
    print(f"实体共现: {len(entity_cooccur)} 对")
    print(f"反向索引: {len(inverted)} 个标签")

    if not args.dry_run:
        write_ndjson(REL_ROOT / "cooccur" / "tag_to_tag.ndjson", tag_cooccur)
        write_ndjson(REL_ROOT / "cooccur" / "entity_to_entity.ndjson", entity_cooccur)
        write_ndjson(REL_ROOT / "inverted_index" / "tag_objects.ndjson", inverted)
        print(f"\n已写入: {REL_ROOT}/")
    else:
        print("[dry-run 模式]")

    if tag_cooccur:
        print("\n标签共现 TOP 10:")
        for r in tag_cooccur[:10]:
            print(f"  {r['tagA']} ↔ {r['tagB']}: {r['cooccurCount']}")


if __name__ == "__main__":
    main()
