"""按 target_set 只读复核三步产物闭包：1.download → 4.draft → 5.review → final。

seal 已在每步写 receipt 时完成硬事实校验；本模块是宿主/评审可随时调用的只读复核，
只检查当前 `--through` 阶段及其直接前驱的产物在场、schema 与身份绑定，不回扫整棵树。
省略 `--through` 时校验 publish 后每对象 final 产物在场。
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.control_types import AUTHOR_ARTIFACT_BY_CARRIER, carrier_of_target_ref
from core.schema import assert_valid
from core.stage_artifact_contract import STAGES, required_final_artifacts, required_stage_artifacts

_JSON_SCHEMAS: dict[str, tuple[str, str]] = {
    "1.download/source_refs.json": ("source", "object_source_refs"),
    "4.draft/image_work.json": ("content", "image_work"),
    "4.draft/video_script.json": ("content", "video_script"),
    "5.review/content_review.json": ("content", "content_review"),
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def _regular(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _target_refs(root: Path) -> list[str]:
    target_set = _read_json(root / "0.plan/target_set.json")
    assert_valid(target_set, "execution", "target_set", label="target_set")
    return [str(ref) for ref in target_set.get("targetRefs") or []]


def _artifact_issues(root: Path, object_ref: str, stage: str, name: str, execution_id: str) -> list[str]:
    rel = f"{stage}/{name}"
    path = root / object_ref / rel
    if not _regular(path):
        return [f"{object_ref}: missing {rel}"]
    if path.stat().st_size == 0:
        return [f"{object_ref}/{rel}: artifact is empty"]
    schema = _JSON_SCHEMAS.get(rel)
    if schema is None:
        return []
    try:
        document = _read_json(path)
        assert_valid(document, *schema, label=f"{object_ref}/{rel}")
    except (ValueError, TypeError) as exc:
        return [f"{object_ref}/{rel}: schema invalid ({exc})"]
    issues: list[str] = []
    if isinstance(document, Mapping):
        if document.get("executionId") not in (None, execution_id):
            issues.append(f"{object_ref}/{rel}: executionId drift")
        if document.get("objectRef") not in (None, object_ref):
            issues.append(f"{object_ref}/{rel}: objectRef drift")
    return issues


def _download_issues(root: Path, object_ref: str) -> list[str]:
    """source unit 的正文与资产字节必须与 meta/index 记录一致。"""

    from content.execution.seal import SealError, _seal_acquire

    try:
        _seal_acquire(root, [object_ref])
    except (SealError, ValueError, TypeError) as exc:
        return [f"{object_ref}/1.download: {exc}"]
    return []


def _review_issues(root: Path, object_ref: str) -> list[str]:
    review_path = root / object_ref / "5.review/content_review.json"
    if not _regular(review_path):
        return []
    review = _read_json(review_path)
    draft = review.get("draft") if isinstance(review, Mapping) else None
    carrier = carrier_of_target_ref(object_ref)
    expected_ref = f"4.draft/{AUTHOR_ARTIFACT_BY_CARRIER[carrier]}"
    if not isinstance(draft, Mapping) or draft.get("ref") != expected_ref:
        return [f"{object_ref}/5.review: draft ref must be {expected_ref}"]
    draft_path = root / object_ref / expected_ref
    if not _regular(draft_path):
        return [f"{object_ref}/5.review: draft artifact missing"]
    import hashlib

    digest = "sha256:" + hashlib.sha256(draft_path.read_bytes()).hexdigest()
    if draft.get("digest") != digest:
        return [f"{object_ref}/5.review: draft exact binding drift"]
    return []


def verify_stage_artifacts(
    *,
    execution_id: str,
    publish_root: Path | None = None,
    release_root: Path | None = None,
    commercial: bool = True,
    through: str | None = None,
) -> dict[str, Any]:
    del publish_root, release_root, commercial
    if through is not None and through not in STAGES:
        raise ValueError(f"unsupported --through stage: {through}")
    root = paths.execution_root(execution_id)
    issues: list[str] = []
    if not _regular(root / "execution_manifest.json"):
        return {"executionId": execution_id, "passed": False, "issues": ["execution_manifest.json missing"]}
    target_refs = _target_refs(root)
    if through is None:
        stages_to_check: tuple[str, ...] = STAGES
    else:
        index = STAGES.index(through)
        stages_to_check = tuple(STAGES[max(0, index - 1): index + 1])
    for object_ref in target_refs:
        object_dir = root / object_ref
        if not object_dir.is_dir():
            issues.append(f"{object_ref}: declared target object directory missing")
            continue
        carrier = carrier_of_target_ref(object_ref)
        required = required_stage_artifacts(carrier)
        for stage in stages_to_check:
            for name in required.get(stage, ()):
                issues.extend(_artifact_issues(root, object_ref, stage, name, execution_id))
        if through == "1.download":
            issues.extend(_download_issues(root, object_ref))
        if through in (None, "5.review"):
            issues.extend(_review_issues(root, object_ref))
        if through is None:
            for name in required_final_artifacts(carrier):
                if not _regular(object_dir / name):
                    issues.append(f"{object_ref}: missing final/{name}")
    return {
        "executionId": execution_id,
        "through": through,
        "targets": len(target_refs),
        "passed": not issues,
        "issues": issues,
    }


__all__ = ["verify_stage_artifacts"]
