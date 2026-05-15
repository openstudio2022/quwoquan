"""将标签候选去重/归并后写入正式标签树

读取 tag_runtime/candidates.ndjson，
过滤已存在/重复/低频候选，将通过审核的候选写入 publish/v1/tags。

输出:
  - 新增的 _definition.json 文件
  - tag_runtime/merge_log.ndjson（合入记录）

用法:
  python3 tag_candidate_merge.py
  python3 tag_candidate_merge.py --dry-run
  python3 tag_candidate_merge.py --min-freq 5    # 关键词最低频率
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, RUNTIME_ROOT, NOW_ISO

TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags"
RUNTIME_TAG_DIR = RUNTIME_ROOT / "tag_runtime"
CANDIDATES_FILE = RUNTIME_TAG_DIR / "candidates.ndjson"
MERGE_LOG = RUNTIME_TAG_DIR / "merge_log.ndjson"


def all_existing_tags() -> set[str]:
    tags: set[str] = set()
    for f in TAGS_ROOT.rglob("_definition.json"):
        rel = str(f.parent.relative_to(TAGS_ROOT))
        tags.add(rel)
    return tags


def all_existing_labels() -> set[str]:
    labels: set[str] = set()
    for f in TAGS_ROOT.rglob("_definition.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            labels.add(data.get("label", ""))
        except Exception:
            pass
    return labels


def merge_tag(tag_ref: str, label: str, label_en: str, desc: str) -> bool:
    p = TAGS_ROOT / tag_ref / "_definition.json"
    if p.exists():
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "label": label,
        "labelEn": label_en,
        "description": desc,
        "sourceRefs": ["auto:reverse_discover"],
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description="候选标签归并")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-freq", type=int, default=3)
    args = parser.parse_args()

    if not CANDIDATES_FILE.exists():
        print(f"无候选文件: {CANDIDATES_FILE}")
        sys.exit(0)

    candidates = []
    with open(CANDIDATES_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                candidates.append(json.loads(line))

    existing_tags = all_existing_tags()
    existing_labels = all_existing_labels()
    merged = 0
    skipped = 0
    log_entries: list[dict] = []

    for c in candidates:
        reason = c.get("reason", "")

        if reason == "dead_ref":
            tag_ref = c["tagRef"]
            if tag_ref in existing_tags:
                skipped += 1
                continue
            label = tag_ref.rsplit("/", 1)[-1]
            if not args.dry_run:
                ok = merge_tag(tag_ref, label, label, f"由死引用自动发现: {c.get('source', '')}")
                if ok:
                    merged += 1
                    log_entries.append({"action": "merge", "tagRef": tag_ref, "mergedAt": NOW_ISO})
                else:
                    skipped += 1
            else:
                merged += 1

        elif reason == "content_keyword":
            if c.get("frequency", 0) < args.min_freq:
                skipped += 1
                continue
            label = c["label"]
            if label in existing_labels:
                skipped += 1
                continue
            group = c.get("suggestedGroup", "Topic")
            tag_ref = f"{group}/主题/{label}"
            if not args.dry_run:
                ok = merge_tag(tag_ref, label, label, f"由正文高频词发现 (频率{c['frequency']})")
                if ok:
                    merged += 1
                    log_entries.append({"action": "merge", "tagRef": tag_ref, "mergedAt": NOW_ISO})
                else:
                    skipped += 1
            else:
                merged += 1

    if not args.dry_run and log_entries:
        RUNTIME_TAG_DIR.mkdir(parents=True, exist_ok=True)
        with open(MERGE_LOG, "a", encoding="utf-8") as f:
            for entry in log_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"候选归并完成: {merged} 合入, {skipped} 跳过")
    if args.dry_run:
        print("[dry-run 模式]")


if __name__ == "__main__":
    main()
