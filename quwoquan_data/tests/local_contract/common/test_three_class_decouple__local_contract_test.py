"""P3 三类解耦契约：实体主页主源【只来自百科】+ 文章【含视频则放弃】检测。

- 实体主页 base draft 主源只授予百科（wiki/百度/搜狗百科）primary 资格；官网/官方/政务/媒体降为 supporting。
- 文章来源含内联视频（原生 <video> / 主流视频站嵌入）即标记 hasVideo，内容计划据此弃稿。

可直接运行：python3 quwoquan_data/tests/local_contract/common/test_three_class_decouple__local_contract_test.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os  # noqa: E402

os.environ.setdefault("QWQ_RUNTIME_ROOT", tempfile.mkdtemp(prefix="three_class_rt_"))

from download.fetch import html_has_inline_video  # noqa: E402
from build.homepage_text import _homepage_source_priority  # noqa: E402
from download.research.source_quality import _homepage_can_seed_base_draft  # noqa: E402


def test_article_video_detection_positive_and_negative():
    # 原生 <video> 标签。
    assert html_has_inline_video("<div><p>正文</p><video src='x.mp4'></video></div>")
    # <source type=video> 形式。
    assert html_has_inline_video("<video><source type='video/mp4' src='x.mp4'></video>")
    # 主流视频站 iframe 嵌入（B 站 / YouTube / 腾讯视频）。
    assert html_has_inline_video("<iframe src='https://player.bilibili.com/player.html?aid=1'></iframe>")
    assert html_has_inline_video("<iframe src='https://www.youtube.com/embed/abc'></iframe>")
    assert html_has_inline_video("<iframe src='https://v.qq.com/x/page/abc.html'></iframe>")
    # 纯图文文章不误判。
    assert not html_has_inline_video(
        "<article><h2>九寨沟</h2><p>清晨抵达五花海。</p><img src='a.jpg'/></article>"
    )
    assert not html_has_inline_video("")


def test_homepage_primary_source_is_encyclopedia_only():
    # 百科类授予 primary（priority > 0）。
    for meta in (
        {"researchLane": "homepage", "platform": "维基百科", "category": "encyclopedia"},
        {"researchLane": "homepage", "platform": "百度百科", "category": "encyclopedia"},
        {"researchLane": "homepage", "platform": "搜狗百科", "category": "encyclopedia"},
    ):
        assert _homepage_source_priority(meta) > 0, meta

    # 官网/官方不再是 primary（降为 supporting，priority <= 0）。
    official = {"researchLane": "homepage", "platform": "九寨沟景区官网", "category": "official_site"}
    assert _homepage_source_priority(official) <= 0, official

    # 政务/文旅仍为 supporting。
    gov = {"researchLane": "homepage", "platform": "四川省文旅厅", "category": "government_tourism"}
    assert _homepage_source_priority(gov) <= 0, gov


def test_homepage_base_draft_seed_only_encyclopedia():
    # 只有百科可作主页 base draft 主源。
    assert _homepage_can_seed_base_draft({"platform": "维基百科", "category": "encyclopedia"})
    assert _homepage_can_seed_base_draft({"platform": "百度百科", "category": "encyclopedia"})
    # 官网/政务不可作主页 base draft 主源。
    assert not _homepage_can_seed_base_draft({"platform": "景区官网", "category": "official_site"})
    assert not _homepage_can_seed_base_draft({"platform": "文旅厅", "category": "government_tourism"})


def test_write_source_unit_persists_has_video_flag():
    from _common.source_unit import write_source_unit

    obj = Path(tempfile.mkdtemp(prefix="three_class_obj_"))
    # 含视频来源：hasVideo=True 必须落入 manifest（meta.json），供内容计划弃稿。
    manifest_video = write_source_unit(
        obj,
        ordinal=1,
        source_id="article_with_video",
        source_md="---\ntitle: x\n---\n正文",
        research_lane="article",
        source_role="base",
        url="https://example.com/a",
        title="含视频攻略",
        has_video=True,
    )
    assert manifest_video.get("hasVideo") is True

    # 默认（无视频）：hasVideo=False。
    manifest_plain = write_source_unit(
        obj,
        ordinal=2,
        source_id="article_plain",
        source_md="---\ntitle: y\n---\n正文",
        research_lane="article",
        source_role="base",
        url="https://example.com/b",
        title="纯图文攻略",
    )
    assert manifest_plain.get("hasVideo") is False


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"three-class decouple tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
