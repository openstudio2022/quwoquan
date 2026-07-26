"""Canonical execution work-package directory evidence contract."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

_OUTPUT_ROOT = Path(tempfile.mkdtemp(prefix="qwq_execution_layout_"))

from core.io import write_json  # noqa: E402
from core.paths import (  # noqa: E402
    EXECUTION_ROOT_ALLOWED_ENTRIES,
    execution_entity_object_dir,
    execution_post_object_dir,
    execution_root,
    ensure_object_stages,
)
from verify.verify_directory_evidence_chain import scan_execution, scan_execution_root  # noqa: E402


def _execution_id(sequence: int) -> str:
    return f"20260711--travel-homepage-layout--test-region-a--pilot-{sequence:03d}"


def _seed_execution(sequence: int) -> tuple[str, Path]:
    execution_id = _execution_id(sequence)
    root = execution_root(execution_id)
    for name in EXECUTION_ROOT_ALLOWED_ENTRIES - {"publish_ref.json"}:
        path = root / name
        if "." in name and name.endswith(".json"):
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, {"executionId": execution_id})
        else:
            path.mkdir(parents=True, exist_ok=True)
    return execution_id, root


def test_execution_root_has_one_stable_allowlist():
    execution_id, root = _seed_execution(1)
    assert not scan_execution_root(execution_id)
    assert {entry.name for entry in root.iterdir()} <= EXECUTION_ROOT_ALLOWED_ENTRIES


def test_execution_root_rejects_flat_command_workspace():
    execution_id, root = _seed_execution(2)
    (root / "source").mkdir()
    issues = scan_execution_root(execution_id)
    assert any("execution/source" in issue for issue in issues), issues


def test_entity_object_rejects_loose_images_directory():
    execution_id, _ = _seed_execution(3)
    entity = execution_entity_object_dir(execution_id, "地点", "景区", "云和梯田")
    ensure_object_stages(entity)
    (entity / "images").mkdir(parents=True)
    write_json(entity / "_entity.json", {"label": "云和梯田", "domain": "地点", "type": "景区"})
    issues = scan_execution(execution_id, require_stage_tree=False)
    assert any("散落 images/" in issue for issue in issues), issues


def test_post_object_rejects_absolute_evidence_path():
    execution_id, _ = _seed_execution(4)
    post = execution_post_object_dir(execution_id, "article", "攻略", "云和梯田行前指南", 1)
    ensure_object_stages(post)
    post.mkdir(parents=True, exist_ok=True)
    (post / "article.md").write_text("# 云和梯田行前指南\n\n正文。", encoding="utf-8")
    write_json(
        post / "manifest.json",
        {"contentType": "article", "assets": [], "citedSourceRefs": ["/tmp/source.md"]},
    )
    issues = scan_execution(execution_id, require_stage_tree=False)
    assert any("绝对路径" in issue for issue in issues), issues


def test_execution_shared_rejects_unregistered_evidence():
    execution_id, root = _seed_execution(5)
    write_json(root / "_shared" / "ad_hoc_report.json", {"status": "unknown"})
    issues = scan_execution(execution_id, require_stage_tree=False)
    assert any("ad_hoc_report.json" in issue and "未登记" in issue for issue in issues), issues


def _run_all() -> None:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"directory evidence gate tests passed ({len(tests)})")


if __name__ == "__main__":
    _run_all()
