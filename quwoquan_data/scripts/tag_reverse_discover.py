"""从 post/entity 的 tagRefs 和正文中反向发现标签候选

扫描 publish/v1 中所有 manifest.json 和 _entity.json，
找出引用了但不存在于 tags/ 树中的 tagRef（死引用），以及正文中出现但未打标的高频词。

输出: tag_runtime/candidates.ndjson

用法:
  python3 tag_reverse_discover.py
  python3 tag_reverse_discover.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, RUNTIME_ROOT, NOW_ISO

TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags"
RUNTIME_TAG_DIR = RUNTIME_ROOT / "tag_runtime"
CANDIDATES_FILE = RUNTIME_TAG_DIR / "candidates.ndjson"


def all_existing_tags() -> set[str]:
    tags: set[str] = set()
    for f in TAGS_ROOT.rglob("_definition.json"):
        rel = f.parent.relative_to(TAGS_ROOT)
        tags.add(str(rel))
    return tags


def scan_dead_refs() -> list[dict]:
    """找出 manifest/entity 中引用了但标签树里不存在的 tagRef。"""
    existing = all_existing_tags()
    dead: list[dict] = []
    v1_root = PUBLISH_ROOT / "v1"

    for mf in v1_root.rglob("manifest.json"):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        source = str(mf.relative_to(v1_root))
        for tref in data.get("tagRefs", []):
            if tref not in existing:
                dead.append({"tagRef": tref, "source": source, "reason": "dead_ref"})

    for ef in v1_root.rglob("_entity.json"):
        try:
            data = json.loads(ef.read_text(encoding="utf-8"))
        except Exception:
            continue
        source = str(ef.relative_to(v1_root))
        for tref in data.get("tagRefs", []):
            if tref not in existing:
                dead.append({"tagRef": tref, "source": source, "reason": "dead_ref"})
        geo = data.get("geoTagRef", "")
        if geo and geo not in existing:
            dead.append({"tagRef": geo, "source": source, "reason": "dead_geo_ref"})

    return dead


def scan_content_keywords() -> list[dict]:
    """从 article.md 正文中提取高频中文关键词作为候选。"""
    v1_root = PUBLISH_ROOT / "v1"
    word_counter: Counter[str] = Counter()
    zh_pattern = re.compile(r"[\u4e00-\u9fa5]{2,6}")

    for md in v1_root.rglob("article.md"):
        text = md.read_text(encoding="utf-8")
        words = zh_pattern.findall(text)
        word_counter.update(words)

    existing_labels = set()
    for f in TAGS_ROOT.rglob("_definition.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            existing_labels.add(data.get("label", ""))
            for alias in data.get("aliases", []):
                existing_labels.add(alias)
        except Exception:
            pass

    # 过滤已存在标签和常用虚词
    stopwords = {"但是", "因为", "所以", "如果", "可以", "这个", "那个", "一个",
                 "我们", "他们", "已经", "非常", "什么", "没有", "不是", "就是",
                 "一些", "其中", "或者", "还是", "而且", "以及", "这些", "那些",
                 "自己", "大家", "目前", "通过", "之后", "之前", "同时", "以下",
                 "比较", "进行", "开始", "提供", "包括", "根据", "需要"}

    candidates: list[dict] = []
    for word, count in word_counter.most_common(200):
        if word in existing_labels or word in stopwords:
            continue
        if count >= 3:
            candidates.append({
                "label": word,
                "frequency": count,
                "reason": "content_keyword",
                "suggestedGroup": "Topic",
            })
    return candidates[:50]


def main():
    parser = argparse.ArgumentParser(description="反向发现标签候选")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dead_refs = scan_dead_refs()
    keywords = scan_content_keywords()
    all_candidates = dead_refs + keywords

    if not args.dry_run:
        RUNTIME_TAG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CANDIDATES_FILE, "w", encoding="utf-8") as f:
            for c in all_candidates:
                c["discoveredAt"] = NOW_ISO
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"反向发现完成: {len(dead_refs)} 条死引用, {len(keywords)} 条关键词候选")
    print(f"总计 {len(all_candidates)} 条候选")
    if not args.dry_run:
        print(f"已写入: {CANDIDATES_FILE}")
    else:
        print("[dry-run 模式]")
    for c in all_candidates[:10]:
        print(f"  {c.get('tagRef') or c.get('label')}: {c['reason']}")


if __name__ == "__main__":
    main()
