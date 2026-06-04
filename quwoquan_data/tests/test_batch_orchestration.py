"""单会话多实体批处理编排红绿测试 ——「日产 10 万级」吞吐路径。

覆盖：
- plan_batches 切分（N 个实体按 batch_size 均匀分组，余数成尾批）。
- build_batch_pack 聚合 per-ref writing_pack 摘要 + 回写协议。
- batch_pack_issues：缺 writing_pack（未 prepare）即报。
- render_batch_prompt：含篇目、各篇写回路径、跨篇多样性约束。
- write_batch：落 _batch/{seq}.batch_pack.json + .batch_prompt.md。
- batch_completion_status：占位=pending、agent 草稿=done。

可直接运行：python3 quwoquan_data/tests/test_batch_orchestration.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.batch_orchestration import (  # noqa: E402
    batch_completion_status,
    batch_dir,
    batch_pack_issues,
    build_batch_pack,
    plan_batches,
    render_batch_prompt,
    write_batch,
)
from _common.draft_io import (  # noqa: E402
    write_agent_draft,
    write_placeholder_draft,
    write_writing_pack,
)
from _common.paths import ensure_batch_layout, ensure_task_layout  # noqa: E402

TASK, BATCH = "批处理_gwt", "pilot"


def _prepare(refs):
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "produce")
    for ref in refs:
        write_writing_pack(TASK, BATCH, ref, {"title": f"{ref} 标题", "styleFamily": "实用攻略风", "mustIncludeFacts": [f"{ref} 门票", f"{ref} 交通"]})


def test_plan_batches_splits():
    groups = plan_batches([f"e{i}" for i in range(11)], 4)
    assert [len(g) for g in groups] == [4, 4, 3]
    assert plan_batches(["a", "b"], 0) == [["a"], ["b"]]  # size<1 视为 1


def test_build_pack_aggregates_and_protocol():
    refs = ["九寨沟", "都江堰"]
    _prepare(refs)
    pack = build_batch_pack(TASK, BATCH, 1, refs)
    assert pack["refCount"] == 2
    for item in pack["items"]:
        assert item["hasPack"] is True
        assert item["articleOut"].endswith("/article.md")
        assert item["styleFamily"] == "实用攻略风"


def test_pack_issues_flags_missing_writing_pack():
    pack = build_batch_pack(TASK, BATCH, 9, ["从未prepare的实体"])
    issues = batch_pack_issues(pack)
    assert any("missing writing_pack" in i for i in issues), issues


def test_render_prompt_has_diversity_and_writeback_paths():
    refs = ["九寨沟", "都江堰"]
    _prepare(refs)
    prompt = render_batch_prompt(build_batch_pack(TASK, BATCH, 1, refs))
    assert "跨篇" in prompt
    assert "九寨沟/article.md" in prompt and "都江堰/article.md" in prompt
    assert "annotate-entities" in prompt


def test_write_batch_emits_files():
    refs = ["九寨沟", "都江堰"]
    _prepare(refs)
    write_batch(TASK, BATCH, 1, refs)
    d = batch_dir(TASK, BATCH)
    assert (d / "1.batch_pack.json").exists()
    assert (d / "1.batch_prompt.md").exists()


def test_completion_status_done_vs_pending():
    refs = ["九寨沟", "都江堰"]
    _prepare(refs)
    write_placeholder_draft(TASK, BATCH, "九寨沟")
    write_agent_draft(
        TASK, BATCH, "都江堰", "# 都江堰\n\n正文。", model="cursor-agent", cited_source_paths=[], covered_facts=[]
    )
    status = batch_completion_status(TASK, BATCH, refs)
    assert status["done"] == ["都江堰"]
    assert status["pending"] == ["九寨沟"]
    assert status["total"] == 2


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"batch orchestration tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
