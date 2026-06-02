"""asset:// 引用闭环契约测试（评审痛点「图片找不到对应资源」硬门）。

覆盖：引用→manifest→fileName→物理文件→sha256 全链；assetId 可读化（含中文实体名）；
gallery.md 引用同样纳入；缺文件 / sha256 不一致 / 引用悬空均判 issue。
可直接运行 python3 quwoquan_data/tests/test_asset_refs.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="asset_refs_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _common.article_package import (  # noqa: E402
    asset_id_from_object_key,
    build_gallery_markdown,
    semantic_asset_caption,
    sha256_file,
)
from _common.io import write_json  # noqa: E402
from verify_content_quality import asset_closure_issues  # noqa: E402


def _make_post(post_dir: Path, *, cover_file: str = "九寨沟_cover.jpg") -> dict:
    """落一个最小但闭环完整的 post 包，返回 manifest。"""
    assets_dir = post_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    cover_path = assets_dir / cover_file
    cover_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes-cover")
    detail_path = assets_dir / "九寨沟_detail_1.jpg"
    detail_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes-detail")

    cover_id = asset_id_from_object_key("media/image/post/九寨沟/cover.jpg")
    detail_id = asset_id_from_object_key("media/image/post/九寨沟/detail_1.jpg")

    article = (
        f"---\ntitle: 九寨沟\ncoverImage: asset://{cover_id}\n---\n\n"
        f"正文。\n\n:::figure\n![](asset://{detail_id})\n:::\n"
    )
    (post_dir / "article.md").write_text(article, encoding="utf-8")

    gallery_assets = [
        {"assetId": cover_id, "fileName": cover_file, "role": "cover", "entityName": "九寨沟"},
        {"assetId": detail_id, "fileName": "九寨沟_detail_1.jpg", "role": "node", "entityName": "九寨沟"},
    ]
    (post_dir / "gallery.md").write_text(build_gallery_markdown("九寨沟", gallery_assets), encoding="utf-8")

    manifest = {
        "assets": [
            {"assetId": cover_id, "fileName": cover_file, "caption": "九寨沟", "imageLayout": "fullWidth"},
            {"assetId": detail_id, "fileName": "九寨沟_detail_1.jpg", "caption": "九寨沟", "imageLayout": "wrapRight"},
        ],
        "articleAssetManifest": {
            "assets": [
                {"assetId": cover_id, "sha256": sha256_file(cover_path)},
                {"assetId": detail_id, "sha256": sha256_file(detail_path)},
            ]
        },
    }
    write_json(post_dir / "manifest.json", manifest)
    return manifest


def test_asset_id_is_readable_with_chinese():
    aid = asset_id_from_object_key("media/image/post/九寨沟/cover.jpg")
    assert "九寨沟" in aid, f"assetId should keep readable entity name: {aid}"
    assert aid.startswith("data_asset_")
    # 唯一性：不同 objectKey 仍有不同尾缀。
    other = asset_id_from_object_key("media/image/post/九寨沟/detail_1.jpg")
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
    (post_dir / "assets" / "九寨沟_cover.jpg").unlink()
    issues = asset_closure_issues(post_dir, manifest)
    assert any("asset file missing on disk" in i for i in issues), issues


def test_sha256_mismatch_is_flagged():
    post_dir = _TMP / "tamper"
    manifest = _make_post(post_dir)
    (post_dir / "assets" / "九寨沟_cover.jpg").write_bytes(b"tampered-content")
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


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"asset refs tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
