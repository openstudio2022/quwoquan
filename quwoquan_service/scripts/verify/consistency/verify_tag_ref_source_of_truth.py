#!/usr/bin/env python3
"""标签真相源门禁。

唯一标签真相源 = 数据工程路径制 taxonomy
（quwoquan_data/control_plane/governance/taxonomy，
四分组 Topic/Audience/Format/Entity，tagRef = 目录路径）。已废弃云侧扁平
tag_taxonomy.yaml（topic_*/circle_*/interest_* 等扁平 id）。

校验：
  C1  扁平 tag_taxonomy 在 Go/Dart 业务代码中零引用，且 _shared/tag_taxonomy.yaml
      与 _shared/tag_ref_migration.yaml 物理文件不存在（已删除，不留第二套真相源）。
  C2  对象标签字段已切路径制 tagRef（post / circle / entity.homepage / user_profile
      的 fields.yaml 至少各含一个 `tag_ref: true` 字段，且不含已废弃 tag_taxonomy_ref）。
  C3  metadata 中不残留旧扁平 id（domain_taxonomy.user_tag_ref 等已切路径制 tagRef）。
  C4  metadata 不得引用扁平 tag_taxonomy，也不得把 publish/tags 描述为真相源。

用法: python3 verify_tag_ref_source_of_truth.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import repository_root  # noqa: E402

ROOT = repository_root()
META = ROOT / "quwoquan_service" / "contracts" / "metadata"
SERVICE_ROOT = ROOT / "quwoquan_service" / "services"
GROUPS = ("Topic", "Audience", "Format", "Entity")
TAXONOMY_ROOT = ROOT / "quwoquan_data" / "control_plane" / "governance" / "taxonomy"

errors: list[str] = []
checks: list[str] = []


def c1_zero_reference() -> None:
    """扁平 tag_taxonomy 在 Go/Dart 代码零引用，且废弃文件已物理删除。"""
    pat = re.compile(r"\btag_taxonomy(?!_release)\b")
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
    # 物理文件必须已删除，不留过渡映射。
    for retired in ("tag_taxonomy.yaml", "tag_ref_migration.yaml"):
        p = META / "_shared" / retired
        if p.exists():
            errors.append(
                f"C1: 废弃扁平 taxonomy 文件仍存在 _shared/{retired}（V6 已收口，应物理删除）"
            )


def c2_fields_use_tag_ref() -> None:
    """对象标签字段已切路径制 tagRef。"""
    required = {
        "content-service/contracts/content/post/fields.yaml": "post.tagRefs",
        "circle-service/contracts/circle_management/circle/fields.yaml": "circle.tags",
        "entity-service/contracts/entity_homepage/homepage/fields.yaml": "entity.categoryTags/highlightTags",
        "user-service/contracts/account/user_account/fields.yaml": "user.interestTags",
    }
    for rel, desc in required.items():
        p = SERVICE_ROOT / rel
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
    if not TAXONOMY_ROOT.is_dir():
        errors.append(
            "C3: 标签真相源目录缺失: "
            "quwoquan_data/control_plane/governance/taxonomy"
        )
        return
    for ref in refs:
        if ref.split("/", 1)[0] not in GROUPS:
            errors.append(
                f"C3: domain_taxonomy.user_tag_ref 仍为旧扁平 id 或非法 tagRef（须以四分组开头）: {ref}"
            )
            continue
        definition = TAXONOMY_ROOT / ref / "_definition.json"
        if not definition.is_file():
            errors.append(f"C3: user_tag_ref 在 taxonomy 不可解析: {ref}")


def c4_metadata_contract_clean() -> None:
    """metadata 不得恢复扁平 taxonomy 或把发布快照提升为配置真相源。"""
    flat_pat = re.compile(r"tag_taxonomy\.(?:yaml|yml)|tag_taxonomy_ref")
    publish_truth_pat = re.compile(
        r"(?:唯一|单一)?真相源[^\n]*publish/tags|publish/tags[^\n]*(?:唯一|单一)?真相源"
    )
    hits: list[str] = []
    metadata_roots = [META]
    metadata_roots.extend(
        sorted(path for path in SERVICE_ROOT.glob("*/contracts") if path.is_dir())
    )
    for metadata_root in metadata_roots:
        for pattern in ("*.md", "*.yaml", "*.yml", "*.json"):
            files = metadata_root.rglob(pattern)
            for f in files:
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except OSError as exc:
                    errors.append(f"C4: metadata 文件不可读 {f.relative_to(ROOT)}: {exc}")
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if flat_pat.search(line) or publish_truth_pat.search(line):
                        hits.append(f"{f.relative_to(ROOT)}:{i}")
    if hits:
        errors.append(
            "C4: metadata 仍引用废弃扁平 taxonomy，或把 publish/tags 误写为"
            "配置真相源:\n  " + "\n  ".join(hits)
        )


def main() -> int:
    c1_zero_reference()
    c2_fields_use_tag_ref()
    c3_no_flat_ids()
    c4_metadata_contract_clean()

    for check in checks:
        print(f"[verify_tag_ref] OK {check}")
    if errors:
        for e in errors:
            print(f"[verify_tag_ref] FAIL {e}")
        return 1
    print("[verify_tag_ref] OK: 标签真相源收口校验通过（扁平 taxonomy 零引用 / 字段已切 tagRef / 路径可解析 / 文档无回潮）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
