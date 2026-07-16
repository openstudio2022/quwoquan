"""Current execution and canonical publish quality cleanup contract."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="dirty_data_"))

sys.path.insert(0, str(SCRIPTS_ROOT))

from core.io import write_json  # noqa: E402
import core.paths as _paths_mod  # noqa: E402
from content.review.quality.dirty_data import delete_dirty_data, scan_dirty_data  # noqa: E402


def _retarget_roots() -> None:
    os.environ["QWQ_DATA_ROOT"] = str(_TMP)
    os.environ["QWQ_OUTPUT_ROOT"] = str(_TMP / "output")
    os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
    _paths_mod.DATA_ROOT = _TMP
    _paths_mod.OUTPUT_ROOT = _TMP / "output"
    _paths_mod.DATA_OUTPUT_ROOT = _paths_mod.OUTPUT_ROOT / "data"
    _paths_mod.DATA_EXECUTIONS_ROOT = _paths_mod.DATA_OUTPUT_ROOT / "tasks"
    _paths_mod.RUNTIME_ROOT = _paths_mod.DATA_EXECUTIONS_ROOT
    _paths_mod.DATA_EXECUTIONS_ROOT = _paths_mod.DATA_EXECUTIONS_ROOT
    _paths_mod.PUBLISH_ROOT = _TMP / "publish"


def _seed_dirty_homepage() -> Path:
    _retarget_roots()
    execution_id = "20260711--travel-homepage-quality-cleanup--cn-sichuan--canary-001"
    entity_dir = _paths_mod.DATA_EXECUTIONS_ROOT / execution_id / "entities" / "地点" / "景区" / "毕棚沟"
    assets = entity_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (entity_dir / "page.md").write_text(
        "# 毕棚沟\n\n## 为什么值得关注\n\n毕棚沟 属于「地点/景区」实体，是内容冷启动、搜索承接、推荐召回和小艺主动服务都需要识别的基础节点。\n",
        encoding="utf-8",
    )
    (assets / "毕棚沟_homepage_detail.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    write_json(entity_dir / "_entity.json", {"label": "毕棚沟", "domain": "地点", "type": "景区", "executionId": execution_id})
    write_json(entity_dir / "manifest.json", {"assets": [{"assetId": "毕棚沟_homepage_detail", "fileName": "毕棚沟_homepage_detail.png"}]})
    return entity_dir


def _seed_dirty_post() -> Path:
    _retarget_roots()
    execution_id = "20260711--travel-homepage-quality-cleanup--cn-sichuan--canary-001"
    post_dir = _paths_mod.DATA_EXECUTIONS_ROOT / execution_id / "posts" / "article" / "都江堰" / "1"
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "article.md").write_text("正文足够长" * 200 + "\nasset://missing_cover\n", encoding="utf-8")
    write_json(
        post_dir / "manifest.json",
        {
            "contentType": "article",
            "tagRefs": ["Topic/旅行", "Format/内容角度/攻略"],
            "entityRefs": ["/entity/地点/景区/都江堰"],
            "executionId": execution_id,
            "assets": [{"assetId": "missing_cover", "fileName": "img_01.jpg", "sha256": "sha256:" + "0" * 64}],
        },
    )
    return post_dir


def test_dirty_scan_and_delete_removes_bad_artifacts():
    _retarget_roots()
    entity_dir = _seed_dirty_homepage()
    post_dir = _seed_dirty_post()
    rows = scan_dirty_data()
    assert any(row["kind"] == "entity_homepage" for row in rows), rows
    assert any(row["kind"] == "post_package" for row in rows), rows
    deleted = delete_dirty_data(rows)
    assert deleted
    assert not (entity_dir / "page.md").exists()
    assert not (entity_dir / "manifest.json").exists()
    assert not (entity_dir / "assets").exists()
    assert not post_dir.exists()


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"dirty data cleanup tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
