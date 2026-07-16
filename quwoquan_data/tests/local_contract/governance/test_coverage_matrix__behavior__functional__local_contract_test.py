from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from governance.coverage.coverage_matrix import (  # noqa: E402
    DISCOVERY_SOURCES,
    ENTITY_TYPES,
    _runtime_root,
    coverage_matrix_status,
    resumable_cells,
    prepare_coverage_matrix,
    record_cell_page,
)


def test_matrix_runtime_root_uses_canonical_data_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))

    assert _runtime_root() == tmp_path / "output" / "data" / "local" / "workspace" / "coverage" / "matrix"


def test_matrix_is_city_sharded_and_resume_preserves_terminal_cells(tmp_path: Path) -> None:
    admin_tree = {
        "浙江省": {
            "杭州市": ["上城区", "西湖区"],
            "宁波市": ["海曙区"],
        }
    }
    report = prepare_coverage_matrix(
        run_id="matrix-r1",
        provinces=["浙江省"],
        sources=list(DISCOVERY_SOURCES),
        admin_tree=admin_tree,
        runtime_root=tmp_path,
        guardrails={"requestBudget": 20000, "maxPagesPerCell": 20},
    )
    assert report["cityCheckpointCount"] == 2
    assert report["cellCount"] == 3 * len(ENTITY_TYPES) * len(DISCOVERY_SOURCES)

    checkpoint_path = tmp_path / "matrix-r1" / "checkpoint_浙江省_杭州市.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "schema/governance/discovery_checkpoint.schema.json"
    )
    Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8"))
    ).validate(checkpoint)
    cell_id = checkpoint["cells"][0]["cellId"]
    record_cell_page(
        checkpoint_path=checkpoint_path,
        cell_id=cell_id,
        raw_rows=[{"name": "西湖"}],
        semantic_admitted_count=1,
        semantic_rejected_count=0,
        dedup_unique_count=0,
        dedup_duplicate_count=1,
        next_cursor=None,
        request_succeeded=True,
        exhausted=True,
        saturation_threshold=0.05,
        saturation_rounds=2,
    )
    intermediate = record_cell_page(
        checkpoint_path=checkpoint_path,
        cell_id=cell_id,
        raw_rows=[],
        semantic_admitted_count=0,
        semantic_rejected_count=0,
        dedup_unique_count=0,
        dedup_duplicate_count=0,
        next_cursor=None,
        request_succeeded=True,
        exhausted=True,
        saturation_threshold=0.05,
        saturation_rounds=2,
    )
    assert intermediate["status"] == "exhausted"
    cell = record_cell_page(
        checkpoint_path=checkpoint_path,
        cell_id=cell_id,
        raw_rows=[],
        semantic_admitted_count=0,
        semantic_rejected_count=0,
        dedup_unique_count=0,
        dedup_duplicate_count=0,
        next_cursor=None,
        request_succeeded=True,
        exhausted=True,
        saturation_threshold=0.05,
        saturation_rounds=2,
    )
    assert cell["status"] == "saturated"
    assert cell["saturationEvidence"]["driverComplete"] is True

    resumed = prepare_coverage_matrix(
        run_id="matrix-r1",
        provinces=["浙江省"],
        sources=list(DISCOVERY_SOURCES),
        admin_tree=admin_tree,
        runtime_root=tmp_path,
        resume=True,
        guardrails={"requestBudget": 20000, "maxPagesPerCell": 20},
    )
    assert resumed["resumedCellCount"] == resumed["cellCount"]
    after = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert next(row for row in after["cells"] if row["cellId"] == cell_id)["status"] == "saturated"
    assert cell_id not in {
        row["cell"]["cellId"]
        for row in resumable_cells(run_dir=tmp_path / "matrix-r1")
    }


