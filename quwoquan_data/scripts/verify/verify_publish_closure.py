#!/usr/bin/env python3
"""Verify canonical publish has no dangling or orphaned consumer objects, and that every
media digest it references is held by at least one durable copy (content library or the
out-of-repo carried media root)."""
from __future__ import annotations

import sys
from pathlib import Path


sys.dont_write_bytecode = True

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical.creator_avatar_quality import (
    creator_avatar_quality_issues,
)
from content.release.canonical.media_holding_closure import (
    MediaReferenceRecordError,
    media_references_in_tree,
)
from content.release.canonical.object_transaction_audit import validate_publish_invariants
from core.content_library import MediaHoldingError, carried_media_entry, resolve_media_holding
from core.paths import PUBLISH_ROOT, carried_media_root
from verify.verify_publish_purity import publish_structure_issues


def carried_media_closure_issues(publish_root: Path) -> list[dict[str, str]]:
    """随体闭包：canonical 引用的每个媒体摘要必须在 content library 或随体根至少一处可达。

    随体已出仓、不受版本控制，所以「可检测」由这里保证；「可重建」由 canonical 记录的
    sourceUrl 保证——缺失时把它一起报出，字节可按来源直链原样重取。
    """
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        references = list(media_references_in_tree(publish_root))
    except MediaReferenceRecordError as exc:
        # 记录形态本身不合法（如只有 objectKey 没有 sha256）时门禁同样 fail closed，
        # 但以 typed issue 报出而不是让门禁进程崩溃。
        return [{"code": "DATA.PUBLISH.MEDIA_RECORD_INVALID", "ref": str(exc)}]
    for reference in references:
        digest = reference.digest
        if digest in seen:
            continue
        seen.add(digest)
        held = False
        try:
            resolve_media_holding(digest)
            held = True
        except (MediaHoldingError, ValueError):
            held = carried_media_entry(digest) is not None
        if not held:
            issues.append(
                {
                    "code": "DATA.PUBLISH.CARRIED_MEDIA_MISSING",
                    "ref": (
                        f"{reference.reference_ref} digest={digest} "
                        f"(sourceUrl={_source_url_for(publish_root, reference) or '?'}; carriedRoot={carried_media_root()})"
                    ),
                }
            )
    return issues


def _source_url_for(publish_root: Path, reference) -> str:
    """从声明该引用的 rights/manifest 文档里找回来源直链，让缺失字节可按来源重取。"""
    import json

    try:
        document = json.loads((publish_root / reference.document_ref).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    for row in document.get("assets") or []:
        if not isinstance(row, dict):
            continue
        digest = str(row.get("sha256") or (row.get("asset") or {}).get("sha256") or "")
        if digest == reference.digest:
            return str(row.get("originalAssetUrl") or row.get("sourceUrl") or row.get("collectionPageUrl") or row.get("source") or "")
    return ""


def main() -> int:
    report = validate_publish_invariants(PUBLISH_ROOT)
    creator_issues = creator_avatar_quality_issues(PUBLISH_ROOT)
    structure_issues = publish_structure_issues(PUBLISH_ROOT)
    carried_issues = carried_media_closure_issues(PUBLISH_ROOT)
    issues = [*report["issues"], *creator_issues, *carried_issues]
    if structure_issues or issues:
        print("[verify_publish_closure] FAIL")
        for issue in structure_issues:
            print(f"  - publish_structure: {issue}")
        for issue in issues:
            print(f"  - {issue['code']}: {issue['ref']}")
        return 1
    print(f"[verify_publish_closure] OK mediaRefs={report['mediaRefCount']} carriedRoot={carried_media_root()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
