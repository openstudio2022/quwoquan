"""场景组：source-ready 批的幂等 resume/replay 与 shortfall checkpoint。

homepage/article source-ready acquisition 契约测试（public mediawiki）。

从 test_homepage_article_source_ready_acquisition__public_mediawiki__contract__local_contract_test.py
按场景拆出：已验证 capsule 免网络 resume、同 seed 重复 capsule 确定性跳过、
shortfall 冻结可重放 partial checkpoint、生产者修复后被拒 seed 重试；
测试逐字搬移。共享常量与构造 helper 见
tests/support/homepage_article_source_ready_acquisition_fixture.py。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.source.research.homepage_article_source_ready_acquisition import (
    HomepageArticleSourceReadyAcquisitionError,
    acquire_homepage_article_source_ready_batch,
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


def test_acquisition_resumes_verified_capsules_without_repeating_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned(f"首页恢复实体{index}") for index in range(2)]
    projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"resume-capsules-projection"),
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
    network_calls = 0

    def acquire(
        row: dict[str, object], *, carrier: str, **_: object
    ) -> AcquiredSourceReadyCandidate:
        nonlocal network_calls
        network_calls += 1
        return _fake_acquired(carrier, str(row["candidateName"]))

    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", acquire)
    arguments = {
        "coverage_run_dir": tmp_path / "coverage",
        "output_root": tmp_path / "output",
        "source_set_id": "m100-resume-capsules",
        "target_scale": "M100",
        "source_revision": IDENTITY["sourceRevision"],
        "source_digest": IDENTITY["sourceDigest"],
        "entity_catalog_digest": IDENTITY["entityCatalogDigest"],
        "captured_at": CAPTURED_AT,
        "homepage_count": 2,
        "article_count": 0,
        "seed_selection": _seed_selection(
            tmp_path / "seed-selection.json", rows, homepage_count=2
        ),
    }

    first = acquire_homepage_article_source_ready_batch(**arguments)
    replay = acquire_homepage_article_source_ready_batch(**arguments)

    assert replay == first
    assert network_calls == 2


def test_acquisition_resume_skips_duplicated_seed_capsules_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """历史波次给同一 seed 冻结过两个合法 capsule：同参数 resume 必须确定性跳过多余的，而非整批拒绝。"""
    from content.source.research import homepage_article_source_ready_acquisition as mod
    from content.source.research.homepage_article_source_ready_evidence import (
        file_sha256,
    )

    rows = [_planned("首页去重实体")]
    projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"duplicated-seed-projection"),
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
    monkeypatch.setattr(
        mod,
        "acquire_mediawiki_source_ready_candidate",
        lambda row, *, carrier, **_: _fake_acquired(carrier, str(row["candidateName"])),
    )
    arguments = {
        "coverage_run_dir": tmp_path / "coverage",
        "output_root": tmp_path / "output",
        "source_set_id": "m100-duplicated-seed",
        "target_scale": "M100",
        "source_revision": IDENTITY["sourceRevision"],
        "source_digest": IDENTITY["sourceDigest"],
        "entity_catalog_digest": IDENTITY["entityCatalogDigest"],
        "captured_at": CAPTURED_AT,
        "homepage_count": 1,
        "article_count": 0,
        "seed_selection": _seed_selection(
            tmp_path / "seed-selection.json", rows, homepage_count=1
        ),
    }
    first = acquire_homepage_article_source_ready_batch(**arguments)
    evidence_root = Path(first["evidenceRoot"])
    selection = json.loads((evidence_root / "seed-selection.json").read_text())
    coverage_projection = json.loads(
        (evidence_root / "coverage-projection.json").read_text()
    )
    # 同一 seed、同一页面、不同波次 capturedAt：产出第二个合法 capsule。
    mod._write_acquired_candidate(
        _fake_acquired("homepage", "首页去重实体"),
        evidence_root=evidence_root,
        identity=IDENTITY,
        captured_at="2026-08-08T00:00:00Z",
        coverage_binding={
            "ref": "coverage-projection.json",
            "digest": str(coverage_projection["projectionDigest"]),
            "fileSha256": file_sha256(evidence_root / "coverage-projection.json"),
        },
        seed_selection_binding={
            "ref": "seed-selection.json",
            "digest": str(selection["selectionDigest"]),
            "fileSha256": file_sha256(evidence_root / "seed-selection.json"),
        },
        seed=selection["seeds"][0],
    )
    assert len(list((evidence_root / "capsules" / "homepage").iterdir())) == 2

    resume = acquire_homepage_article_source_ready_batch(**arguments)
    replay = acquire_homepage_article_source_ready_batch(**arguments)

    assert resume == replay
    assert resume["counts"] == {"homepage": 1, "article": 0}
    batch = json.loads(Path(resume["sourceReadyManifest"]).read_text())
    assert len(batch["candidateCapsules"]) == 1


def test_acquisition_shortfall_freezes_replayable_partial_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned(f"实体{index}") for index in range(4)]
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

    def acquire(
        row: dict[str, object], *, carrier: str, **_: object
    ) -> AcquiredSourceReadyCandidate:
        if carrier == "homepage" and row["candidateName"] != "实体0":
            raise MediaWikiSourceReadyRejected("homepage candidate unavailable")
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
            source_set_id="m100-partial-checkpoint",
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
            homepage_count=2,
            article_count=2,
            seed_selection=_seed_selection(
                tmp_path / "seed-selection.json", rows, homepage_count=2
            ),
        )
    checkpoint = captured.value.checkpoint
    assert checkpoint is not None
    assert checkpoint["status"] == "source_pool_shortfall"
    assert checkpoint["counts"] == {"homepage": 1, "article": 2}
    assert Path(checkpoint["sourceReadyManifest"]).is_file()
    report = json.loads(
        (Path(checkpoint["evidenceRoot"]) / checkpoint["reportRef"]).read_text()
    )
    assert report["counts"]["homepageShortfall"] == 1
    assert report["counts"]["articleShortfall"] == 0
    assert len(report["rejections"]) == 1
    assert report["rejections"][0]["reason"] == "homepage candidate unavailable"


def test_acquisition_resume_retries_previously_rejected_seeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """幂等 resume 必须按 capsule 存在性跳过：早于最后一个已接受 capsule 的被拒 seed 在生产者修复后必须被重试。"""
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned(f"重试实体{index}") for index in range(4)]
    projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"retry-rejected-projection"),
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
    blocked_names = {"重试实体1"}
    acquired_names: list[str] = []

    def acquire(
        row: dict[str, object], *, carrier: str, **_: object
    ) -> AcquiredSourceReadyCandidate:
        name = str(row["candidateName"])
        acquired_names.append(name)
        if name in blocked_names:
            raise MediaWikiSourceReadyRejected(
                "homepage source lacks an immutable structured fact"
            )
        return _fake_acquired(carrier, name)

    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", acquire)
    arguments = {
        "coverage_run_dir": tmp_path / "coverage",
        "output_root": tmp_path / "output",
        "source_set_id": "m100-retry-rejected",
        "target_scale": "M100",
        "source_revision": IDENTITY["sourceRevision"],
        "source_digest": IDENTITY["sourceDigest"],
        "entity_catalog_digest": IDENTITY["entityCatalogDigest"],
        "captured_at": CAPTURED_AT,
        "homepage_count": 4,
        "article_count": 0,
        "seed_selection": _seed_selection(
            tmp_path / "seed-selection.json",
            rows,
            homepage_count=4,
            seed_origin="current_coverage",
        ),
    }
    with pytest.raises(HomepageArticleSourceReadyAcquisitionError) as shortfall:
        acquire_homepage_article_source_ready_batch(**arguments)
    assert shortfall.value.code == mod.SOURCE_POOL_SHORTFALL
    assert shortfall.value.checkpoint is not None
    assert shortfall.value.checkpoint["counts"] == {"homepage": 3, "article": 0}

    # 生产者修复后，同参数 resume 必须重试之前被拒的 seed（它位于三个已
    # 接受 capsule 之间），而不是因列表位置被永久跳过。
    blocked_names.clear()
    acquired_names.clear()
    resumed = acquire_homepage_article_source_ready_batch(**arguments)

    assert acquired_names == ["重试实体1"]
    assert resumed["counts"] == {"homepage": 4, "article": 0}
    batch = json.loads(Path(resumed["sourceReadyManifest"]).read_text())
    assert len(batch["candidateCapsules"]) == 4
