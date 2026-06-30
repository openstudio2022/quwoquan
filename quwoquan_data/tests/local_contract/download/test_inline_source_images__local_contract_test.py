"""RC3 子步C2：同源内联 <img> 候选构建 + 走五道硬门后回连段落占位的契约测试。

可直接运行：python3 quwoquan_data/tests/local_contract/download/test_inline_source_images__local_contract_test.py
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

import io  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402

os.environ.setdefault("QWQ_RUNTIME_ROOT", tempfile.mkdtemp(prefix="inline_img_rt_"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import download.handler_images as hi  # noqa: E402
from download.fetch import _html_to_plain_text_with_inline_images  # noqa: E402


def test_inline_extractor_prefers_lazy_data_attr_over_placeholder_src():
    """RC3 漏图根因：lazy 站点把真实图放 data-original，src 留占位 gif。

    抽取器必须取 data-* 真实地址，否则游记数十张图被占位吞掉（用户实测九寨沟游记缺图）。
    """
    html = (
        "<html><body>"
        "<p>九寨沟五花海</p>"
        "<img src='https://qunarzz.com/assets/blank.gif' "
        "data-original='https://tr-osdcp.qunarzz.com/photo/real-001.jpg'/>"
        "<p>五彩池</p>"
        "<img src='https://qunarzz.com/img/loading.gif' "
        "data-src='https://tr-osdcp.qunarzz.com/photo/real-002.jpg'/>"
        "<img src='https://cdn.example.com/photo/plain-003.jpg'/>"
        "</body></html>"
    )
    _text, imgs = _html_to_plain_text_with_inline_images(html, "https://travel.qunar.com/youji/1")
    srcs = [i["src"] for i in imgs]
    assert "https://tr-osdcp.qunarzz.com/photo/real-001.jpg" in srcs
    assert "https://tr-osdcp.qunarzz.com/photo/real-002.jpg" in srcs
    assert "https://cdn.example.com/photo/plain-003.jpg" in srcs
    # 占位 gif 绝不被当成正文配图
    assert not any("blank.gif" in s or "loading.gif" in s for s in srcs)


def test_inline_extractor_merges_consecutive_images_into_figuregroup():
    """P2 图文混排：相邻连续 <img> 合并为单个 :::figuregroup 占位（内部 N 张同序 assetId），
    被真实文字隔断的单图仍是 :::figure 单图块；H1-H6 标题保结构为 markdown `#` 级标题。
    （根因 R-CS10：连续 N 张拆 N 个独立占位 → AI 易丢图/打散图文交错。）
    """
    from _common.figure_groups import iter_figure_groups, figure_image_count

    html = (
        "<html><body>"
        "<h2>第一站 五花海</h2>"
        "<p>清晨抵达五花海，湖水斑斓。</p>"
        "<img src='https://cdn/a1.jpg'/>"
        "<img src='https://cdn/a2.jpg'/>"
        "<img src='https://cdn/a3.jpg'/>"
        "<p>随后前往五彩池。</p>"
        "<img src='https://cdn/b1.jpg'/>"
        "<h3>交通贴士</h3>"
        "<p>建议自驾。</p>"
        "</body></html>"
    )
    text, imgs = _html_to_plain_text_with_inline_images(html, "https://x/y")

    # 标题保结构：H2 -> `## `、H3 -> `### `。
    assert "## 第一站 五花海" in text
    assert "### 交通贴士" in text

    # 相邻连续 3 图 -> 单个 figuregroup count=3，组内 3 个同序 assetId。
    groups = list(iter_figure_groups(text))
    assert len(groups) == 1, text
    gid, declared, group_imgs = groups[0]
    assert gid and declared == 3
    assert [aid for _cap, aid in group_imgs] == [
        "source-inline-001",
        "source-inline-002",
        "source-inline-003",
    ]

    # 被正文隔断的第 4 张图不并入组，保持单图块。
    assert ":::figure\n![source image](asset://source-inline-004)" in text
    # 正文实际图片张数（组内逐张 + 单图）= 4。
    assert figure_image_count(text) == 4

    # 抽取器内联清单与占位一一对应、同序，覆盖全部 4 张图（供 CLI 同源下载回填）。
    assert [i["placeholderId"] for i in imgs] == [
        "source-inline-001",
        "source-inline-002",
        "source-inline-003",
        "source-inline-004",
    ]
    assert [i["src"] for i in imgs] == [
        "https://cdn/a1.jpg",
        "https://cdn/a2.jpg",
        "https://cdn/a3.jpg",
        "https://cdn/b1.jpg",
    ]


def _jpeg(seed: int, size=(800, 600)) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(size[1], size[0], 3), dtype="uint8")
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class _OkVerdict:
    blocks_image_publish = False
    status = "ok"
    reasons: list[str] = []


def test_build_inline_image_candidates_maps_src_and_placeholder():
    rows = [
        {"placeholderId": "source-inline-001", "src": "https://img/a.jpg", "caption": "五花海"},
        {"placeholderId": "source-inline-002", "src": "https://img/b.jpg", "caption": ""},
        {"placeholderId": "", "src": "https://img/c.jpg", "caption": "无占位被跳过"},
        {"placeholderId": "source-inline-004", "src": "", "caption": "无src被跳过"},
        "not-a-mapping",
    ]
    out = hi.build_inline_image_candidates(rows, entity_id="九寨沟")
    assert [c["placeholderId"] for c in out] == ["source-inline-001", "source-inline-002"]
    assert [c["url"] for c in out] == ["https://img/a.jpg", "https://img/b.jpg"]
    assert out[0]["caption"] == "五花海"
    # 相关性用真实 caption，不用实体名拼接伪造；caption 为空则留空交相关性门判定。
    assert out[0]["relevance"] == "五花海"
    assert out[1]["relevance"] == ""


def test_build_inline_image_candidates_empty_input():
    assert hi.build_inline_image_candidates(None, entity_id="九寨沟") == []
    assert hi.build_inline_image_candidates([], entity_id="九寨沟") == []


def test_inline_candidate_flows_through_gates_with_placeholder():
    """内联候选与计划 imageUrls 合并走同一五道硬门；通过门后回连 placeholderId。"""
    saved: dict[str, object] = {}

    def patch(name: str, value) -> None:
        saved[name] = getattr(hi, name)
        setattr(hi, name, value)

    try:
        patch("validate_image_rights", lambda spec, vertical: [])
        patch("_cached_source_image_payload", lambda *a, **k: None)
        patch(
            "fetch_image_payload",
            lambda url, max_bytes=0: {
                "bytes": _jpeg(7),
                "ext": ".jpg",
                "url": url,
                "requestedUrl": url,
                "contentType": "image/jpeg",
                "sha256": "z",
            },
        )
        patch("image_dimensions", lambda b: (800, 600))
        patch("pixel_size_issue", lambda w, h, asset_id: None)
        patch(
            "_write_image_check_temp_file",
            lambda task_id, batch_id, subdir=None, payload=None: Path(tempfile.mkstemp()[1]),
        )
        patch("_assess_source_image", lambda temp, spec, task_id=None, batch_id=None: _OkVerdict())
        patch("_cleanup_image_check_temp_file", lambda p: None)
        patch("relevance_issue", lambda relevance, entity_id, asset_id: None)

        images, issues, funnel = hi._download_source_unit_images(
            {
                "source_id": "article_qunar_base",
                "imageUrls": [],
                "license": "internal-curated",
                "credit": "qunar",
                "url": "https://travel.qunar.com/youji/7870084",
            },
            task_id="旅行/地域/四川省/景区/x",
            batch_id="inline_gate",
            entity_id="九寨沟",
            object_dir=Path(tempfile.mkdtemp(prefix="inline_obj_")),
            ordinal=1,
            vertical="travel",
            extra_candidates=hi.build_inline_image_candidates(
                [
                    {
                        "placeholderId": "source-inline-001",
                        "src": "https://travel.qunar.com/photo/a.jpg",
                        "caption": "五花海高山湖泊实景",
                    }
                ],
                entity_id="九寨沟",
            ),
        )
    finally:
        for key, value in saved.items():
            setattr(hi, key, value)

    assert len(images) == 1, (issues, funnel)
    assert images[0]["placeholderId"] == "source-inline-001"
    assert images[0]["url"] == "https://travel.qunar.com/photo/a.jpg"
    assert funnel["candidateCount"] == 1


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"inline source image tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
