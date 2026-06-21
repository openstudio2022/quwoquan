#!/usr/bin/env python3
"""标签真相源门禁（V0.5 B0：标签真相源收口）。

唯一标签真相源 = 数据工程路径制 taxonomy（quwoquan_data/publish/tags，
四分组 Topic/Audience/Format/Entity，tagRef = 目录路径）。已废弃云侧扁平
tag_taxonomy.yaml（topic_*/circle_*/interest_* 等扁平 id）。

校验（V6 同源收口：扁平 taxonomy 彻底退役，单一真相源 = publish/tags）：
  C1  扁平 tag_taxonomy 在 Go/Dart 业务代码中零引用，且 _shared/tag_taxonomy.yaml
      与 _shared/tag_ref_migration.yaml 物理文件不存在（已删除，不留第二套真相源）。
  C2  对象标签字段已切路径制 tagRef（post / circle / entity.homepage / user_profile
      的 fields.yaml 至少各含一个 `tag_ref: true` 字段，且不含已废弃 tag_taxonomy_ref）。
  C3  metadata 中不残留旧扁平 id（domain_taxonomy.user_tag_ref 等已切路径制 tagRef）。
  C4  metadata 文档(.md)不得引用扁平 tag_taxonomy（防 README 等回潮盲区，单一真相源 = publish/tags）。

用法: python3 verify_tag_ref_source_of_truth.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
META = ROOT / "quwoquan_service" / "contracts" / "metadata"
GROUPS = ("Topic", "Audience", "Format", "Entity")

errors: list[str] = []
warnings: list[str] = []


def c1_zero_reference() -> None:
    """扁平 tag_taxonomy 在 Go/Dart 代码零引用，且废弃文件已物理删除。"""
    pat = re.compile(r"tag_taxonomy")
    hits: list[str] = []
    for base in (ROOT / "quwoquan_service", ROOT / "quwoquan_app"):
        if not base.exists():
            continue
        for ext in ("*.go", "*.dart"):
            for f in base.rglob(ext):
                if "/generated/" in str(f) or f.name.endswith(".g.dart"):
                    # 生成产物不应引用；若引用同样视为违规，故不豁免
                    pass
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if pat.search(text):
                    hits.append(str(f.relative_to(ROOT)))
    if hits:
        errors.append(
            "C1: 扁平 tag_taxonomy 仍被 Go/Dart 引用（应改用路径制 tagRef）:\n  "
            + "\n  ".join(hits)
        )
    # 物理文件必须已删除（单一真相源 = publish/tags，不留过渡映射）
    for retired in ("tag_taxonomy.yaml", "tag_ref_migration.yaml"):
        p = META / "_shared" / retired
        if p.exists():
            errors.append(
                f"C1: 废弃扁平 taxonomy 文件仍存在 _shared/{retired}（V6 已收口，应物理删除）"
            )


def c2_fields_use_tag_ref() -> None:
    """对象标签字段已切路径制 tagRef。"""
    required = {
        "content/post/fields.yaml": "post.tagRefs",
        "social/circle/fields.yaml": "circle.tags",
        "entity/homepage/fields.yaml": "entity.categoryTags/highlightTags",
        "user/user_profile/fields.yaml": "user.interestTags",
    }
    for rel, desc in required.items():
        p = META / rel
        if not p.exists():
            errors.append(f"C2: 缺少 {rel}")
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if "tag_ref: true" not in text:
            errors.append(f"C2: {rel} 未发现 `tag_ref: true`（{desc} 应切路径制 tagRef）")
        if "tag_taxonomy_ref:" in text:
            errors.append(f"C2: {rel} 仍含已废弃属性 `tag_taxonomy_ref`")


def c3_no_flat_ids() -> None:
    """metadata 中不残留旧扁平 id（domain_taxonomy.user_tag_ref 等已切路径制 tagRef）。"""
    dt = META / "_shared" / "domain_taxonomy.yaml"
    if not dt.exists():
        return
    text = dt.read_text(encoding="utf-8", errors="ignore")
    ref_re = re.compile(r"^\s*user_tag_ref:\s*(\S+)\s*$", re.MULTILINE)
    refs = [m.group(1).strip() for m in ref_re.finditer(text)]
    tags_root = ROOT / "quwoquan_data" / "publish" / "tags"
    for ref in refs:
        if ref.split("/", 1)[0] not in GROUPS:
            errors.append(
                f"C3: domain_taxonomy.user_tag_ref 仍为旧扁平 id 或非法 tagRef（须以四分组开头）: {ref}"
            )
            continue
        # 真树存在则做 resolvable 真校验（产物不入 git，CI 缺失时 SKIP）
        if tags_root.exists() and not (tags_root / ref).exists():
            errors.append(f"C3: user_tag_ref 在 taxonomy 不可解析: {ref}")
    if not tags_root.exists():
        warnings.append(
            "C3: publish/tags 产物不在仓库（数据工程产物不入 git）；"
            "user_tag_ref resolvable 真校验 SKIP，仅校验路径格式。"
        )


def c4_metadata_docs_clean() -> None:
    """metadata 文档(.md)不得引用扁平 tag_taxonomy（README 等回潮盲区）。

    C1 只扫 .go/.dart 业务代码，metadata 自身的 .md（README/DESIGN 等）是盲区；
    此前 README 把已删的 tag_taxonomy.yaml 写成现行真相源回潮未被任何门禁抓住。
    单一真相源 = quwoquan_data/publish/tags，metadata 文档不得描述扁平 taxonomy。
    """
    pat = re.compile(r"tag_taxonomy")
    hits: list[str] = []
    for f in META.rglob("*.md"):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                hits.append(f"{f.relative_to(ROOT)}:{i}")
    if hits:
        errors.append(
            "C4: metadata 文档仍引用扁平 tag_taxonomy（单一真相源 = publish/tags，"
            "文档不得把已删扁平 taxonomy 写成现行真相源）:\n  " + "\n  ".join(hits)
        )


def main() -> int:
    c1_zero_reference()
    c2_fields_use_tag_ref()
    c3_no_flat_ids()
    c4_metadata_docs_clean()

    for w in warnings:
        print(f"[verify_tag_ref] WARN {w}")
    if errors:
        for e in errors:
            print(f"[verify_tag_ref] FAIL {e}")
        return 1
    print("[verify_tag_ref] OK: 标签真相源收口校验通过（扁平 taxonomy 零引用 / 字段已切 tagRef / 迁移格式合法 / 文档无回潮）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
