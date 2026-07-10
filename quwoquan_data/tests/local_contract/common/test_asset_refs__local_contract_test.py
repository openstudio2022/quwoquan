"""asset:// 引用闭环契约测试（评审痛点「图片找不到对应资源」硬门）。

覆盖：引用→manifest→fileName→物理文件→sha256 全链；assetId 可读化（含中文实体名）；
gallery.md 引用同样纳入；缺文件 / sha256 不一致 / 引用悬空均判 issue。
可直接运行 python3 quwoquan_data/tests/local_contract/common/test_asset_refs__local_contract_test.py
"""
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

_TMP = Path(tempfile.mkdtemp(prefix="asset_refs_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.article_package import (  # noqa: E402
    build_gallery_markdown,
    copy_asset_files,
    post_asset_id,
    semantic_asset_caption,
    sha256_file,
)
from _common.io import write_json  # noqa: E402
from _common.draft_io import draft_asset_reference_issues  # noqa: E402
from verify.verify_content_quality import asset_closure_issues  # noqa: E402


def _make_post(post_dir: Path) -> dict:
    """落一个最小但闭环完整的 post 包，返回 manifest。"""
    assets_dir = post_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    cover_id = post_asset_id(
        entity_name="九寨沟",
        role="cover",
        global_batch_seq=42,
        ref="九寨沟_攻略",
    )
    detail_id = post_asset_id(
        entity_name="九寨沟",
        role="node",
        global_batch_seq=42,
        ref="九寨沟_攻略",
    )
    cover_file = f"{cover_id}.jpg"
    detail_file = f"{detail_id}.jpg"
    cover_path = assets_dir / cover_file
    cover_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes-cover")
    detail_path = assets_dir / detail_file
    detail_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes-detail")

    article = (
        f"---\ntitle: 九寨沟\ncoverImage: asset://{cover_id}\n---\n\n"
        f"正文。\n\n:::figure\n![](asset://{detail_id})\n:::\n"
    )
    (post_dir / "article.md").write_text(article, encoding="utf-8")

    gallery_assets = [
        {"assetId": cover_id, "fileName": cover_file, "role": "cover", "entityName": "九寨沟"},
        {"assetId": detail_id, "fileName": detail_file, "role": "node", "entityName": "九寨沟"},
    ]
    (post_dir / "gallery.md").write_text(build_gallery_markdown("九寨沟", gallery_assets), encoding="utf-8")

    manifest = {
        "assets": [
            {
                "assetId": cover_id,
                "fileName": cover_file,
                "caption": "九寨沟",
                "imageLayout": "fullWidth",
                "sha256": sha256_file(cover_path),
            },
            {
                "assetId": detail_id,
                "fileName": detail_file,
                "caption": "九寨沟",
                "imageLayout": "wrapRight",
                "sha256": sha256_file(detail_path),
            },
        ],
    }
    write_json(post_dir / "manifest.json", manifest)
    return manifest


def test_asset_id_is_readable_with_chinese():
    aid = post_asset_id(
        entity_name="九寨沟",
        role="cover",
        global_batch_seq=42,
        ref="九寨沟_攻略",
    )
    assert "九寨沟" in aid, f"assetId should keep readable entity name: {aid}"
    assert not aid.startswith("data_asset_")
    # 唯一性：不同 objectKey 仍有不同尾缀。
    other = post_asset_id(
        entity_name="九寨沟",
        role="node",
        global_batch_seq=42,
        ref="九寨沟_攻略",
    )
    assert aid != other


def test_gallery_caption_is_semantic_not_filename():
    cap = semantic_asset_caption({"fileName": "x.jpg", "entityName": "九寨沟", "role": "cover"})
    assert cap == "九寨沟 · 封面", cap
    # agent 写的真实说明原样保留。
    assert semantic_asset_caption({"caption": "晨雾里的五花海", "entityName": "九寨沟"}) == "晨雾里的五花海"


def test_closed_loop_has_no_issues():
    post_dir = _TMP / "ok"
    manifest = _make_post(post_dir)
    assert asset_closure_issues(post_dir, manifest) == []


def test_dangling_reference_is_flagged():
    post_dir = _TMP / "dangling"
    manifest = _make_post(post_dir)
    (post_dir / "article.md").write_text(
        (post_dir / "article.md").read_text(encoding="utf-8") + "\nasset://data_asset_不存在_deadbeef\n",
        encoding="utf-8",
    )
    issues = asset_closure_issues(post_dir, manifest)
    assert any("asset ref not in manifest" in i for i in issues), issues


def test_missing_physical_file_is_flagged():
    post_dir = _TMP / "missing"
    manifest = _make_post(post_dir)
    (post_dir / "assets" / manifest["assets"][0]["fileName"]).unlink()
    issues = asset_closure_issues(post_dir, manifest)
    assert any("asset file missing on disk" in i for i in issues), issues


def test_sha256_mismatch_is_flagged():
    post_dir = _TMP / "tamper"
    manifest = _make_post(post_dir)
    (post_dir / "assets" / manifest["assets"][0]["fileName"]).write_bytes(b"tampered-content")
    issues = asset_closure_issues(post_dir, manifest)
    assert any("sha256 mismatch" in i for i in issues), issues


def test_gallery_reference_also_checked():
    post_dir = _TMP / "gallery_only"
    manifest = _make_post(post_dir)
    # 引用一个 manifest 未登记的 asset 仅出现在 gallery。
    (post_dir / "gallery.md").write_text(
        "# g\n- **x**: `asset://data_asset_野的_cafef00d`\n", encoding="utf-8"
    )
    issues = asset_closure_issues(post_dir, manifest)
    assert any("asset ref not in manifest" in i for i in issues), issues


def test_copy_asset_files_fails_closed_when_source_missing():
    out = _TMP / "copy_missing" / "assets"
    try:
        copy_asset_files(
            [{"assetId": "missing_cover", "fileName": "cover.jpg", "sourcePath": str(_TMP / "nope.jpg")}],
            out,
        )
    except FileNotFoundError as exc:
        assert "asset sourcePath missing" in str(exc)
    else:
        raise AssertionError("copy_asset_files must fail when sourcePath is missing")


def test_draft_unknown_asset_ref_is_flagged_before_materialize():
    article = "正文\n\n:::figure\nasset://九寨沟_cover_01_deadbeef\n:::\n"
    pack = {"assets": [{"assetId": "九寨沟_cover_42_cafef00d", "fileName": "九寨沟_cover_42_cafef00d.jpg"}]}
    issues = draft_asset_reference_issues(article, pack)
    assert any("九寨沟_cover_01_deadbeef" in issue for issue in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"asset refs tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
