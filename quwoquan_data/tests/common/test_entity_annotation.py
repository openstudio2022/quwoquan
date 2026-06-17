"""实体标注红绿测试 ——「文章里把实体标成可点击 inline 链接 + 词典 grounding + ref 闭环」。

覆盖：
- build_entity_dictionary：主实体入词典；extractedEntities 经主页存在性 grounding（无主页者不入）。
- annotate_inline：body 首次出现标注、frontmatter 不动、幂等、长名优先不嵌套。
- merge_entity_refs：主实体 ∪ 被标注实体（去重、normalize），annotate 未跑时退化为仅主实体。
- annotation_closure_issues：主实体覆盖 / 库外实体 grounding / manifest 登记 / 路径合法。
- annotation_publish_issues：发布态强制门（manifest.entityRefs 必须逐一正文标注）。

可直接运行：python3 quwoquan_data/tests/common/test_entity_annotation.py
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

sys.path.insert(0, str(SCRIPTS_ROOT))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.entity_annotation import (  # noqa: E402
    annotate_inline,
    annotation_closure_issues,
    annotation_publish_issues,
    build_entity_dictionary,
    merge_entity_refs,
    parse_entity_links,
)
from _common.entity_extract import homepage_exists  # noqa: E402
from _common.paths import batch_entity_object_dir, ensure_task_layout  # noqa: E402

TASK = "实体标注_gwt"
BATCH = "b1"


def _seed_homepage(name: str, domain: str = "地点", etype: str = "景区") -> None:
    ensure_task_layout(TASK)
    page = batch_entity_object_dir(TASK, BATCH, domain, etype, name) / "page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f"# {name}\n\n实体主页。", encoding="utf-8")


def test_build_dictionary_grounds_on_homepage():
    _seed_homepage("海螺沟")  # 有主页
    brief = {"entityRefs": ["地点/景区/九寨沟"], "subject": {"type": "地点/景区"}}
    draft_meta = {
        "extractedEntities": [
            "字符串候选只进入治理线，不得直接进可点击词典",
            {"name": "海螺沟", "type": "景区"},
            {"name": "无主页实体", "type": "景区"},
        ]
    }
    dictionary, required = build_entity_dictionary(TASK, BATCH, brief, draft_meta)
    assert dictionary["九寨沟"] == "/entity/地点/景区/九寨沟"
    assert dictionary["海螺沟"] == "/entity/地点/景区/海螺沟"
    assert "无主页实体" not in dictionary, "无主页实体不得进词典（grounding）"
    assert required == ["/entity/地点/景区/九寨沟"]
    assert homepage_exists("地点", "景区", "海螺沟", TASK, BATCH) is True


def test_annotate_inline_first_occurrence_and_frontmatter_safe():
    article = (
        "---\ntitle: 九寨沟看水攻略\n---\n\n"
        "九寨沟的水很美，海螺沟也值得一去。后文再次提到九寨沟时不应重复标注。"
    )
    dictionary = {
        "九寨沟": "/entity/地点/景区/九寨沟",
        "海螺沟": "/entity/地点/景区/海螺沟",
    }
    new_article, annotated = annotate_inline(article, dictionary)
    assert "title: 九寨沟看水攻略" in new_article, "frontmatter 不得被标注破坏"
    assert new_article.count("[九寨沟](/entity/地点/景区/九寨沟)") == 1, "仅首次出现标注"
    assert "[海螺沟](/entity/地点/景区/海螺沟)" in new_article
    assert annotated == {"/entity/地点/景区/九寨沟", "/entity/地点/景区/海螺沟"}
    # 幂等：再次标注不变。
    again, _ = annotate_inline(new_article, dictionary)
    assert again == new_article


def test_merge_entity_refs_unions_and_dedup():
    brief = {"entityRefs": ["地点/景区/九寨沟"], "subject": {"type": "地点/景区"}}
    meta = {"annotatedEntityRefs": ["/entity/地点/景区/海螺沟", "地点/景区/九寨沟"]}
    refs = merge_entity_refs(brief, meta)
    assert set(refs) == {"/entity/地点/景区/九寨沟", "/entity/地点/景区/海螺沟"}
    assert len(refs) == 2, "去重"
    assert merge_entity_refs(brief, {}) == ["/entity/地点/景区/九寨沟"], "未标注退化为仅主实体"


def test_closure_flags_missing_coverage_and_ungrounded():
    dictionary = {"九寨沟": "/entity/地点/景区/九寨沟"}
    required = ["/entity/地点/景区/九寨沟"]
    # 主实体未标注 → coverage 报。
    missing = annotation_closure_issues(
        "正文里没有任何实体链接。", manifest_entity_refs=required, dictionary=dictionary, required_refs=required
    )
    assert any("主实体未标注" in i for i in missing)
    # 库外实体（峨眉山不在词典）→ grounding 报；且未登记 manifest。
    ungrounded = annotation_closure_issues(
        "[峨眉山](/entity/地点/景区/峨眉山) 与 [九寨沟](/entity/地点/景区/九寨沟)",
        manifest_entity_refs=required,
        dictionary=dictionary,
        required_refs=required,
    )
    assert any("库外实体" in i for i in ungrounded)
    assert any("未登记" in i for i in ungrounded)
    # 路径不合法。
    malformed = annotation_closure_issues(
        "[九寨沟](/entity/地点)",
        manifest_entity_refs=[],
        dictionary={},
        required_refs=[],
        require_coverage=False,
    )
    assert any("malformed" in i for i in malformed)


def test_publish_issues_soft_and_registration():
    assert annotation_publish_issues("无任何实体链接的发布正文。", ["/entity/地点/景区/九寨沟"]) != []
    art = "[九寨沟](/entity/地点/景区/九寨沟) 的水。"
    # 有实体链接但 manifest 为空，仍然违反登记闭环。
    assert annotation_publish_issues(art, []) != []
    # 有 manifest 但标注实体不在其中 → 报未登记。
    assert annotation_publish_issues(art, ["地点/景区/峨眉山"]) != []
    assert annotation_publish_issues(art, ["地点/景区/九寨沟"]) == [], "normalize 后登记匹配则通过"


def test_parse_entity_links():
    links = parse_entity_links("[九寨沟](/entity/地点/景区/九寨沟) 和 [海螺沟](/entity/地点/景区/海螺沟)")
    assert links == [
        ("九寨沟", "/entity/地点/景区/九寨沟"),
        ("海螺沟", "/entity/地点/景区/海螺沟"),
    ]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"entity annotation tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
