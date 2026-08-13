from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.source.research.homepage_article_source_ready_aggregate import (
    merge_homepage_article_source_ready_batches,
)
from content.source.research.homepage_article_source_ready_batch import (
    HomepageArticleSourceReadyBatchError,
    _digest,
    freeze_homepage_article_source_ready_batch,
    load_homepage_article_source_ready_batch,
)

from quwoquan_data.tests.local_contract.source.test_homepage_article_source_ready_batch__evidence_projection__contract__local_contract_test import (
    _batch,
)
from support.scale_source_pool_catalog_fixture import (
    IDENTITY,
)


def _members(root: Path) -> list[Path]:
    manifests: list[Path] = []
    for index in range(2):
        member_root = (
            root
            / "homepage-article-source-ready"
            / "m100"
            / f"member-{index}"
        )
        _, manifest = _batch(member_root, index=index)
        manifests.append(manifest)
    return manifests


def _merge(root: Path, manifests: list[Path]) -> dict[str, object]:
    return merge_homepage_article_source_ready_batches(
        batch_manifests=manifests,
        output_root=root,
        source_set_id="m100-homepage-article-aggregate",
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        created_at="2026-08-08T01:00:00Z",
    )


def _carrier_only_member(root: Path, *, index: int, carrier: str) -> Path:
    batch, path = _batch(root, index=index)
    binding = next(
        row for row in batch["candidateCapsules"] if row["carrier"] == carrier
    )
    stable = {
        key: value for key, value in batch.items() if key != "sourceSetDigest"
    }
    stable["sourceSetId"] = f"{batch['sourceSetId']}-{carrier}"
    stable["candidateCapsules"] = [binding]
    stable["counts"] = {
        "homepage": 1 if carrier == "homepage" else 0,
        "article": 1 if carrier == "article" else 0,
    }
    document = {**stable, "sourceSetDigest": _digest(stable)}
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_merge_rebases_member_roots_and_freezes_exact_catalogs(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    manifests = _members(output_root)

    result = _merge(output_root, manifests)
    replay = _merge(output_root, manifests)

    assert replay == result
    assert result["counts"] == {"homepage": 2, "article": 2}
    assert result["memberCount"] == 2
    manifest = Path(str(result["sourceReadyManifest"]))
    loaded = load_homepage_article_source_ready_batch(
        manifest, evidence_root=output_root
    )
    assert len(loaded["homepageCandidates"]) == 2
    assert len(loaded["articleCandidates"]) == 2
    bindings = loaded["capsuleBindings"]
    assert all(
        str(row["ref"]).startswith("homepage-article-source-ready/m100/member-")
        for row in bindings.values()
    )
    frozen = freeze_homepage_article_source_ready_batch(
        manifest,
        evidence_root=output_root,
        output_root=tmp_path / "catalog-output",
        minimum_homepage_candidate_count=2,
        minimum_article_candidate_count=2,
    )
    assert frozen["homepage"]["candidateCount"] == 2
    assert frozen["article"]["candidateCount"] == 2


def test_merge_accepts_carrier_exclusive_batches_from_one_frozen_selection(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    homepage = _carrier_only_member(
        output_root / "homepage-article-source-ready/m100/homepage-member",
        index=10,
        carrier="homepage",
    )
    article = _carrier_only_member(
        output_root / "homepage-article-source-ready/m100/article-member",
        index=11,
        carrier="article",
    )

    result = _merge(output_root, [homepage, article])

    assert result["counts"] == {"homepage": 1, "article": 1}
    projection = json.loads(
        (output_root / str(result["aggregateProjectionRef"])).read_text()
    )
    assert sorted(
        (
            row["counts"]["homepage"],
            row["counts"]["article"],
        )
        for row in projection["memberBatches"]
    ) == [(0, 1), (1, 0)]


def test_merge_rejects_duplicate_or_identity_drift(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    manifests = _members(output_root)

    with pytest.raises(HomepageArticleSourceReadyBatchError) as duplicate:
        _merge(output_root, [manifests[0], manifests[0]])
    assert duplicate.value.code == "DATA.SOURCE.INVALID_EVIDENCE"

    with pytest.raises(HomepageArticleSourceReadyBatchError) as identity:
        merge_homepage_article_source_ready_batches(
            batch_manifests=manifests,
            output_root=output_root,
            source_set_id="identity-drift",
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest="sha256:" + "9" * 64,
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            created_at="2026-08-08T01:00:00Z",
        )
    assert identity.value.code == "DATA.SOURCE.INVALID_EVIDENCE"


def test_merge_rejects_symlink_and_create_once_drift(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    manifests = _members(output_root)
    link = output_root / "homepage-article-source-ready/m100/link/batches/link.json"
    link.parent.mkdir(parents=True)
    link.symlink_to(manifests[0])
    with pytest.raises(HomepageArticleSourceReadyBatchError) as symlink:
        _merge(output_root, [link, manifests[1]])
    assert symlink.value.code == "DATA.SOURCE.INVALID_EVIDENCE"

    result = _merge(output_root, manifests)
    projection = output_root / str(result["aggregateProjectionRef"])
    projection.write_text(json.dumps({"tampered": True}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError) as collision:
        _merge(output_root, manifests)
    assert getattr(collision.value, "code", "") == "DATA.SOURCE.INVALID_EVIDENCE"