def test_failed_or_truncated_page_never_counts_as_empty_or_saturated(tmp_path: Path) -> None:
    prepare_coverage_matrix(
        run_id="matrix-r2",
        provinces=["四川省"],
        sources=["osm_poi"],
        admin_tree={"四川省": {"成都市": ["锦江区"]}},
        runtime_root=tmp_path,
    )
    checkpoint_path = tmp_path / "matrix-r2" / "checkpoint_四川省_成都市.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    failed_id = checkpoint["cells"][0]["cellId"]
    failed = record_cell_page(
        checkpoint_path=checkpoint_path,
        cell_id=failed_id,
        raw_rows=[],
        semantic_admitted_count=0,
        semantic_rejected_count=0,
        dedup_unique_count=0,
        dedup_duplicate_count=0,
        next_cursor=None,
        request_succeeded=False,
        exhausted=True,
        retry_state={"attempt": 3},
    )
    assert failed["status"] == "failed"

    partial_id = checkpoint["cells"][1]["cellId"]
    partial = record_cell_page(
        checkpoint_path=checkpoint_path,
        cell_id=partial_id,
        raw_rows=[],
        semantic_admitted_count=0,
        semantic_rejected_count=0,
        dedup_unique_count=0,
        dedup_duplicate_count=0,
        next_cursor=None,
        request_succeeded=True,
        exhausted=True,
        truncated=True,
    )
    assert partial["status"] == "partial"


def test_resume_rejects_guardrail_drift(tmp_path: Path) -> None:
    kwargs = {
        "run_id": "matrix-guardrails",
        "provinces": ["浙江省"],
        "sources": ["wiki_category"],
        "admin_tree": {"浙江省": {"杭州市": ["西湖区"]}},
        "runtime_root": tmp_path,
    }
    prepare_coverage_matrix(**kwargs, guardrails={"maxPagesPerCell": 20})
    with pytest.raises(ValueError, match="guardrail drift"):
        prepare_coverage_matrix(
            **kwargs,
            resume=True,
            guardrails={"maxPagesPerCell": 21},
        )


def test_page_checkpoint_keeps_typed_counts_cursor_retry_and_hash(tmp_path: Path) -> None:
    prepare_coverage_matrix(
        run_id="matrix-r3",
        provinces=["浙江省"],
        sources=["wikidata_geo"],
        admin_tree={"浙江省": {"杭州市": ["西湖区"]}},
        runtime_root=tmp_path,
    )
    checkpoint_path = tmp_path / "matrix-r3" / "checkpoint_浙江省_杭州市.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    cell_id = checkpoint["cells"][0]["cellId"]
    cell = record_cell_page(
        checkpoint_path=checkpoint_path,
        cell_id=cell_id,
        raw_rows=[
            {
                "name": "西湖",
                "identityRefs": {"qid": "Q123"},
                "sourceCursor": "cursor-1",
            },
            {"name": "Quarry", "identityRefs": {"osmType": "way", "osmId": "9"}},
        ],
        semantic_admitted_count=1,
        semantic_rejected_count=1,
        dedup_unique_count=1,
        dedup_duplicate_count=0,
        semantic_admitted_rows=[
            {"name": "西湖", "identityRefs": {"qid": "Q123"}}
        ],
        semantic_rejections=[
            {"name": "Quarry", "reason": "generic_or_placeholder_name"}
        ],
        dedup_results=[
            {"identityKey": "qid:Q123", "result": "unique"}
        ],
        next_cursor="cursor-2",
        request_succeeded=True,
        exhausted=False,
        attempt=2,
        retry_count=1,
        retry_state={"reason": "rate_limited", "backoffSeconds": 4},
    )
    assert cell["identity"] == {
        "province": "浙江省",
        "city": "杭州市",
        "district": "西湖区",
        "entityType": ENTITY_TYPES[0],
        "source": "wikidata_geo",
    }
    assert cell["sourceState"] == {"cursor": "cursor-2", "page": 1}
    assert cell["counts"] == {
        "raw": 2,
        "semanticAdmitted": 1,
        "semanticRejected": 1,
        "dedupUnique": 1,
        "dedupDuplicate": 0,
    }
    assert cell["attemptState"]["attempt"] == 2
    assert cell["attemptState"]["retryCount"] == 1
    assert cell["lastPageSnapshot"]["sha256"].startswith("sha256:")
    assert cell["lastPageSnapshot"]["rawCount"] == 2
    assert cell["stopReason"] is None
    raw_lines = (
        tmp_path / "matrix-r3" / "raw_浙江省_杭州市.ndjson"
    ).read_text(encoding="utf-8").splitlines()
    envelope = json.loads(raw_lines[0])
    assert envelope["pageSnapshot"]["sha256"] == cell["lastPageSnapshot"]["sha256"]
    assert envelope["sourceCursorBefore"] is None
    assert envelope["sourceCursorAfter"] == "cursor-2"
    candidates = (
        tmp_path / "matrix-r3" / "candidates_浙江省_杭州市.ndjson"
    ).read_text(encoding="utf-8")
    assert '"identityKey": "qid:Q123"' in candidates
    gaps = json.loads(
        (tmp_path / "matrix-r3" / "gaps_浙江省_杭州市.json").read_text(
            encoding="utf-8"
        )
    )
    assert gaps["rejectReasons"] == {"generic_or_placeholder_name": 1}


