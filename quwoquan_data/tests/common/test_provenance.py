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
    batch_entity_object_dir,
    batch_root,
    ensure_batch_layout,
    ensure_task_layout,
)
from _common.provenance import (  # noqa: E402
    PROVENANCE_SCHEMA,
    build_provenance,
    provenance_issues,
)
from _common.post_evidence_chain import build_source_refs_snapshot  # noqa: E402
from _common.source_unit import write_source_unit  # noqa: E402
from _common.stage_reports import write_stage_result  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402

TASK = "出处记录_gwt"
BATCH = "pilot"


def _seed_post(produce_root: Path, ref: str, title: str) -> None:
    register_content_object(TASK, BATCH, ref, content_type="article", angle="攻略", title=title)
    obj = batch_entity_object_dir(TASK, BATCH, "地点", "景区", "九寨沟")
    base_manifest = write_source_unit(
        obj,
        ordinal=1,
        source_id="base",
        source_md="# 九寨沟\n\nsource a",
        clean_md="# 九寨沟\n\nsource a",
        platform="curated",
        source_category="overview_baike",
        url="https://example.com/a",
        title="source a",
        target_ref="/entity/地点/景区/九寨沟",
        relevance="九寨沟基础事实",
        task_id=TASK,
        batch_id=BATCH,
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="supplement",
        source_md="# 九寨沟补充\n\nsource b",
        clean_md="# 九寨沟补充\n\nsource b",
        platform="curated",
        source_category="travelogue",
        url="https://example.com/b",
        title="source b",
        target_ref="/entity/地点/景区/九寨沟",
        relevance="九寨沟补充事实",
        task_id=TASK,
        batch_id=BATCH,
    )
    rel_a = str(base_manifest["sourceRef"])
    source_abs = batch_root(TASK, BATCH) / rel_a
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
            "sourcePaths": [rel_a],
            "sourceUrls": ["https://example.com/a"],
            "assets": [],
        },
    )
    write_prompt(TASK, BATCH, ref, f"# {title}\n\n提示。")
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
            "sourcePaths": [rel_a],
            "sourceUrls": ["https://example.com/a"],
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
        cited_source_paths=[str(source_abs)],
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


def test_materialize_writes_source_refs_snapshot_and_finalization_report():
    post_dir = _materialize_one()
    source_refs = read_json(post_dir / "1.download" / "source_refs.json")
    # 单底稿零参考 v2：sources 长度恒为 1，仅唯一底稿来源单元，无内联原文镜像。
    assert source_refs["schemaVersion"] == "quwoquan_data.source_refs/2"
    assert source_refs["baseSourceRef"].startswith("sources/")
    assert source_refs["baseSourceRef"].endswith("/source.md")
    assert len(source_refs["sources"]) == 1
    assert source_refs["sources"][0]["sourceUnitRef"].startswith("sources/")
    assert source_refs["sources"][0]["role"] == "base"
    assert source_refs["sources"][0]["sourceFileSha256"]
    assert "sourceMarkdown" not in source_refs["sources"][0]
    assert "citedSourceRefs" not in source_refs
    assert "sourcePaths" not in source_refs
    report = read_json(post_dir / "5.review" / "finalization_report.json")
    assert report["articleSource"] == "4.draft/draft.article.md"
    assert report["draftSha256"]
    assert report["finalSha256"]
    assert report["composeSnapshotMatchesDraft"] is True
    assert report["frontmatterInjected"] is True
    assert report["bodyChanged"] is False
    assert report["frontmatterOnlyChange"] is True


def test_source_refs_snapshot_is_single_base_without_inline_mirror():
    """单底稿零参考 v2：snapshot 只登记唯一底稿来源单元，不内联原文镜像。"""
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, "binary_source_asset", "produce")
    obj = batch_entity_object_dir(TASK, "binary_source_asset", "地点", "景区", "九寨沟")
    source_manifest = write_source_unit(
        obj,
        ordinal=1,
        source_id="base",
        source_md="# 九寨沟\n\nsource a",
        clean_md="# 九寨沟\n\nsource a",
        platform="curated",
        source_category="overview_baike",
        url="https://example.com/a",
        title="source a",
        target_ref="/entity/地点/景区/九寨沟",
        relevance="九寨沟基础事实",
        task_id=TASK,
        batch_id="binary_source_asset",
    )
    source_md = str(source_manifest["sourceRef"])

    source_refs = build_source_refs_snapshot(
        TASK,
        "binary_source_asset",
        base_source_ref=source_md,
    )

    assert source_refs["schemaVersion"] == "quwoquan_data.source_refs/2"
    assert source_refs["baseSourceRef"] == source_md
    assert len(source_refs["sources"]) == 1
    base_entry = source_refs["sources"][0]
    assert base_entry["sourceRef"] == source_md
    assert base_entry["role"] == "base"
    assert base_entry["sourceFileSha256"]
    assert "sourceMarkdown" not in base_entry
    assert "sourceCleanMarkdown" not in base_entry


