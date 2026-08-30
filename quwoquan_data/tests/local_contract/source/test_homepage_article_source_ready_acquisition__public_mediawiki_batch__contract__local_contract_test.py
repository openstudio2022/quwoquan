"""场景组：source-ready 批处理生命周期与 CLI 入口。

homepage/article source-ready acquisition 契约测试（public mediawiki）。

从 test_homepage_article_source_ready_acquisition__public_mediawiki__contract__local_contract_test.py
按场景拆出：seed selection 合法性、coverage snapshot 字节绑定、可重放物理批、
preflight seed 漂移拒绝、typed shortfall、carrier 选择性执行、有界并发与
CLI 身份冻结；测试逐字搬移。共享常量与构造 helper 见
tests/support/homepage_article_source_ready_acquisition_fixture.py。
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

import pytest
from content.source.research.homepage_article_source_ready_acquisition import (
    HomepageArticleSourceReadyAcquisitionError,
    acquire_homepage_article_source_ready_batch,
)
from content.source.research.homepage_article_source_ready_evidence import (
    canonical_digest,
    write_create_once_json,
)
from content.source.research.homepage_article_seed_selection import (
    HomepageArticleSeedSelectionError,
    load_homepage_article_seed_selection,
)
from content.source.research.homepage_article_source_ready_mediawiki import (
    AcquiredSourceReadyCandidate,
    MediaWikiSourceReadyRejected,
)
from support.homepage_article_source_ready_acquisition_fixture import (
    CAPTURED_AT,
    IDENTITY,
    _fake_acquired,
    _planned,
    _projection,
    _seed_selection,
    _sha,
)


def test_seed_selection_rejects_legacy_identity_and_receipt_fields(
    tmp_path: Path,
) -> None:
    source = _seed_selection(
        tmp_path / "valid-seed-selection.json", [_planned("测试实体")], homepage_count=1
    )
    document = json.loads(source.read_text())
    document["seeds"][0]["sourceDigest"] = IDENTITY["sourceDigest"]
    stable = {key: value for key, value in document.items() if key != "selectionDigest"}
    document["selectionDigest"] = canonical_digest(stable)
    invalid = tmp_path / "legacy-bound-seed-selection.json"
    write_create_once_json(invalid, document)

    with pytest.raises(HomepageArticleSeedSelectionError):
        load_homepage_article_seed_selection(invalid)


def test_coverage_snapshot_preserves_absolute_report_as_bound_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    source_run = tmp_path / "canonical-run"
    source_run.mkdir()
    for name in mod._COVERAGE_FILES:
        (source_run / name).write_bytes(f"canonical:{name}".encode())
    (source_run / "source_inconclusive.ndjson").write_bytes(b"")
    projection = {
        "schema": "quwoquan_data.coverage_source_ready_catalog_projection",
        **IDENTITY,
        "plannedCandidates": [_planned("首页实体"), _planned("文章实体")],
        "projectionDigest": _sha(b"projection"),
    }
    observed_runs: list[Path] = []

    def project(*, run_dir: Path, **_: object) -> dict[str, object]:
        observed_runs.append(run_dir)
        assert run_dir == source_run
        return projection

    monkeypatch.setattr(
        mod,
        "project_coverage_source_ready_catalog_inputs",
        project,
    )
    snapshot_root = tmp_path / "snapshot"

    frozen = mod._copy_coverage_run(
        source_run,
        evidence_root=snapshot_root,
        identity=IDENTITY,
    )

    assert frozen == projection
    assert observed_runs == [source_run, source_run]
    for name in mod._COVERAGE_FILES:
        assert (snapshot_root / name).read_bytes() == (source_run / name).read_bytes()
    assert json.loads((snapshot_root / "coverage-projection.json").read_text()) == projection


def test_acquisition_writes_replayable_physical_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned("首页实体"), _planned("文章实体")]
    preflight_projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"preflight-projection"),
    }

    def copy_run(
        _run: Path,
        *,
        evidence_root: Path,
        identity: object,
        expected_projection: object = None,
    ) -> dict[str, object]:
        return _projection(evidence_root, rows)

    def acquire(row: dict[str, object], *, carrier: str, **_: object) -> AcquiredSourceReadyCandidate:
        return _fake_acquired(carrier, str(row["candidateName"]))

    monkeypatch.setattr(mod, "_copy_coverage_run", copy_run)
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: preflight_projection
    )
    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", acquire)
    monkeypatch.setattr(
        mod,
        "acquire_article_site_source_ready_candidate",
        lambda row, **kwargs: acquire(row, carrier="article", **kwargs),
    )
    arguments = {
        "coverage_run_dir": tmp_path / "coverage",
        "output_root": tmp_path / "output",
        "source_set_id": "m100-public-mediawiki",
        "target_scale": "M100",
        "source_revision": IDENTITY["sourceRevision"],
        "source_digest": IDENTITY["sourceDigest"],
        "entity_catalog_digest": IDENTITY["entityCatalogDigest"],
        "captured_at": CAPTURED_AT,
        "homepage_count": 1,
        "article_count": 1,
        "seed_selection": _seed_selection(
            tmp_path / "seed-selection.json",
            rows,
            homepage_count=1,
            seed_origin="current_coverage",
        ),
    }
    first = acquire_homepage_article_source_ready_batch(**arguments)
    replay = acquire_homepage_article_source_ready_batch(**arguments)

    assert replay == first
    assert first["counts"] == {"homepage": 1, "article": 1}
    assert Path(first["sourceReadyManifest"]).is_file()
    evidence_root = Path(first["evidenceRoot"])
    report = json.loads((evidence_root / first["reportRef"]).read_text())
    assert report["counts"]["attempted"] == 2
    assert report["counts"]["rejected"] == 0
    assert report["rejections"] == []
    batch = json.loads(Path(first["sourceReadyManifest"]).read_text())
    for binding in batch["candidateCapsules"]:
        capsule = json.loads((evidence_root / binding["ref"]).read_text())
        assert capsule["provenance"]["seedOrigin"] == "current_coverage"
        assert "historicalComparison" not in capsule["provenance"]


def test_acquisition_rejects_seed_drift_before_output_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned("首页实体"), _planned("文章实体")]
    drifted = [dict(row) for row in rows]
    drifted[0] = {
        **drifted[0],
        "coverageRecordDigest": _sha(b"changed-coverage-record"),
    }
    monkeypatch.setattr(
        mod,
        "_project_coverage_run",
        lambda _run, *, identity: {
            "plannedCandidates": drifted,
            "projectionDigest": _sha(b"drifted-projection"),
        },
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda *_args, **_kwargs: pytest.fail("output write started before preflight"),
    )
    monkeypatch.setattr(
        mod,
        "acquire_mediawiki_source_ready_candidate",
        lambda *_args, **_kwargs: pytest.fail("network acquisition started before preflight"),
    )

    with pytest.raises(
        HomepageArticleSourceReadyAcquisitionError,
        match="DATA.SOURCE.INVALID_EVIDENCE",
    ):
        acquire_homepage_article_source_ready_batch(
            coverage_run_dir=tmp_path / "coverage",
            output_root=tmp_path / "output",
            source_set_id="m100-preflight-drift",
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
            homepage_count=1,
            article_count=1,
            seed_selection=_seed_selection(
                tmp_path / "seed-selection.json",
                rows,
                homepage_count=1,
                seed_origin="current_coverage",
            ),
        )
    assert not (tmp_path / "output").exists()


def test_acquisition_reports_typed_shortfall_without_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned("首页实体"), _planned("文章实体")]
    preflight_projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"preflight-projection"),
    }
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: preflight_projection
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda _run, *, evidence_root, identity, expected_projection=None: _projection(evidence_root, rows),
    )

    def acquire(row: dict[str, object], *, carrier: str, **_: object) -> AcquiredSourceReadyCandidate:
        if carrier == "article":
            raise MediaWikiSourceReadyRejected("no illustrated source page")
        return _fake_acquired(carrier, str(row["candidateName"]))

    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", acquire)
    monkeypatch.setattr(
        mod,
        "acquire_article_site_source_ready_candidate",
        lambda row, **kwargs: acquire(row, carrier="article", **kwargs),
    )
    with pytest.raises(HomepageArticleSourceReadyAcquisitionError) as captured:
        acquire_homepage_article_source_ready_batch(
            coverage_run_dir=tmp_path / "coverage",
            output_root=tmp_path / "output",
            source_set_id="m100-shortfall",
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
            homepage_count=1,
            article_count=1,
            seed_selection=_seed_selection(
                tmp_path / "seed-selection.json", rows, homepage_count=1
            ),
        )
    assert captured.value.code == "DATA.SOURCE.POOL_SHORTFALL"
    assert not list((tmp_path / "output").rglob("batches/*.json"))


def test_acquisition_can_run_article_carrier_without_waiting_for_homepage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned("首页实体"), _planned("文章实体")]
    projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"carrier-selective-projection"),
    }
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: projection
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda _run, *, evidence_root, identity, expected_projection=None: _projection(
            evidence_root, rows
        ),
    )

    acquired_carriers: list[str] = []

    def acquire(
        row: dict[str, object], *, carrier: str, **_: object
    ) -> AcquiredSourceReadyCandidate:
        acquired_carriers.append(carrier)
        return _fake_acquired(carrier, str(row["candidateName"]))

    monkeypatch.setattr(
        mod,
        "acquire_mediawiki_source_ready_candidate",
        lambda *_args, **_kwargs: pytest.fail("inactive homepage carrier was called"),
    )
    monkeypatch.setattr(
        mod,
        "acquire_article_site_source_ready_candidate",
        lambda row, **kwargs: acquire(row, carrier="article", **kwargs),
    )
    result = acquire_homepage_article_source_ready_batch(
        coverage_run_dir=tmp_path / "coverage",
        output_root=tmp_path / "output",
        source_set_id="m100-article-only",
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
        homepage_count=0,
        article_count=1,
        seed_selection=_seed_selection(
            tmp_path / "seed-selection.json", rows, homepage_count=1
        ),
    )

    assert acquired_carriers == ["article"]
    assert result["counts"] == {"homepage": 0, "article": 1}


def test_acquisition_starts_exact_pending_workload_and_isolates_rejections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned(f"首页实体{index}") for index in range(3)]
    projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"bounded-concurrency-projection"),
    }
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: projection
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda _run, *, evidence_root, identity, expected_projection=None: _projection(
            evidence_root, rows
        ),
    )

    lock = threading.Lock()
    active = 0
    maximum_active = 0

    def acquire(
        row: dict[str, object], *, carrier: str, **_: object
    ) -> AcquiredSourceReadyCandidate:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            time.sleep(0.02)
            if row["candidateName"] == "首页实体2":
                raise RuntimeError("last candidate crashed")
            return _fake_acquired(carrier, str(row["candidateName"]))
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", acquire)
    result = acquire_homepage_article_source_ready_batch(
        coverage_run_dir=tmp_path / "coverage",
        output_root=tmp_path / "output",
        source_set_id="m100-bounded-concurrency",
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
        homepage_count=2,
        article_count=0,
        seed_selection=_seed_selection(
            tmp_path / "seed-selection.json", rows, homepage_count=3
        ),
    )

    assert maximum_active == len(rows)
    assert result["counts"] == {"homepage": 2, "article": 0}
    report = json.loads(
        (Path(result["evidenceRoot"]) / result["reportRef"]).read_text()
    )
    assert report["counts"]["attempted"] == 3
    assert report["counts"]["rejected"] == 1
    assert report["rejections"][0]["reason"].startswith(
        "DATA.SOURCE.ACQUISITION_FAILED: RuntimeError:"
    )


def test_acquisition_cli_freezes_exact_identity_and_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import content.source.research.handler_cli as handler

    captured: dict[str, object] = {}

    def acquire(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "schema": "quwoquan_data.homepage_article_source_ready_acquisition_result",
            "counts": {"homepage": 180, "article": 180},
        }

    monkeypatch.setattr(handler, "acquire_homepage_article_source_ready_batch", acquire)
    parser = argparse.ArgumentParser()
    handler.register_parser(parser.add_subparsers(dest="command", required=True))
    arguments = parser.parse_args(
        [
            "source-pool",
            "acquire-homepage-article",
            "--coverage-run-dir",
            str(tmp_path / "coverage"),
            "--source-set-id",
            "m100-public-mediawiki",
            "--target-scale",
            "M100",
            "--source-revision",
            IDENTITY["sourceRevision"],
            "--source-digest",
            IDENTITY["sourceDigest"],
            "--entity-catalog-digest",
            IDENTITY["entityCatalogDigest"],
            "--captured-at",
            CAPTURED_AT,
            "--homepage-count",
            "180",
            "--article-count",
            "180",
            "--seed-selection",
            str(tmp_path / "seed-selection.json"),
            "--output-root",
            str(tmp_path / "output"),
        ]
    )

    arguments.handler(arguments)

    assert captured == {
        "coverage_run_dir": tmp_path / "coverage",
        "output_root": tmp_path / "output",
        "source_set_id": "m100-public-mediawiki",
        "target_scale": "M100",
        "source_revision": IDENTITY["sourceRevision"],
        "source_digest": IDENTITY["sourceDigest"],
        "entity_catalog_digest": IDENTITY["entityCatalogDigest"],
        "captured_at": CAPTURED_AT,
        "homepage_count": 180,
        "article_count": 180,
        "seed_selection": tmp_path / "seed-selection.json",
    }
    assert json.loads(capsys.readouterr().out)["counts"] == {
        "homepage": 180,
        "article": 180,
    }
