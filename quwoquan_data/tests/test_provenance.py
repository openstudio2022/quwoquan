"""结构化出处 provenance.json 红绿测试 ——「精简中间产物 + 统一回查入口 + 完整性门」。

覆盖：
- materialize 端到端产出最小 provenance.json，且 completeness 门全绿。
- provenance 只保留 final / agentInput / originalSources / gateResults / citedSourcePaths。
- completeness 门：缺文件→missing；generator≠agent→报；originalSources 空→报；decision≠approved→报。
- issues 强制门：无文件→报；digest 不一致→报；cited 源越出 originalSources→报。

可直接运行：python3 quwoquan_data/tests/test_provenance.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

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
from produce.materialize import materialize_posts  # noqa: E402

TASK = "出处记录_gwt"
BATCH = "pilot"


def _seed_post(produce_root: Path, ref: str, title: str) -> None:
    review_dir = produce_root / "results" / "review"
    compose_dir = produce_root / "results" / "compose"
    review_dir.mkdir(parents=True, exist_ok=True)
    compose_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        review_dir / f"{ref}.json",
        {
            "ref": ref,
            "payload": {
                "decision": "approved",
                "qualityScore": 92.0,
                "issues": [],
                "checks": {
                    "routeCoverage": {"passed": True, "issues": []},
                    "travelogueDensity": {"passed": True, "issues": []},
                },
            },
        },
    )
    write_json(
        compose_dir / f"{ref}.json",
        {
            "payload": {
                "generator": "agent",
                "generatorModel": "cursor-agent",
                "articleMarkdown": f"# {title}\n\n正文：{ref} 的真实叙事展开，足够长以通过字数门校验。" * 12,
                "title": title,
                "publishTitle": title,
                "carrier": "article",
                "entityRefs": [],
                "tagRefs": ["Topic/旅行", "Format/内容角度/攻略"],
                "assets": [],
                "sourcePaths": ["sources/a.md", "sources/b.md"],
                "sourceUrls": ["https://example.com/a", "https://example.com/b"],
                "citedSourceRefs": ["sources/a.md"],
                "storySpine": {"sourceQuality": [{"sourceId": "a", "score": 0.9}]},
                "relatedSearchPlan": {"queries": ["开放时间"]},
                "evidenceBundle": {"routeNodes": [{"entityName": "九寨沟"}]},
            }
        },
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
    prov_path = post_dir / "provenance.json"
    assert prov_path.exists(), "materialize 必须产出 provenance.json"
    # 取代 produce_trace.json（精简：单一结构化回查入口）。
    assert not (post_dir / "produce_trace.json").exists()
    manifest = read_json(post_dir / "manifest.json")
    assert provenance_issues(post_dir, manifest) == []


def test_provenance_minimal_partitions_present():
    post_dir = _materialize_one()
    data = read_json(post_dir / "provenance.json")
    assert data["schemaVersion"] == PROVENANCE_SCHEMA
    for section in ("final", "agentInput", "originalSources", "gateResults", "citedSourcePaths"):
        assert section in data, section
    for dropped in ("evidenceSources", "intermediate"):
        assert dropped not in data
    assert data["final"]["generator"] == "agent"
    assert data["originalSources"], "原始数据源必须一一记录"
    assert data["gateResults"]["decision"] == "approved"
    assert "routeCoverage" in data["gateResults"]["checks"]


def test_missing_file_flagged():
    empty = Path(tempfile.mkdtemp())
    issues = provenance_issues(empty, {"articleMarkdownDigest": "x"})
    assert any("missing provenance.json" in i for i in issues)


def _write_provenance(post_dir: Path, *, digest: str, generator: str, originals, cited, decision):
    payload = {
        "schemaVersion": PROVENANCE_SCHEMA,
        "ref": "r",
        "final": {"generator": generator, "articleDigest": digest},
        "agentInput": {"title": "t"},
        "originalSources": originals,
        "gateResults": {"decision": decision, "checks": {}},
        "citedSourcePaths": cited,
    }
    write_json(post_dir / "provenance.json", payload)


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
    assert any("articleDigest != manifest" in i for i in issues)
    assert any("cited source not in originalSources" in i for i in issues)


def test_build_provenance_uses_meta_over_compose():
    data = build_provenance(
        "ref1",
        writing_pack={"title": "T", "styleFamily": "实用攻略风", "mustIncludeFacts": ["门票"]},
        draft_meta={"generator": "agent", "model": "cursor-agent", "styleFamily": "旅途随笔风", "openingStrategy": "scene_immersion"},
        review_payload={"decision": "approved", "checks": {}},
        compose_payload={"sourcePaths": ["sources/a.md"], "generator": "agent"},
        manifest={"publishTitle": "T", "publishSeq": 1, "articleMarkdownDigest": "d"},
    )
    # draft_meta 的 styleFamily 优先于 writing_pack。
    assert data["final"]["styleFamily"] == "旅途随笔风"
    assert data["final"]["openingStrategy"] == "scene_immersion"
    assert "mustIncludeFacts" not in data["agentInput"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"provenance tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
