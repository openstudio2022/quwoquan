#!/usr/bin/env python3
"""标签真相源门禁（V0.5 B0：标签真相源收口）。

唯一标签真相源 = 数据工程路径制 taxonomy（quwoquan_data/publish/v1/tags，
四分组 Topic/Audience/Format/Entity，tagRef = 目录路径）。已废弃云侧扁平
tag_taxonomy.yaml（topic_*/circle_*/interest_* 等扁平 id）。

校验：
  C1  扁平 tag_taxonomy 在 Go/Dart 业务代码中零引用。
  C2  对象标签字段已切路径制 tagRef（post / circle / entity.homepage / user_profile
      的 fields.yaml 至少各含一个 `tag_ref: true` 字段）。
  C3  _shared/tag_ref_migration.yaml 的 launch 子集目标 tagRef 格式合法
      （以 Topic/Audience/Format/Entity 开头，verify_tag_tree.py R10）；
      若 publish/v1/tags 产物存在则真校验目录可解析，缺失则 SKIP（首发子集产物
      由数据工程主线后置产出，不阻断会话0门禁）。

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
    """扁平 tag_taxonomy 在 Go/Dart 代码零引用。"""
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


def c2_fields_use_tag_ref() -> None:
    """对象标签字段已切路径制 tagRef。"""
    required = {
        "content/post/fields.yaml": "post.tags",
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


def c3_migration_targets() -> None:
    """迁移映射 launch 子集目标 tagRef 格式合法 + 可选 resolvable。"""
    mig = META / "_shared" / "tag_ref_migration.yaml"
    if not mig.exists():
        errors.append("C3: 缺少 _shared/tag_ref_migration.yaml")
        return
    text = mig.read_text(encoding="utf-8", errors="ignore")
    # 匹配形如:  key: { tagRef: Topic/旅行, status: launch }
    line_re = re.compile(
        r"\{\s*tagRef:\s*([^,}]+?)\s*,\s*status:\s*(launch|deferred)\s*\}"
    )
    launch_refs: list[str] = []
    for m in line_re.finditer(text):
        ref, status = m.group(1).strip(), m.group(2).strip()
        if status == "launch":
            launch_refs.append(ref)
    if not launch_refs:
        errors.append("C3: tag_ref_migration.yaml 未发现 launch 子集映射")
        return
    for ref in launch_refs:
        if not ref.split("/", 1)[0] in GROUPS:
            errors.append(f"C3: launch tagRef 非法（须以四分组开头）: {ref}")

    # 可选 resolvable 真校验（产物存在才做）
    tags_root = ROOT / "quwoquan_data" / "publish" / "v1" / "tags"
    if not tags_root.exists():
        warnings.append(
            "C3: publish/v1/tags 产物不在仓库（数据工程主线后置）；"
            "首发子集 resolvable 真校验 SKIP，仅校验格式。"
        )
        return
    for ref in launch_refs:
        if not (tags_root / ref).exists():
            errors.append(f"C3: launch tagRef 在 taxonomy 不可解析: {ref}")


def main() -> int:
    c1_zero_reference()
    c2_fields_use_tag_ref()
    c3_migration_targets()

    for w in warnings:
        print(f"[verify_tag_ref] WARN {w}")
    if errors:
        for e in errors:
            print(f"[verify_tag_ref] FAIL {e}")
        return 1
    print("[verify_tag_ref] OK: 标签真相源收口校验通过（扁平 taxonomy 零引用 / 字段已切 tagRef / 迁移格式合法）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
