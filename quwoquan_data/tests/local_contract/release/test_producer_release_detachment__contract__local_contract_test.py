# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020
from __future__ import annotations

import ast
from types import SimpleNamespace
from pathlib import Path

import pytest

from content.release.canonical import aggregate_release_builder as builder
from content.release.canonical.aggregate_release_documents import (
    release_header_document,
)
from content.release.canonical.aggregate_release_result import (
    aggregate_release_result,
)
from content.release.canonical.object_source_identity import source_identity_set
from core.source_digest import SourceDefinitionSnapshot

_DATA_ROOT = Path(__file__).resolve().parents[3]
_CANONICAL_ROOT = _DATA_ROOT / "scripts/content/release/canonical"
_FORBIDDEN_HEADER_FIELDS = {
    "targetEnvironment",
    "selectionScope",
    "releaseMode",
    "samplePlanRef",
    "samplePlanDigest",
    "contractMigration",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _selection(milestone: str) -> SimpleNamespace:
    targets = {"homepage": 1000, "article": 1000, "image": 1000, "video": 100}
    return SimpleNamespace(
        pool_digest="sha256:" + "3" * 64,
        eligible_count=sum(targets.values()),
        milestone=milestone,
        milestone_targets=targets,
    )


def test_m1000_header_and_result_need_no_sampling_authority_or_uat_plan() -> None:
    execution_id = "20260906--travel-article-detach--china--scale-1000"
    source_digest = "sha256:" + "1" * 64
    identities, identity_set_digest = source_identity_set(
        [
            {
                "executionId": execution_id,
                "sourceRevision": "sha256:" + "4" * 64,
                "sourceDigest": source_digest,
                "entityCatalogDigest": "sha256:" + "5" * 64,
            }
        ]
    )
    counts = {"homepage": 1000, "article": 1000, "image": 1000, "video": 100, "total": 3100}
    contents = [
        {
            "contentId": f"content-{index}",
            "version": 1,
            "postRef": f"article/m1000/{index}",
            "selectionIdentityDigest": "sha256:" + f"{index:064x}",
            "canonicalObjectDigest": "sha256:" + f"{index + 3000:064x}",
            "contentLibraryBindingDigest": "sha256:" + f"{index + 6000:064x}",
        }
        for index in range(1, 2101)
    ]
    header = release_header_document(
        release_id="m1000-detached-001",
        execution_ids=[execution_id],
        source_revision=None,
        source_digest=None,
        entity_catalog_digest=None,
        source_digest_documents=[SourceDefinitionSnapshot(source_digest).to_document()],
        asset_admission={
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {"verified": 0, "unverified": 0, "restricted": 0, "unknown": 0},
            "authorizationRequiredAssetIds": [],
            "researchAcceptedCount": 0,
            "commercialAcceptedCount": 0,
        },
        canonical_merkle="sha256:" + "2" * 64,
        release_class="research",
        product_lifecycle_state="research",
        pool_digest="sha256:" + "3" * 64,
        counts=counts,
        contents=contents,
        authors=[],
        milestone="M1000",
        milestone_targets={"homepage": 1000, "article": 1000, "image": 1000, "video": 100},
        source_identities=identities,
        source_identity_set_digest=identity_set_digest,
    )
    result = aggregate_release_result(
        release_id="m1000-detached-001",
        release_root="/release/m1000-detached-001",
        execution_ids=[execution_id],
        entity_count=1000,
        post_count=2100,
        creator_count=1,
        carrier_counts=counts,
        canonical_merkle="sha256:" + "2" * 64,
        manifest_digest="sha256:" + "6" * 64,
        cohort_selection=_selection("M1000"),
        excluded=(),
    )

    assert header.keys().isdisjoint(_FORBIDDEN_HEADER_FIELDS)
    assert result.keys().isdisjoint(_FORBIDDEN_HEADER_FIELDS)


def test_aggregate_builder_source_does_not_create_uat_artifact() -> None:
    builder = _CANONICAL_ROOT / "aggregate_release_builder.py"
    source = builder.read_text(encoding="utf-8")
    imports = _imports(builder)

    assert "uat/sample_plan.json" not in source
    assert "build_release_uat_sample_plan_artifact" not in source
    assert "sampling_authority" not in source
    assert not any("release_uat" in name for name in imports)
    assert not any("readback" in name for name in imports)


def test_producer_forward_import_graph_has_no_environment_edge() -> None:
    entry_modules = {
        "content.release.canonical.aggregate_release",
        "content.release.canonical.aggregate_release_builder",
        "content.release.canonical.aggregate_release_existing",
        "content.release.canonical.aggregate_release_documents",
        "content.release.canonical.aggregate_release_pool",
        "content.release.canonical.aggregate_release_pool_closure",
        "content.release.canonical.aggregate_release_result",
        "content.release.canonical.aggregate_release_selection",
        "content.release.canonical.handler_pool",
        "content.release.canonical.producer_release_handoff",
        "content.release.canonical.integrity",
        "content.release.canonical.release_consistency",
        "content.release.canonical.release_header",
        "content.release.canonical.release_media_consistency",
    }
    imports: set[str] = set()
    for module in entry_modules:
        path = _CANONICAL_ROOT / (module.rsplit(".", 1)[-1] + ".py")
        imports.update(_imports(path))

    assert not any(name.startswith("content.release.environment") for name in imports)


def test_producer_release_graph_has_no_consumer_named_selection_model() -> None:
    for name in (
        "aggregate_release_builder.py",
        "aggregate_release_existing.py",
        "aggregate_release_pool.py",
        "aggregate_release_selection.py",
    ):
        source = (_CANONICAL_ROOT / name).read_text(encoding="utf-8")
        assert "EnvironmentRelease" not in source
        assert "environment_selection" not in source
        assert "selection_scope" not in source
        assert "targetEnvironment" not in source


def test_producer_cli_registration_does_not_load_consumer_modules() -> None:
    source = (_CANONICAL_ROOT / "handler.py").read_text(encoding="utf-8")

    for forbidden in (
        "acceptance_lease import",
        "lifecycle_exit import",
        "build_lookup_indexes import",
        "reset import",
        "object_transaction_replay import",
    ):
        assert forbidden not in source


@pytest.mark.parametrize("milestone", ("M100", "M1000"))
def test_milestone_build_writes_no_uat_artifact_or_consumer_fields(
    milestone: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish_root = tmp_path / "publish"
    release_root = tmp_path / "releases"
    release_id = f"{milestone.lower()}-detached-001"
    execution_id = f"20260906--travel-article-{milestone.lower()}--china--scale-100"
    counts = {"homepage": 1, "article": 0, "image": 0, "video": 0, "total": 1}
    selection = SimpleNamespace(
        pool_digest="sha256:" + "3" * 64,
        eligible_count=1,
        milestone=milestone,
        milestone_targets={"homepage": 1, "article": 0, "image": 0, "video": 0},
    )
    preparation = SimpleNamespace(
        excluded=(),
        cohort_selection=selection,
        execution_ids=[execution_id],
        source_digests=(SourceDefinitionSnapshot("sha256:" + "1" * 64),),
        source_identities=({
            "sourceRevision": "sha256:" + "4" * 64,
            "sourceDigest": "sha256:" + "1" * 64,
            "entityCatalogDigest": "sha256:" + "5" * 64,
            "executionIds": [execution_id],
        },),
        source_identity_set_digest="sha256:" + "6" * 64,
        entity_catalog_digest=None,
        source_revision=None,
        desired={
            "creators": [],
            "entities": ["地点/景区/fixture"],
            "posts": [],
            "tags": [],
        },
    )
    captured_header: dict[str, object] = {}

    monkeypatch.setattr(builder, "prepare_pool_release", lambda **_kwargs: preparation)
    monkeypatch.setattr(builder, "build_release_contents", lambda _selection: [])
    monkeypatch.setattr(builder, "build_release_authors", lambda *_args, **_kwargs: [])

    def copy_object(_source: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(builder, "_copy_tree", copy_object)
    monkeypatch.setattr(
        builder,
        "build_release_media_manifest",
        lambda **_kwargs: {"issues": [], "assets": []},
    )
    monkeypatch.setattr(builder, "bind_release_object_media_assets", lambda **_kwargs: None)
    monkeypatch.setattr(
        builder,
        "build_release_asset_admission",
        lambda **_kwargs: {
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {
                "verified": 0,
                "unverified": 0,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": [],
            "researchAcceptedCount": 0,
            "commercialAcceptedCount": 0,
        },
    )
    monkeypatch.setattr(builder, "assert_valid", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(builder, "objects_merkle", lambda *_args, **_kwargs: "sha256:" + "2" * 64)

    def header_document(**kwargs: object) -> dict[str, object]:
        captured_header.update(kwargs)
        return {
            "schema": "quwoquan_data.release",
            "releaseId": release_id,
            "releaseClass": "research",
            "productLifecycleState": "research",
            "canonicalMerkle": "sha256:" + "2" * 64,
            "executionIds": [execution_id],
            "counts": counts,
            "milestone": milestone,
        }

    monkeypatch.setattr(builder, "release_header_document", header_document)
    monkeypatch.setattr(
        builder,
        "release_desired_state_document",
        lambda **_kwargs: {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": preparation.desired,
        },
    )
    monkeypatch.setattr(builder, "copy_release_media_objects", lambda **_kwargs: None)
    monkeypatch.setattr(
        builder,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed", "blockingIssues": []},
    )
    monkeypatch.setattr(
        builder,
        "release_attestation_document",
        lambda **_kwargs: {"schema": "quwoquan_data.release_attestation"},
    )
    monkeypatch.setattr(builder, "assert_environment_neutral", lambda _root: None)
    monkeypatch.setattr(builder, "payload_digest", lambda _root: "sha256:" + "7" * 64)

    result = builder._build_aggregate_release.__wrapped__(
        publish_root=publish_root,
        release_root=release_root,
        release_id=release_id,
        release_class="research",
        cohort={"milestone": milestone},
    )

    release_dir = release_root / release_id
    assert not (release_dir / "payload/uat/sample_plan.json").exists()
    assert captured_header.keys().isdisjoint(_FORBIDDEN_HEADER_FIELDS)
    assert result.keys().isdisjoint(_FORBIDDEN_HEADER_FIELDS)
