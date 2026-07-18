"""单 execution 写作分组编排红绿测试。

覆盖：
- partition_writer_groups 切分（N 个实体按 writer_group_size 均匀分组，余数成尾批）。
- build_writer_group_pack 聚合 per-ref writing_pack 摘要 + 回写协议。
- writer_group_issues：缺 writing_pack（未 prepare）即报。
- render_writer_group_prompt：含篇目、各篇写回路径、跨篇多样性与 execution 编排约束。
- write_writer_group：落 `_shared/workspace/post/writer_groups/`。
- writer_group_completion_status：占位=pending、agent 草稿=done。

可直接运行：pytest quwoquan_data/tests/local_contract/execution/test_writer_groups__behavior__functional__local_contract_test.py
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


from content.execution.writer_groups import (  # noqa: E402
    writer_group_completion_status,
    writer_group_dir,
    writer_group_issues,
    build_writer_group_pack,
    partition_writer_groups,
    render_writer_group_prompt,
    write_writer_group,
)
from content.post import object_index as content_object  # noqa: E402
from content.post.article.draft_io import (  # noqa: E402
    write_agent_draft,
    write_placeholder_draft,
    write_writing_pack,
)
from core.paths import ensure_execution_command_layout, ensure_execution_layout  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

EXECUTION_ID = "20260711--travel-article-agent-pack--cn-sichuan--canary-001"


def setup_function() -> None:
    build_execution_fixture(EXECUTION_ID)


def _prepare(refs):
    ensure_execution_layout(EXECUTION_ID)
    ensure_execution_command_layout(EXECUTION_ID, "post")
    for ref in refs:
        content_object.register_content_object(EXECUTION_ID, ref, content_type="article", angle="体验", title=f"{ref} 标题")
        write_writing_pack(EXECUTION_ID, ref, {"title": f"{ref} 标题", "styleFamily": "实用攻略风", "mustIncludeFacts": [f"{ref} 门票", f"{ref} 交通"]})


def test_partition_writer_groups_splits():
    groups = partition_writer_groups([f"e{i}" for i in range(11)], 4)
    assert [len(g) for g in groups] == [4, 4, 3]
    assert partition_writer_groups(["a", "b"], 0) == [["a"], ["b"]]  # size<1 视为 1


def test_build_pack_aggregates_and_protocol():
    refs = ["九寨沟", "都江堰"]
    _prepare(refs)
    pack = build_writer_group_pack(EXECUTION_ID, 1, refs)
    assert pack["refCount"] == 2
    for item in pack["items"]:
        assert item["hasPack"] is True
        assert item["articleOut"].endswith("/draft.article.md")
        assert item["styleFamily"] == "实用攻略风"


def test_pack_issues_flags_missing_writing_pack():
    content_object.register_content_object(EXECUTION_ID, "从未prepare的实体", content_type="article", angle="体验", title="从未prepare的实体 标题")
    pack = build_writer_group_pack(EXECUTION_ID, 9, ["从未prepare的实体"])
    issues = writer_group_issues(pack)
    assert any("missing writing_pack" in i for i in issues), issues


def test_render_prompt_has_diversity_and_writeback_paths():
    refs = ["九寨沟", "都江堰"]
    _prepare(refs)
    prompt = render_writer_group_prompt(build_writer_group_pack(EXECUTION_ID, 1, refs))
    assert "跨篇" in prompt
    assert "posts/article/体验/九寨沟 标题/1/4.draft/draft.article.md" in prompt
    assert "posts/article/体验/都江堰 标题/1/4.draft/draft.article.md" in prompt
    assert "execution orchestrator" in prompt


def test_write_writer_group_emits_files():
    refs = ["九寨沟", "都江堰"]
    _prepare(refs)
    write_writer_group(EXECUTION_ID, 1, refs)
    d = writer_group_dir(EXECUTION_ID)
    assert (d / "1.writer_group_pack.json").exists()
    assert (d / "1.writer_group_prompt.md").exists()


def test_completion_status_done_vs_pending():
    refs = ["九寨沟", "都江堰"]
    _prepare(refs)
    write_placeholder_draft(EXECUTION_ID, "九寨沟")
    write_agent_draft(
        EXECUTION_ID,
        "都江堰",
        "# 都江堰\n\n正文。",
        model="cursor-agent",
        cited_source_paths=[],
        covered_facts=[],
        agent_run_id="run-dujiangyan",
        agent_id="agent-dujiangyan",
    )
    status = writer_group_completion_status(EXECUTION_ID, refs)
    assert status["done"] == ["都江堰"]
    assert status["pending"] == ["九寨沟"]
    assert status["total"] == 2


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"execution writer group tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
