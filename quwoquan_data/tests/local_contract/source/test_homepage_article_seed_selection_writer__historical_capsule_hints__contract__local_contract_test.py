from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.source.research.homepage_article_seed_selection import (
    HomepageArticleSeedSelectionError,
    seed_id,
)
from content.source.research.homepage_article_seed_selection_writer import (
    build_seed_selection_from_current_coverage,
    build_seed_selection_from_historical_capsules,
)
from content.source.research.homepage_article_source_ready_evidence import (
    canonical_digest,
    file_sha256,
)


def _write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _fixture(root: Path) -> tuple[str, str]:
    candidate_id = "homepage-historical-1"
    capsule_stable = {
        "schema": "quwoquan_data.homepage_article_source_ready_candidate",
        "carrier": "homepage",
        "sourceRevision": "sha256:" + "a" * 64,
        "sourceDigest": "sha256:" + "b" * 64,
        "entityCatalogDigest": "sha256:" + "c" * 64,
        "candidate": {
            "candidateId": candidate_id,
            "entityRef": "/entity/地点/城市/测试市",
            "primarySource": {
                "sourceUrl": "https://zh.wikipedia.org/wiki/test",
            },
        },
        "materialization": {
            "body": {"contentSha256": "sha256:" + "d" * 64}
        },
        "provenance": {},
    }
    capsule = {
        **capsule_stable,
        "capsuleDigest": canonical_digest(capsule_stable),
    }
    capsule_ref = "capsules/homepage/one.json"
    _write(root / capsule_ref, capsule)
    planned = {
        "coverageEntityIdentity": "name_location:测试市|测试省|测试市|",
        "canonicalEntityRef": "/entity/地点/城市/测试市",
        "candidateName": "测试市",
        "province": "测试省",
        "city": "测试市",
        "district": "",
        "entityType": "地点/城市",
        "source": {
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "sourceUrl": "https://zh.wikipedia.org/wiki/test",
        },
    }
    planned["coverageRecordDigest"] = canonical_digest(planned)
    projection_stable = {
        "schema": "quwoquan_data.coverage_projection",
        "plannedCandidates": [planned],
    }
    projection = {
        **projection_stable,
        "projectionDigest": canonical_digest(projection_stable),
    }
    projection_ref = "coverage-projection.json"
    _write(root / projection_ref, projection)
    batch = {
        "schema": "quwoquan_data.homepage_article_source_ready_batch",
        "candidateCapsules": [
            {
                "candidateId": candidate_id,
                "carrier": "homepage",
                "ref": capsule_ref,
                "fileSha256": file_sha256(root / capsule_ref),
                "digest": capsule["capsuleDigest"],
                "evidenceRootRef": ".",
            }
        ],
        "coverageProjection": {
            "ref": projection_ref,
            "fileSha256": file_sha256(root / projection_ref),
            "digest": projection["projectionDigest"],
        },
    }
    batch_ref = "batches/one.json"
    _write(root / batch_ref, batch)
    return batch_ref, candidate_id


def test_writer_strips_legacy_identity_and_keeps_only_fresh_lookup_hints(
    tmp_path: Path,
) -> None:
    batch_ref, candidate_id = _fixture(tmp_path)

    result = build_seed_selection_from_historical_capsules(
        evidence_root=tmp_path,
        batch_refs=(batch_ref,),
        seed_set_id="m100-wave-seeds",
        homepage_candidate_ids=(candidate_id,),
        article_candidate_ids=(),
    )

    assert result["counts"] == {"homepage": 1, "article": 0}
    seed = result["seeds"][0]
    assert seed["seedOrigin"] == "historical_capsule_hint"
    assert seed["coverageKey"]["entityRef"] == "/entity/地点/城市/测试市"
    assert seed["historicalBaseline"]["bodyContentSha256"] == "sha256:" + "d" * 64
    assert not ({"sourceRevision", "sourceDigest", "receiptRef"} & set(seed))