def test_saturation_requires_driver_completion_empty_pages_and_decay(tmp_path: Path) -> None:
    prepare_coverage_matrix(
        run_id="matrix-r4",
        provinces=["四川省"],
        sources=["wiki_category"],
        admin_tree={"四川省": {"成都市": ["锦江区"]}},
        runtime_root=tmp_path,
    )
    checkpoint_path = tmp_path / "matrix-r4" / "checkpoint_四川省_成都市.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    cell_id = checkpoint["cells"][0]["cellId"]
    first = record_cell_page(
        checkpoint_path=checkpoint_path,
        cell_id=cell_id,
        raw_rows=[{"name": "甲"}],
        semantic_admitted_count=1,
        semantic_rejected_count=0,
        dedup_unique_count=0,
        dedup_duplicate_count=1,
        next_cursor="next",
        request_succeeded=True,
        exhausted=False,
        saturation_threshold=0.05,
        saturation_rounds=2,
        required_empty_pages=2,
    )
    assert first["status"] == "running"
    second = record_cell_page(
        checkpoint_path=checkpoint_path,
        cell_id=cell_id,
        raw_rows=[],
        semantic_admitted_count=0,
        semantic_rejected_count=0,
        dedup_unique_count=0,
        dedup_duplicate_count=0,
        next_cursor="last",
        request_succeeded=True,
        exhausted=False,
        saturation_threshold=0.05,
        saturation_rounds=2,
        required_empty_pages=2,
    )
    assert second["status"] == "running"
    final = record_cell_page(
        checkpoint_path=checkpoint_path,
        cell_id=cell_id,
        raw_rows=[],
        semantic_admitted_count=0,
        semantic_rejected_count=0,
        dedup_unique_count=0,
        dedup_duplicate_count=0,
        next_cursor=None,
        request_succeeded=True,
        exhausted=True,
        saturation_threshold=0.05,
        saturation_rounds=2,
        required_empty_pages=2,
    )
    assert final["status"] == "saturated"
    assert final["stopReason"] == "driver_exhausted_and_decay_saturated"
    assert final["saturationEvidence"]["consecutiveEmptyPages"] == 2
    assert final["saturationEvidence"]["driverComplete"] is True
    status = coverage_matrix_status(run_dir=tmp_path / "matrix-r4")
    assert status["provinces"]["四川省"]["saturated"] is False
    latest = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    for other in latest["cells"][1:]:
        for exhausted in (False, True):
            record_cell_page(
                checkpoint_path=checkpoint_path,
                cell_id=other["cellId"],
                raw_rows=[],
                semantic_admitted_count=0,
                semantic_rejected_count=0,
                dedup_unique_count=0,
                dedup_duplicate_count=0,
                next_cursor=None if exhausted else "next",
                request_succeeded=True,
                exhausted=exhausted,
                saturation_threshold=0.05,
                saturation_rounds=2,
                required_empty_pages=2,
            )
    status = coverage_matrix_status(run_dir=tmp_path / "matrix-r4")
    assert status["provinces"]["四川省"]["saturated"] is True
    assert status["provinces"]["四川省"]["coverage"]["districtTypeCellsCompleted"] == 10
    assert status["provinces"]["四川省"]["coverage"]["sourceDriversCompleted"] == 10