def test_materialize_relativizes_repo_runtime_cited_source_paths():
    post_dir = _materialize_one()
    manifest = read_json(post_dir / "manifest.json")
    provenance = read_json(post_dir / "5.review" / "provenance.json")
    source_refs = read_json(post_dir / "1.download" / "source_refs.json")
    expected = source_refs["baseSourceRef"]
    assert manifest["citedSourceRefs"][0] == expected
    assert provenance["citedSourcePaths"][0] == expected


def test_materialize_relativizes_repo_absolute_runtime_paths():
    task = "出处记录_repo_relative_gwt"
    batch = "pilot_repo"
    ensure_task_layout(task)
    ensure_batch_layout(task, batch, "produce")
    register_content_object(task, batch, "repo_ref", content_type="article", angle="攻略", title="repo 路径攻略")
    obj = batch_entity_object_dir(task, batch, "地点", "景区", "九寨沟")
    source_manifest = write_source_unit(
        obj,
        ordinal=1,
        source_id="base",
        source_md="# source\n\nrepo relative source",
        clean_md="# source\n\nrepo relative source",
        platform="curated",
        source_category="overview_baike",
        url="https://example.com/a",
        title="source a",
        target_ref="/entity/地点/景区/九寨沟",
        task_id=task,
        batch_id=batch,
    )
    source_ref = str(source_manifest["sourceRef"])
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
            "baseSourceRef": source_ref,
            "sourcePaths": [],
            "sourceUrls": ["https://example.com/a"],
            "assets": [],
        },
    )
    write_prompt(task, batch, "repo_ref", "# repo 路径攻略\n\n提示。")
    write_stage_result(task, batch, "produce", "review", "repo_ref", {"decision": "approved", "checks": {}})
    # 顶层批次布局：repo 相对路径走 runtime/batches/<intentLabel>__<batch>/...，
    # 相对化 marker = /batches/<intentLabel>__<batch>/。
    batch_dir_name = batch_root(task, batch).name
    repo_relative = (
        f"quwoquan_data/runtime/batches/{batch_dir_name}/"
        f"{source_ref}"
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

    source_abs = batch_root(task, batch) / source_ref
    write_agent_draft(
        task,
        batch,
        "repo_ref",
        "# repo 路径攻略\n\n正文足够长。" * 20,
        model="cursor-agent",
        cited_source_paths=[str(source_abs)],
        covered_facts=[],
        session_trace="test-session",
        agent_run_id="run-repo-relative",
        agent_id="agent-repo-relative",
    )
    materialized = materialize_posts(task, batch, "article")
    assert len(materialized) == 1
    manifest = read_json(materialized[0] / "manifest.json")
    provenance = read_json(materialized[0] / "5.review" / "provenance.json")
    expected = source_ref
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


def test_build_provenance_records_cited_binary_asset_as_original_source():
    source_md = "entities/地点/景区/都江堰/1.download/sources/04.article/source.md"
    asset_ref = "entities/地点/景区/都江堰/1.download/sources/04.article/assets/cover.jpg"
    data = build_provenance(
        "ref2",
        writing_pack={"title": "都江堰"},
        draft_meta={
            "generator": "agent",
            "agentRunId": "run-2",
            "promptSha256": "sha256:p",
            "writingPackSha256": "sha256:w",
            "sourceBundleSha256": "sha256:s",
            "draftSha256": "sha256:d",
            "citedSourcePaths": [source_md, asset_ref],
        },
        review_payload={"decision": "approved", "checks": {}},
        compose_payload={
            "sourcePaths": [source_md],
            "sourceUrls": ["https://example.com/source"],
            "citedSourceRefs": [source_md, asset_ref],
            "articleMarkdownDigest": "digest",
        },
        manifest={"contentType": "article", "articleMarkdownDigest": "digest"},
    )

    original_paths = {str(row.get("path")) for row in data["originalSources"]}
    assert source_md in original_paths
    assert asset_ref in original_paths


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"provenance tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
