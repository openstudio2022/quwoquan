# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-018
"""全池 fidelity 审计只读 canonical root，并生成可重放 content-addressed baseline。"""
from __future__ import annotations

import hashlib
import json
import sys
import runpy
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def put(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def source(root: Path, *, text: str = "高山 湖泊 海拔 旅行", rights: bool = True) -> str:
    raw = text.encode()
    evidence = put(root / "evidence.txt", raw)
    doc = {
        "schema": "quwoquan_data.publish_source", "sourceId": root.name,
        "sourceUrl": "https://example.com/source", "sourceUseMode": "factual_reference_only",
        "fetchedAt": "2026-09-14T00:00:00Z", "metadata": {}, "assets": [],
        "evidence": [{"path": evidence.name, "sha256": digest(raw), "bytes": len(raw), "kind": "source_snapshot"}],
    }
    if rights:
        doc["sourceAttribution"] = {"rightsBasis": "CC BY 4.0", "commercialAuthorizationStatus": "verified"}
    put(root / "source.json", doc)
    return f"sources/{root.name}/source.json"


def object_package(root: Path, carrier: str, title: str, body: str, *, approved: bool = True,
                   source_text: str = "高山 湖泊 海拔 旅行", intent: str | None = "planning_consultation") -> None:
    source_ref = source(root / "sources/s001", text=source_text)
    final = "page.md" if carrier == "homepage" else "article.md"
    put(root / final, body.encode())
    manifest = {
        "schema": "quwoquan_data.entity_object" if carrier == "homepage" else "quwoquan_data.post_object",
        "entityId" if carrier == "homepage" else "contentId": title,
        "version": 1, "finalContentRef": final, "title": title,
        "contentType": carrier, "sourceRefs": [source_ref], "assets": [],
        "sourceIdentity": {"executionId": "run-1", "sourceRevision": digest(b"rev"),
                           "sourceDigest": digest(source_text.encode()), "entityCatalogDigest": digest(b"catalog"),
                           "identityDigest": digest(title.encode())},
        "payloadDigest": digest(body.encode()), "markdownDialect": "qwq-rich-md",
        "generatorModel": "model-x", "modelBatch": "batch-1", "entityRefs": [title.removesuffix("速览")],
    }
    if carrier == "article" and intent is not None:
        manifest["writingIntent"] = intent
    put(root / "manifest.json", manifest)
    put(root / "content_review.json", {"schema": "quwoquan_data.content_review", "decision": "approved" if approved else "rejected",
        "blockingIssues": [], "dimensions": [{"name": "content", "decision": "approved", "issues": []}]})


def test_content_addressed_baseline_is_deterministic_and_publish_root_is_read_only(tmp_path):
    from governance.content_fidelity_audit import audit_and_write

    publish = tmp_path / "publish"
    object_package(publish / "entities/地点/景区/p0001/雪山/1", "homepage", "雪山", "# 雪山\n\n高山 湖泊 海拔 旅行")
    object_package(publish / "posts/article/导览/p0001/雪山速览/1", "article", "雪山速览", "# 雪山速览\n\n高山 湖泊 海拔 旅行")
    before = {p.relative_to(publish).as_posix(): p.read_bytes() for p in publish.rglob("*") if p.is_file()}
    first = audit_and_write(publish_root=publish, output_root=tmp_path / "out-a", max_objects=100, max_file_bytes=10000)
    second = audit_and_write(publish_root=publish, output_root=tmp_path / "out-b", max_objects=100, max_file_bytes=10000)
    assert first["baselineDigest"] == second["baselineDigest"]
    assert Path(first["manifestPath"]).name == first["baselineDigest"].removeprefix("sha256:") + ".json"
    manifest = json.loads(Path(first["manifestPath"]).read_text())
    assert manifest["baselineDigest"] == first["baselineDigest"]
    assert manifest["counts"]["objects"] == 2
    assert {row["carrier"] for row in manifest["objects"]} == {"homepage", "article"}
    assert all(set(row["digests"]) == {"object", "version", "payload", "source", "review"} for row in manifest["objects"])
    assert manifest["duplicates"]["homepageArticleSameEntity"][0]["textSimilarity"] >= 0.8
    assert before == {p.relative_to(publish).as_posix(): p.read_bytes() for p in publish.rglob("*") if p.is_file()}


def test_typed_issues_metrics_and_false_positive_are_mechanical(tmp_path):
    from governance.content_fidelity_audit import scan_pool

    publish = tmp_path / "publish"
    root = publish / "posts/article/导览/p0001/坏样本/1"
    object_package(root, "article", "坏样本", "# 坏样本\n\n一句话", source_text="| 项目 | 值 |\n|---|---|\n高山 湖泊 海拔 旅行", intent=None)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["sourceRefs"].append("sources/missing/source.json")
    put(root / "manifest.json", manifest)
    result = scan_pool(publish_root=publish, max_objects=10, max_file_bytes=10000)
    codes = {issue["code"] for issue in result["issues"]}
    assert {"source_incomplete", "review_false_positive"} <= codes
    assert {"semantic_fidelity_loss", "table_or_reference_loss", "article_no_independent_intent"}.isdisjoint(codes)
    reasons = {reason for row in result["semanticReviewQueue"] for reason in row["reasons"]}
    assert {"semantic_fidelity_candidate", "intent_contract_missing"} <= reasons
    for metric in result["metrics"].values():
        assert metric["denominator"] >= metric["numerator"] >= 0
        assert metric["rate"] is None or 0 <= metric["rate"] <= 1
    assert result["riskLayers"]["high"]


def test_duplicate_evidence_and_carrier_media_rights_gaps_are_reported(tmp_path):
    from governance.content_fidelity_audit import scan_pool

    publish = tmp_path / "publish"
    a = publish / "posts/image/风景/p0001/一/1"
    b = publish / "posts/video/风景/p0001/二/1"
    for root, carrier in ((a, "article"), (b, "video")):
        object_package(root, carrier, root.parent.name, "# 标题\n\n高山 湖泊 海拔 旅行")
        manifest = json.loads((root / "manifest.json").read_text())
        manifest["assets"] = [{"assetId": "missing", "path": "media/missing.jpg", "sourceRefs": []}]
        put(root / "manifest.json", manifest)
    result = scan_pool(publish_root=publish, max_objects=10, max_file_bytes=10000)
    codes = {issue["code"] for issue in result["issues"]}
    assert {"carrier_mismatch", "media_loss", "rights_gap"} <= codes
    assert result["duplicates"]["snapshotOrExcerpt"]


def test_limits_fail_closed_and_output_is_create_once(tmp_path):
    from governance.content_fidelity_audit import AuditError, audit_and_write

    publish = tmp_path / "publish"
    object_package(publish / "entities/地点/景区/p0001/雪山/1", "homepage", "雪山", "# 雪山\n\n正文")
    with pytest.raises(AuditError, match="OBJECT_BOUND_EXCEEDED"):
        audit_and_write(publish_root=publish, output_root=tmp_path / "out", max_objects=0, max_file_bytes=1000)
    result = audit_and_write(publish_root=publish, output_root=tmp_path / "out", max_objects=10, max_file_bytes=1000)
    with pytest.raises(FileExistsError):
        audit_and_write(publish_root=publish, output_root=tmp_path / "out", max_objects=10, max_file_bytes=1000)
    assert Path(result["manifestPath"]).is_file()


def test_cli_facade_dispatches_audit_and_prints_json(monkeypatch, capsys):
    import governance.content_fidelity_audit as audit

    observed = {}
    def fake_audit_and_write(**kwargs):
        observed.update(kwargs)
        return {"schema": audit.SCHEMA, "baselineDigest": "sha256:" + "1" * 64,
                "manifestPath": "/out/baseline.json", "counts": {"objects": 2}, "riskLayers": {}}

    monkeypatch.setattr(audit, "audit_and_write", fake_audit_and_write)
    monkeypatch.setattr(sys, "argv", ["qwq-data", "governance", "content-fidelity-audit",
        "--publish-root", "p", "--output-root", "o", "--max-objects", "2", "--max-file-bytes", "10"])
    runpy.run_path(str(SCRIPTS / "cli.py"), run_name="__main__")
    output = json.loads(capsys.readouterr().out)
    assert output["baselineDigest"] == "sha256:" + "1" * 64
    assert observed == {"publish_root": Path("p"), "output_root": Path("o"), "max_objects": 2, "max_file_bytes": 10}


def legacy_source(root: Path, *, coverage: str, method: str, scope: str, html: str) -> str:
    raw = html.encode()
    put(root / "evidence.raw", raw)
    put(root / "source.json", {"schema": "quwoquan_data.publish_source", "sourceId": root.name,
        "sourceUrl": "https://zh.wikipedia.org/wiki/雪山", "sourceUseMode": "factual_reference_only",
        "fetchedAt": "2026-09-14", "metadata": {}, "assets": [],
        "evidence": [{"id": "excerpt", "path": "evidence.raw", "sha256": digest(raw), "bytes": len(raw), "kind": "source_excerpt"}],
        "sourceWork": {"capture": {"coverage": coverage, "method": method, "scope": scope}}})
    return f"sources/{root.name}/source.json"


def test_partial_capture_separates_integrity_from_semantic_assessment(tmp_path):
    from governance.content_fidelity_audit import scan_pool
    root = tmp_path / "publish/entities/地点/中国/景区/p0001/雪山/1"
    object_package(root, "homepage", "雪山", "# 雪山\n\n很短")
    ref = legacy_source(root / "sources/legacy", coverage="partial", method="host_webfetch_excerpt",
                        scope="宿主正文摘录，未取原HTML/revision/媒体", html="<table><tr><td>高山湖泊海拔旅行资料</td></tr></table><ref>来源</ref>")
    manifest = json.loads((root / "manifest.json").read_text()); manifest["sourceRefs"] = [ref]
    manifest["sourceAttribution"] = {"sourcePostUrl": "https://zh.wikipedia.org/wiki/雪山", "rightsBasis": "CC BY-SA 4.0"}
    put(root / "manifest.json", manifest)
    result = scan_pool(publish_root=tmp_path / "publish", max_objects=10, max_file_bytes=10000)
    codes = {i["code"] for i in result["issues"]}
    assert "source_incomplete" in codes
    assert "semantic_fidelity_loss" not in codes and "table_or_reference_loss" not in codes
    reasons = {reason for row in result["semanticReviewQueue"] for reason in row["reasons"]}
    assert {"semantic_fidelity_candidate", "table_or_reference_candidate"} <= reasons
    assert result["objects"][0]["coverage"]["semanticAssessment"] == "semantic_review_required"


def test_manifest_attribution_covers_legacy_source_without_embedded_rights(tmp_path):
    from governance.content_fidelity_audit import scan_pool
    root = tmp_path / "publish/entities/地点/中国/景区/p0001/雪山/1"
    object_package(root, "homepage", "雪山", "# 雪山\n\n正文")
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["sourceAttribution"] = {"sourcePostUrl": "https://example.com/source", "rightsBasis": "CC BY 4.0"}
    put(root / "manifest.json", manifest)
    source_doc = json.loads((root / "sources/s001/source.json").read_text()); source_doc.pop("sourceAttribution")
    put(root / "sources/s001/source.json", source_doc)
    result = scan_pool(publish_root=tmp_path / "publish", max_objects=10, max_file_bytes=10000)
    assert "rights_gap" not in {i["code"] for i in result["issues"]}


def test_entity_ref_normalization_and_missing_intent_only_queue_review(tmp_path):
    from governance.content_fidelity_audit import scan_pool
    publish = tmp_path / "publish"
    home = publish / "entities/地点/中国/景区/p0001/雪山/1"
    article = publish / "posts/article/导览/p0001/雪山攻略/1"
    object_package(home, "homepage", "雪山", "# 雪山\n\n高山湖泊路线")
    hm = json.loads((home / "manifest.json").read_text()); hm["entityRef"] = "/entity/travel/cn/snow-mountain"; put(home / "manifest.json", hm)
    object_package(article, "article", "完全不同标题", "# 完全不同\n\n另一种写法", intent=None)
    am = json.loads((article / "manifest.json").read_text()); am["entityRefs"] = ["/ENTITY/travel/cn/snow-mountain/"]
    am["publishAngle"] = "导览"; am["experienceClaimMode"] = "editorial_synthesis"; am.pop("modelBatch")
    put(article / "manifest.json", am)
    result = scan_pool(publish_root=publish, max_objects=10, max_file_bytes=10000)
    assert result["duplicates"]["homepageArticleSameEntity"]
    article_row = next(r for r in result["objects"] if r["carrier"] == "article")
    assert article_row["generation"]["modelBatch"] == "unknown"
    assert article_row["generation"]["executionId"] == "run-1"
    assert "article_no_independent_intent" not in article_row["issueCodes"]
    assert any(f["code"] == "intent_contract_missing" for f in result["mechanicalFindings"])
    assert any("intent_contract_missing" in q["reasons"] for q in result["semanticReviewQueue"])


def test_review_scope_discovers_grok_models_stratifies_and_preserves_reasons(tmp_path):
    from governance.content_fidelity_audit import scan_pool

    publish = tmp_path / "publish"
    grok = publish / "posts/article/历史/p0001/Grok文章/1"
    object_package(grok, "article", "Grok文章", "# Grok文章\n\n高山 湖泊 海拔 旅行")
    manifest = json.loads((grok / "manifest.json").read_text()); manifest["generatorModel"] = "gRoK-next"; manifest["createdAt"] = "2026-09-15T00:00:00Z"; put(grok / "manifest.json", manifest)
    other = publish / "posts/video/风光/p0001/样本/1"
    object_package(other, "video", "样本", "# 样本\n\n高山 湖泊 海拔 旅行")
    result = scan_pool(publish_root=publish, max_objects=10, max_file_bytes=10000)
    assert result["scanPolicy"]["grokModelMatcher"]["discoveredMatchedValues"] == ["gRoK-next"]
    grok_item = next(q for q in result["semanticReviewQueue"] if q["objectRef"] == grok.relative_to(publish).as_posix())
    assert "planned_full_grok_article_review" in grok_item["reasons"]
    assert result["reviewScope"]["strata"]
    assert all(s["selectedRefs"] for s in result["reviewScope"]["strata"])
    assert len({q["objectRef"] for q in result["semanticReviewQueue"]}) == len(result["semanticReviewQueue"])


def test_manifest_membership_or_digest_drift_fails_closed(tmp_path, monkeypatch):
    import governance.content_fidelity_audit as audit

    publish = tmp_path / "publish"
    root = publish / "entities/地点/景区/p0001/雪山/1"
    object_package(root, "homepage", "雪山", "# 雪山\n\n正文")
    original = audit._manifest_snapshot
    calls = 0
    def drifting(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        if calls == 2:
            result[next(iter(result))]["sha256"] = "sha256:" + "f" * 64
        return result
    monkeypatch.setattr(audit, "_manifest_snapshot", drifting)
    with pytest.raises(audit.AuditError, match="PUBLISH_ROOT_DRIFT"):
        audit.scan_pool(publish_root=publish, max_objects=10, max_file_bytes=10000)
