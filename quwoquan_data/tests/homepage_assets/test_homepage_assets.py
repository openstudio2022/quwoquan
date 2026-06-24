"""homepage-assets scan/repair contract tests."""
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
import struct
import sys
import tempfile
import zlib
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="homepage_assets_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import read_json, write_json  # noqa: E402
from _common.image_safety import STATUS_UNSAFE, assess_image  # noqa: E402
from homepage_assets.repair import repair_homepage, scan_homepages  # noqa: E402


def _seed_entity(root: Path, *, with_manifest: bool = True) -> Path:
    entity_dir = root / "entities" / "地点" / "景区" / "毕棚沟"
    entity_dir.mkdir(parents=True, exist_ok=True)
    (entity_dir / "page.md").write_text(
        "# 毕棚沟\n\n毕棚沟是川西重要景区，适合秋季彩林、雪山观景和轻徒步。\n",
        encoding="utf-8",
    )
    write_json(entity_dir / "_entity.json", {
        "label": "毕棚沟",
        "domain": "地点",
        "type": "景区",
        "sourceTaskId": "旅行/地域/四川省/景区/景区全覆盖",
        "tagRefs": ["Topic/旅行/季节/秋", "Topic/旅行/场景/徒步"],
    })
    if with_manifest:
        write_json(entity_dir / "manifest.json", {"tagRefs": [], "assets": []})
    return entity_dir


def test_scan_flags_page_without_asset():
    _seed_entity(_TMP / "publish")
    issues = scan_homepages(include_runtime=False, include_publish=True)
    assert len(issues) == 1
    assert issues[0].entity_ref == "地点/景区/毕棚沟"
    assert any("no asset" in item for item in issues[0].issues), issues[0].issues


def test_repair_without_real_assets_fails_closed():
    entity_dir = _seed_entity(_TMP / "runtime" / "tasks" / "旅行" / "地域" / "四川省" / "景区" / "景区全覆盖")
    issue = [i for i in scan_homepages(include_runtime=True, include_publish=False) if i.entity_dir == entity_dir][0]
    result = repair_homepage(issue)
    assert result["remainingIssues"]
    assert "no reusable real homepage assets" in result["remainingIssues"][0]
    assert not (entity_dir / "assets" / "毕棚沟_homepage_hero.png").exists()


def test_repair_reuses_existing_homepage_assets_only():
    entity_dir = _seed_entity(_TMP / "runtime" / "tasks" / "旅行" / "地域" / "四川省" / "景区" / "真实图闭环")
    assets_dir = entity_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "cover.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"cover" * 1000)
    (assets_dir / "detail.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"detail" * 1000)
    issue = [i for i in scan_homepages(include_runtime=True, include_publish=False) if i.entity_dir == entity_dir][0]
    result = repair_homepage(issue)
    assert result["remainingIssues"] == []

    page = (entity_dir / "page.md").read_text(encoding="utf-8")
    assert "内容冷启动" not in page
    assert "asset://cover" in page
    assert "asset://detail" in page

    manifest = read_json(entity_dir / "manifest.json")
    assert len(manifest["assets"]) == 2
    for asset in manifest["assets"]:
        assert (entity_dir / "assets" / asset["fileName"]).is_file()

    remaining = [i for i in scan_homepages(include_runtime=True, include_publish=False) if i.entity_dir == entity_dir]
    assert remaining == []


def test_low_texture_placeholder_png_is_unsafe():
    path = _TMP / "placeholder.png"
    width, height = 320, 180
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            v = 140 + (x + y) % 20
            row.extend((v, v, min(v + 20, 255)))
        rows.append(b"\x00" + bytes(row))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )
    verdict = assess_image(path)
    assert verdict.status == STATUS_UNSAFE
    assert "low_texture_placeholder_graphic" in verdict.reasons


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"homepage assets tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
