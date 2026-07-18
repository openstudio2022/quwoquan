"""结构化出处 provenance.json 红绿测试 ——「精简中间产物 + 统一回查入口 + 完整性门」。

覆盖：
- materialize 端到端产出最小 provenance.json，且 completeness 门全绿。
- provenance 只保留 final / agentInput / originalSources / gateResults / citedSourcePaths。
- completeness 门：缺文件→missing；generator≠agent→报；originalSources 空→报；decision≠approved→报。
- issues 强制门：无文件→报；digest 不一致→报；cited 源越出 originalSources→报。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_provenance__behavior__functional__local_contract_test.py
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


from content.post.object_index import register_content_object  # noqa: E402
from content.post.article.draft_io import _source_bundle_sha256, write_prompt, write_writing_pack  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.paths import (  # noqa: E402
    execution_command_root,
    execution_entity_object_dir,
    execution_root,
    ensure_execution_command_layout,
    ensure_execution_layout,
)
from core.provenance import (  # noqa: E402
    PROVENANCE_SCHEMA,
    build_provenance,
    provenance_issues,
)
from core.post_evidence_chain import build_source_refs_snapshot  # noqa: E402
from content.source.source_unit import write_source_unit  # noqa: E402
from content.execution.stage_reports import write_stage_result  # noqa: E402
from content.post.materialize_apply import materialize_posts  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

TASK = "20260711--travel-article-provenance--cn-sichuan--canary-001"


def test_source_bundle_hash_accepts_runtime_relative_path_with_batch_prefix():
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="source_bundle_hash_") as tmp:
        os.chdir(tmp)
        try:
            execution_dir = Path(".qwq_output/data/tasks/20260711--travel-article-demo--cn-sichuan--canary-001")
            source = execution_dir / "sources/su_demo/source.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# 来源\n\n九寨沟底稿。", encoding="utf-8")

            digest = _source_bundle_sha256([source.as_posix()], base_dir=execution_dir)
        finally:
            os.chdir(old_cwd)

    assert digest and digest.startswith("sha256:")


def _seed_post(post_root: Path, ref: str, title: str) -> None:
    build_execution_fixture(TASK)
    register_content_object(TASK, ref, content_type="article", angle="攻略", title=title)
    obj = execution_entity_object_dir(TASK, "地点", "景区", "九寨沟")
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
        execution_id=TASK,
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
        execution_id=TASK,
    )
    rel_a = str(base_manifest["sourceRef"])
    source_abs = execution_root(TASK) / rel_a
    write_writing_pack(
        TASK,
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
    write_prompt(TASK, ref, f"# {title}\n\n提示。")
    write_stage_result(
        TASK,
        "post",
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
        "post",
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
    from content.post.article.draft_io import write_agent_draft

    write_agent_draft(
        TASK,
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
    ensure_execution_layout(TASK)
    ensure_execution_command_layout(TASK, "post")
    post_root = execution_command_root(TASK, "post")
    import shutil

    posts = post_root / "posts"
    if posts.exists():
        shutil.rmtree(posts)
    _seed_post(post_root, "九寨沟", "九寨沟看水攻略")
    materialized = materialize_posts(TASK, "article")
    assert len(materialized) == 1, materialized
    return materialized[0]


def test_materialize_writes_complete_provenance():
    post_dir = _materialize_one()
    prov_path = post_dir / "5.review" / "provenance.json"
    assert prov_path.exists(), "materialize 必须产出 provenance.json"
    # 取代 post_trace.json（精简：单一结构化回查入口）。
    assert not (post_dir / "post_trace.json").exists()
    manifest = read_json(post_dir / "manifest.json")
    assert "articleMarkdownDigest" not in manifest
    assert provenance_issues(post_dir, manifest) == []


def test_provenance_minimal_partitions_present():
    post_dir = _materialize_one()
    data = read_json(post_dir / "5.review" / "provenance.json")
    assert data["schema"] == PROVENANCE_SCHEMA
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
    # sources 长度恒为 1，仅唯一底稿来源单元，无内联原文镜像。
    assert source_refs["schema"] == "quwoquan_data.source_refs"
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
    """Snapshot 只登记唯一底稿来源单元，不内联原文镜像。"""
    ensure_execution_layout(TASK)
    ensure_execution_command_layout(TASK, "post")
    obj = execution_entity_object_dir(TASK, "地点", "景区", "九寨沟")
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
        execution_id=TASK,
    )
    source_md = str(source_manifest["sourceRef"])

    source_refs = build_source_refs_snapshot(
        TASK,
        base_source_ref=source_md,
    )

    assert source_refs["schema"] == "quwoquan_data.source_refs"
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
    task = "20260711--travel-article-repo-path--cn-sichuan--canary-002"
    build_execution_fixture(task)
    ensure_execution_layout(task)
    ensure_execution_command_layout(task, "post")
    register_content_object(task, "repo_ref", content_type="article", angle="攻略", title="repo 路径攻略")
    obj = execution_entity_object_dir(task, "地点", "景区", "九寨沟")
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
        execution_id=task,
    )
    source_ref = str(source_manifest["sourceRef"])
    write_writing_pack(
        task,
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
    write_prompt(task, "repo_ref", "# repo 路径攻略\n\n提示。")
    write_stage_result(task, "post", "review", "repo_ref", {"decision": "approved", "checks": {}})
    # Execution 工作包路径以 `.qwq_output/data/tasks/<executionId>` 为唯一根。
    execution_dir_name = execution_root(task).name
    repo_relative = (
        f".qwq_output/data/tasks/{execution_dir_name}/"
        f"{source_ref}"
    )
    write_stage_result(
        task,
        "post",
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
    from content.post.article.draft_io import write_agent_draft

    source_abs = execution_root(task) / source_ref
    write_agent_draft(
        task,
        "repo_ref",
        "# repo 路径攻略\n\n正文足够长。" * 20,
        model="cursor-agent",
        cited_source_paths=[str(source_abs)],
        covered_facts=[],
        session_trace="test-session",
        agent_run_id="run-repo-relative",
        agent_id="agent-repo-relative",
    )
    materialized = materialize_posts(task, "article")
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
        "schema": PROVENANCE_SCHEMA,
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
