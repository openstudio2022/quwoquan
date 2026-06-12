"""结构化出处 provenance.json 红绿测试 ——「精简中间产物 + 统一回查入口 + 完整性门」。

覆盖：
- materialize 端到端产出最小 provenance.json，且 completeness 门全绿。
- provenance 只保留 final / agentInput / originalSources / gateResults / citedSourcePaths。
- completeness 门：缺文件→missing；generator≠agent→报；originalSources 空→报；decision≠approved→报。
- issues 强制门：无文件→报；digest 不一致→报；cited 源越出 originalSources→报。

可直接运行：python3 quwoquan_data/tests/common/test_provenance.py
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

from _common.content_object import register_content_object  # noqa: E402
from _common.draft_io import write_prompt, write_writing_pack  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_command_root,
    ensure_batch_layout,
    ensure_task_layout,
)
from _common.provenance import (  # noqa: E402
    PROVENANCE_SCHEMA,
    build_provenance,
    provenance_issues,
)
from _common.stage_reports import write_stage_result  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402

TASK = "出处记录_gwt"
BATCH = "pilot"


def _seed_post(produce_root: Path, ref: str, title: str) -> None:
    register_content_object(TASK, BATCH, ref, content_type="article", angle="攻略", title=title)
    rel_a = "task_download/sources/a.md"
    rel_b = "task_download/sources/b.md"
    write_writing_pack(
        TASK,
        BATCH,
        ref,
        {
            "ref": ref,
            "title": title,
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": [],
            "baseSourceRef": rel_a,
            "sourcePaths": [rel_a, rel_b],
            "sourceUrls": ["https://example.com/a", "https://example.com/b"],
            "assets": [],
        },
    )
    write_prompt(TASK, BATCH, ref, f"# {title}\n\n提示。")
    download_root = batch_command_root(TASK, BATCH, "download") / "sources"
    download_root.mkdir(parents=True, exist_ok=True)
    (download_root / "a.md").write_text("# a\n\nsource a", encoding="utf-8")
    (download_root / "b.md").write_text("# b\n\nsource b", encoding="utf-8")
    write_stage_result(
        TASK,
        BATCH,
        "produce",
        "review",
        ref,
        {
            "decision": "approved",
            "qualityScore": 92.0,
            "issues": [],
            "checks": {
                "routeCoverage": {"passed": True, "issues": []},
                "travelogueDensity": {"passed": True, "issues": []},
            },
        },
    )
    write_stage_result(
        TASK,
        BATCH,
        "produce",
        "compose",
        ref,
        {
            "generator": "agent",
            "generatorModel": "cursor-agent",
            "articleMarkdown": f"# {title}\n\n正文：{ref} 的真实叙事展开，足够长以通过字数门校验。" * 12,
            "title": title,
            "publishTitle": title,
            "carrier": "article",
            "entityRefs": [],
            "tagRefs": ["Topic/旅行", "Format/内容角度/攻略"],
            "assets": [],
            "sourcePaths": [rel_a, rel_b],
            "sourceUrls": ["https://example.com/a", "https://example.com/b"],
            "citedSourceRefs": [rel_a],
            "storySpine": {"sourceQuality": [{"sourceId": "a", "score": 0.9}]},
            "relatedSearchPlan": {"queries": ["开放时间"]},
            "evidenceBundle": {"routeNodes": [{"entityName": "九寨沟"}]},
        },
    )
    from _common.draft_io import write_agent_draft

    write_agent_draft(
        TASK,
        BATCH,
        ref,
        f"# {title}\n\n正文：{ref} 的真实叙事展开，足够长以通过字数门校验。" * 12,
        model="cursor-agent",
        cited_source_paths=[
            str((batch_command_root(TASK, BATCH, "download") / "sources" / "a.md")),
            str((batch_command_root(TASK, BATCH, "download") / "sources" / "b.md")),
        ],
        covered_facts=[],
        session_trace="test-session",
        agent_run_id="run-provenance",
        agent_id="agent-provenance",
    )


def _materialize_one() -> Path:
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "produce")
    produce_root = batch_command_root(TASK, BATCH, "produce")
    import shutil

    posts = produce_root / "posts"
    if posts.exists():
        shutil.rmtree(posts)
    _seed_post(produce_root, "九寨沟", "九寨沟看水攻略")
    materialized = materialize_posts(TASK, BATCH, "article")
    assert len(materialized) == 1, materialized
    return materialized[0]


def test_materialize_writes_complete_provenance():
    post_dir = _materialize_one()
    prov_path = post_dir / "5.review" / "provenance.json"
    assert prov_path.exists(), "materialize 必须产出 provenance.json"
    # 取代 produce_trace.json（精简：单一结构化回查入口）。
    assert not (post_dir / "produce_trace.json").exists()
    manifest = read_json(post_dir / "manifest.json")
    assert "articleMarkdownDigest" not in manifest
    assert provenance_issues(post_dir, manifest) == []


def test_provenance_minimal_partitions_present():
    post_dir = _materialize_one()
    data = read_json(post_dir / "5.review" / "provenance.json")
    assert data["schemaVersion"] == PROVENANCE_SCHEMA
    for section in ("final", "agentInput", "originalSources", "gateResults", "citedSourcePaths"):
        assert section in data, section
    for dropped in ("evidenceSources", "intermediate"):
        assert dropped not in data
    assert data["final"]["generator"] == "agent"
    assert data["originalSources"], "原始数据源必须一一记录"
    assert data["gateResults"]["decision"] == "approved"
    assert "routeCoverage" in data["gateResults"]["checks"]


def test_materialize_relativizes_repo_runtime_cited_source_paths():
    post_dir = _materialize_one()
    manifest = read_json(post_dir / "manifest.json")
    provenance = read_json(post_dir / "5.review" / "provenance.json")
    expected = "task_download/sources/a.md"
    assert manifest["citedSourceRefs"][0] == expected
    assert provenance["citedSourcePaths"][0] == expected


def test_materialize_relativizes_repo_absolute_runtime_paths():
    task = "出处记录_repo_relative_gwt"
    batch = "pilot_repo"
    ensure_task_layout(task)
    ensure_batch_layout(task, batch, "produce")
    register_content_object(task, batch, "repo_ref", content_type="article", angle="攻略", title="repo 路径攻略")
    write_writing_pack(
        task,
        batch,
        "repo_ref",
        {
            "ref": "repo_ref",
            "title": "repo 路径攻略",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": [],
            "baseSourceRef": "entities/地点/景区/九寨沟/1.download/sources/01.base/source.md",
            "sourcePaths": [],
            "sourceUrls": ["https://example.com/a"],
            "assets": [],
        },
    )
    write_prompt(task, batch, "repo_ref", "# repo 路径攻略\n\n提示。")
    write_stage_result(task, batch, "produce", "review", "repo_ref", {"decision": "approved", "checks": {}})
    repo_relative = (
        f"quwoquan_data/runtime/tasks/{task}/batches/{batch}/"
        "entities/地点/景区/九寨沟/1.download/sources/01.base/source.md"
    )
    write_stage_result(
        task,
        batch,
        "produce",
        "compose",
        "repo_ref",
        {
            "generator": "agent",
            "generatorModel": "cursor-agent",
            "articleMarkdown": "# repo 路径攻略\n\n正文足够长。" * 20,
            "title": "repo 路径攻略",
            "publishTitle": "repo 路径攻略",
            "carrier": "article",
            "entityRefs": [],
            "tagRefs": ["主题/山水风光", "Format/内容角度/攻略"],
            "assets": [],
            "sourcePaths": [repo_relative],
            "sourceUrls": ["https://example.com/a"],
            "citedSourceRefs": [repo_relative],
            "storySpine": {"beats": ["b1"]},
        },
    )
    from _common.draft_io import write_agent_draft

    source_abs = (
        Path(os.environ["QWQ_RUNTIME_ROOT"])
        / "tasks"
        / task
        / "batches"
        / batch
        / "entities/地点/景区/九寨沟/1.download/sources/01.base"
    )
    source_abs.mkdir(parents=True, exist_ok=True)
    (source_abs / "source.md").write_text("# source\n\nrepo relative source", encoding="utf-8")
    write_agent_draft(
        task,
        batch,
        "repo_ref",
        "# repo 路径攻略\n\n正文足够长。" * 20,
        model="cursor-agent",
        cited_source_paths=[str(source_abs / "source.md")],
        covered_facts=[],
        session_trace="test-session",
        agent_run_id="run-repo-relative",
        agent_id="agent-repo-relative",
    )
    materialized = materialize_posts(task, batch, "article")
    assert len(materialized) == 1
    manifest = read_json(materialized[0] / "manifest.json")
    provenance = read_json(materialized[0] / "5.review" / "provenance.json")
    expected = "entities/地点/景区/九寨沟/1.download/sources/01.base/source.md"
    assert manifest["citedSourceRefs"] == [expected]
    assert provenance["citedSourcePaths"] == [expected]


def test_missing_file_flagged():
    empty = Path(tempfile.mkdtemp())
    issues = provenance_issues(empty, {"articleMarkdownDigest": "x"})
    assert any("missing provenance.json" in i for i in issues)


def _write_provenance(post_dir: Path, *, digest: str, generator: str, originals, cited, decision):
    payload = {
        "schemaVersion": PROVENANCE_SCHEMA,
        "ref": "r",
        "final": {"generator": generator, "articleDigest": digest, "agentRunId": "run-1"},
        "agentInput": {
            "title": "t",
            "promptSha256": "sha256:a",
            "writingPackSha256": "sha256:b",
            "sourceBundleSha256": "sha256:c",
            "draftSha256": "sha256:d",
        },
        "originalSources": originals,
        "gateResults": {"decision": decision, "checks": {}},
        "citedSourcePaths": cited,
    }
    (post_dir / "5.review").mkdir(parents=True, exist_ok=True)
    write_json(post_dir / "5.review" / "provenance.json", payload)


def test_completeness_flags_non_agent_and_empty_sources():
    post_dir = Path(tempfile.mkdtemp())
    _write_provenance(
        post_dir, digest="d", generator="script", originals=[], cited=[], decision="revision_needed"
    )
    issues = provenance_issues(post_dir, {"articleMarkdownDigest": "d"})
    assert any("generator must be 'agent'" in i for i in issues)
    assert any("originalSources empty" in i for i in issues)
    assert any("decision must be 'approved'" in i for i in issues)


def test_issues_soft_skip_when_absent():
    empty = Path(tempfile.mkdtemp())
    assert provenance_issues(empty, {"articleMarkdownDigest": "x"}) != []


def test_issues_flag_digest_and_cited_mismatch():
    post_dir = Path(tempfile.mkdtemp())
    _write_provenance(
        post_dir,
        digest="OLD",
        generator="agent",
        originals=[{"path": "sources/a.md"}],
        cited=["sources/zzz.md"],
        decision="approved",
    )
    issues = provenance_issues(post_dir, {"articleMarkdownDigest": "NEW"})
    assert any("articleDigest != article.md digest" in i for i in issues)
    assert any("cited source not in originalSources" in i for i in issues)


def test_build_provenance_uses_meta_over_compose():
    data = build_provenance(
        "ref1",
        writing_pack={"title": "T", "styleFamily": "实用攻略风", "mustIncludeFacts": ["门票"]},
        draft_meta={
            "generator": "agent",
            "model": "cursor-agent",
            "agentRunId": "run-1",
            "agentId": "agent-1",
            "sessionTrace": "session-1",
            "styleFamily": "旅途随笔风",
            "openingStrategy": "scene_immersion",
            "promptSha256": "sha256:a",
            "writingPackSha256": "sha256:b",
            "sourceBundleSha256": "sha256:c",
            "draftSha256": "sha256:d",
        },
        review_payload={"decision": "approved", "checks": {}},
        compose_payload={"sourcePaths": ["sources/a.md"], "generator": "agent", "articleMarkdownDigest": "d"},
        manifest={"publishTitle": "T", "publishSeq": 1},
    )
    # draft_meta 的 styleFamily 优先于 writing_pack。
    assert data["final"]["styleFamily"] == "旅途随笔风"
    assert data["final"]["openingStrategy"] == "scene_immersion"
    assert data["final"]["agentRunId"] == "run-1"
    assert data["final"]["articleDigest"] == "d"
    assert "mustIncludeFacts" not in data["agentInput"]
    assert data["agentInput"]["promptSha256"] == "sha256:a"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"provenance tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
