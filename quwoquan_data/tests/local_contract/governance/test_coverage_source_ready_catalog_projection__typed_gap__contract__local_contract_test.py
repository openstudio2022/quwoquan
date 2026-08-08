from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest


_DIGEST = "sha256:" + "1" * 64
_REVISION = "sha256:" + "2" * 64
_CATALOG = "sha256:" + "3" * 64


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _row(*, name: str = "西湖", district: str = "西湖区") -> dict[str, object]:
    return {
        "schema": "quwoquan_data.source_ready_candidate",
        "identityKey": f"name_location:{name}|浙江省|杭州市|{district}",
        "candidate": {
            "name": name,
            "province": "浙江省",
            "city": "杭州市",
            "district": district,
        },
        "attemptedSources": ["wikipedia"],
        "qualified": True,
        "evidence": {
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "canonicalUrl": "https://zh.wikipedia.org/wiki/" + name,
            "resolvedTitle": name,
            "matchConfidence": 0.95,
        },
        "selection": {
            "provinceRank": 1,
            "coverageCell": {
                "city": "杭州市",
                "district": district,
                "entityType": "地点/景区",
            },
        },
        "qualifiedAt": "2026-08-08T00:00:00Z",
    }


def _run(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    run_dir = tmp_path / "source-ready-zhejiang"
    run_dir.mkdir()
    source_document = {
        "algorithm": "sha256",
        "digest": _DIGEST,
        "inputs": ["test-source"],
    }
    manifest = {
        "schema": "quwoquan_data.source_readiness_manifest",
        "runId": "source-ready-zhejiang",
        "provinces": ["浙江省"],
        "candidateFiles": [],
        "includeMasterList": True,
        "exhaustInput": True,
        "sources": ["wikipedia", "baidu_baike", "toutiao_baike"],
        "minimumPerProvince": 1,
        "inputDigest": "sha256:" + "4" * 64,
        "sourceDigest": source_document,
    }
    ready = run_dir / "source_ready.ndjson"
    inconclusive = run_dir / "source_inconclusive.ndjson"
    frozen = run_dir / "frozen_targets.ndjson"
    serialized = "".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in rows
    )
    ready.write_text(serialized, encoding="utf-8")
    inconclusive.write_text("", encoding="utf-8")
    frozen.write_text(serialized, encoding="utf-8")
    report = {
        "schema": "quwoquan_data.source_readiness_report",
        "runId": "source-ready-zhejiang",
        "generatedAt": "2026-08-08T00:01:00Z",
        "sourceDigest": source_document,
        "inputDigest": manifest["inputDigest"],
        "sources": manifest["sources"],
        "minimumPerProvince": 1,
        "exhaustInput": True,
        "inputExhausted": True,
        "inputUniqueByProvince": {"浙江省": len(rows)},
        "qualifiedByProvince": {"浙江省": len(rows)},
        "frozenByProvince": {"浙江省": len(rows)},
        "coveredCellsByProvince": {"浙江省": len(rows)},
        "processed": len(rows),
        "belowMinimum": {},
        "decision": "GO",
        "outputs": {
            "ready": str(ready),
            "inconclusive": str(inconclusive),
            "frozenTargets": str(frozen),
        },
    }
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "report.json", report)
    return run_dir


def _project(run_dir: Path):
    from governance.coverage.coverage_source_ready_catalog_projection import (
        project_coverage_source_ready_catalog_inputs,
    )

    return project_coverage_source_ready_catalog_inputs(
        run_dir=run_dir,
        source_revision=_REVISION,
        source_digest=_DIGEST,
        entity_catalog_digest=_CATALOG,
    )


def test_projection_binds_physical_coverage_bytes_and_preserves_typed_gaps(
    tmp_path,
):
    run_dir = _run(tmp_path, [_row()])

    first = _project(run_dir)
    second = _project(run_dir)

    assert first == second
    assert first["counts"] == {
        "plannedEntityCount": 1,
        "homepage": {"plannedCount": 1, "readyCount": 0, "mediaMissingCount": 1},
        "article": {"plannedCount": 1, "readyCount": 0, "mediaMissingCount": 1},
    }
    assert first["coverageReceiptStatus"] == "missing"
    assert first["homepageCatalogBuilderInputs"] == []
    assert first["articleCatalogBuilderInputs"] == []
    candidate = first["plannedCandidates"][0]
    assert candidate["coverageEntityIdentity"].startswith("name_location:西湖|")
    assert candidate["source"] == {
        "sourceKind": "wikipedia",
        "extractor": "wikipedia_api",
        "sourceUrl": "https://zh.wikipedia.org/wiki/西湖",
        "observedAt": "2026-08-08T00:00:00Z",
    }
    assert "bodyContentDigest" in candidate["homepage"]["missingEvidence"]
    assert "heroAssetEvidence" in candidate["homepage"]["missingEvidence"]
    assert "articleCoverEvidence" in candidate["article"]["missingEvidence"]
    assert "articleBodyImageEvidence" in candidate["article"]["missingEvidence"]
    assert "contentDigest" not in candidate["source"]
    for binding in first["coverageBindings"].values():
        assert binding["fileSha256"].startswith("sha256:")


def test_projection_rejects_duplicate_entity_identity(tmp_path):
    from governance.coverage.coverage_source_ready_catalog_projection import (
        CoverageSourceReadyProjectionError,
    )

    row = _row()
    with pytest.raises(CoverageSourceReadyProjectionError) as captured:
        _project(_run(tmp_path, [row, dict(row)]))
    assert captured.value.code == "DATA.SOURCE.INVALID_EVIDENCE"
    assert "duplicate entity identity" in str(captured.value)


def test_projection_rejects_source_digest_and_output_file_drift(tmp_path):
    from governance.coverage.coverage_source_ready_catalog_projection import (
        CoverageSourceReadyProjectionError,
    )

    run_dir = _run(tmp_path, [_row()])
    report_path = run_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["sourceDigest"]["digest"] = "sha256:" + "9" * 64
    _write_json(report_path, report)
    with pytest.raises(CoverageSourceReadyProjectionError) as captured:
        _project(run_dir)
    assert captured.value.code == "DATA.SOURCE.INVALID_EVIDENCE"
    assert "sourceDigest drift" in str(captured.value)


def test_catalog_builder_requirement_raises_typed_shortfall(tmp_path):
    from governance.coverage.coverage_source_ready_catalog_projection import (
        CoverageSourceReadyProjectionError,
        require_catalog_builder_inputs,
    )

    projection = _project(_run(tmp_path, [_row()]))
    with pytest.raises(CoverageSourceReadyProjectionError) as captured:
        require_catalog_builder_inputs(projection)
    assert captured.value.code == "DATA.SOURCE.POOL_SHORTFALL"


def test_zhejiang_master_list_keeps_922_poi_leaves_distinct_from_admin_rows():
    from governance.coverage.source_readiness_candidates import _master_candidates

    counts = Counter(
        str(row.get("source") or "")
        for row in _master_candidates(["浙江省"])
    )
    assert counts["master_list"] == 922
    assert counts["admin_region_catalog"] == 102