def test_current_coverage_mode_selects_exact_ready_frozen_canonical_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_seed_selection_writer as mod

    canonical_ref = "/entity/地点/景区/黄龙风景名胜区"
    ready = {
        "schema": "quwoquan_data.source_ready_candidate",
        "identityKey": "name_location:黄龙|四川省|阿坝州|松潘县",
        "candidate": {
            "name": "黄龙",
            "canonicalName": "黄龙风景名胜区",
            "province": "四川省",
            "city": "阿坝州",
            "district": "松潘县",
        },
        "attemptedSources": ["wikipedia"],
        "qualified": True,
        "evidence": {
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "canonicalUrl": "https://zh.wikipedia.org/wiki/黄龙风景名胜区",
            "resolvedTitle": "黄龙风景名胜区",
            "matchConfidence": 0.95,
        },
        "qualifiedAt": "2026-08-12T00:00:00Z",
    }
    frozen = {
        **ready,
        "selection": {
            "provinceRank": 1,
            "coverageCell": {
                "city": "阿坝州",
                "district": "松潘县",
                "entityType": "地点/景区",
            },
        },
    }
    (tmp_path / "source_ready.ndjson").write_text(
        json.dumps(ready, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (tmp_path / "frozen_targets.ndjson").write_text(
        json.dumps(frozen, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    row = {
        "coverageEntityIdentity": ready["identityKey"],
        "canonicalEntityRef": canonical_ref,
        "candidateName": "黄龙风景名胜区",
        "province": "四川省",
        "city": "阿坝州",
        "district": "松潘县",
        "entityType": "地点/景区",
        "source": {
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "sourceUrl": "https://zh.wikipedia.org/wiki/黄龙风景名胜区",
            "observedAt": "2026-08-12T00:00:00Z",
        },
        "coverageRecordDigest": canonical_digest(frozen),
    }
    projection = {"plannedCandidates": [row], "projectionDigest": "sha256:" + "9" * 64}
    monkeypatch.setattr(
        mod,
        "project_coverage_source_ready_catalog_inputs",
        lambda **_: projection,
    )

    result = build_seed_selection_from_current_coverage(
        coverage_run_dir=tmp_path,
        source_revision="sha256:" + "1" * 64,
        source_digest="sha256:" + "2" * 64,
        entity_catalog_digest="sha256:" + "3" * 64,
        seed_set_id="m100-current-exact",
        homepage_entity_refs=(canonical_ref,),
        article_entity_refs=(canonical_ref,),
    )

    assert result["counts"] == {"homepage": 1, "article": 1}
    assert {row["seedOrigin"] for row in result["seeds"]} == {"current_coverage"}
    assert {row["coverageKey"]["entityRef"] for row in result["seeds"]} == {canonical_ref}
    assert all("historicalBaseline" not in row for row in result["seeds"])


def test_current_coverage_photography_article_freezes_category_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_seed_selection_writer as mod

    canonical_ref = "/entity/地点/景区/黄龙风景名胜区"
    ready = {
        "identityKey": "name_location:黄龙|四川省|阿坝州|松潘县",
        "candidate": {},
        "qualified": True,
    }
    frozen = {
        **ready,
        "selection": {
            "coverageCell": {
                "city": "阿坝州",
                "district": "松潘县",
                "entityType": "地点/景区",
            }
        },
    }
    (tmp_path / "source_ready.ndjson").write_text(
        json.dumps(ready, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (tmp_path / "frozen_targets.ndjson").write_text(
        json.dumps(frozen, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    row = {
        "coverageEntityIdentity": ready["identityKey"],
        "canonicalEntityRef": canonical_ref,
        "candidateName": "黄龙风景名胜区",
        "province": "四川省",
        "city": "阿坝州",
        "district": "松潘县",
        "entityType": "地点/景区",
        "source": {
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "sourceUrl": "https://zh.wikipedia.org/wiki/黄龙风景名胜区",
        },
        "coverageRecordDigest": canonical_digest(frozen),
    }
    projection = {"plannedCandidates": [row], "projectionDigest": "sha256:" + "9" * 64}
    monkeypatch.setattr(mod, "project_coverage_source_ready_catalog_inputs", lambda **_: projection)

    result = build_seed_selection_from_current_coverage(
        coverage_run_dir=tmp_path,
        source_revision="sha256:" + "1" * 64,
        source_digest="sha256:" + "2" * 64,
        entity_catalog_digest="sha256:" + "3" * 64,
        seed_set_id="m100-current-photography",
        homepage_entity_refs=(),
        article_entity_refs=(),
        article_photography_entity_refs=(canonical_ref,),
    )

    seed = result["seeds"][0]
    assert seed["articleCategory"] == "photography"
    assert seed["writingIntent"] == "planning_consultation"
    assert seed["topicTagRefs"] == ["Topic/旅行/玩法/摄影旅拍"]
    assert seed["seedId"] == seed_id(
        seed_origin="current_coverage",
        coverage_key=seed["coverageKey"],
        article_category="photography",
    )


def test_writer_rejects_tampered_historical_capsule(tmp_path: Path) -> None:
    batch_ref, candidate_id = _fixture(tmp_path)
    capsule = tmp_path / "capsules/homepage/one.json"
    capsule.write_text("{}\n", encoding="utf-8")

    with pytest.raises(HomepageArticleSeedSelectionError, match="file drift"):
        build_seed_selection_from_historical_capsules(
            evidence_root=tmp_path,
            batch_refs=(batch_ref,),
            seed_set_id="m100-wave-seeds",
            homepage_candidate_ids=(candidate_id,),
            article_candidate_ids=(),
        )
