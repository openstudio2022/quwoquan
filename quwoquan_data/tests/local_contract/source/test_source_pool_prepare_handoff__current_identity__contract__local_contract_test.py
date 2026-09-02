# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001
from __future__ import annotations

import argparse
from pathlib import Path

from content.source.research import handler_cli
from core import paths


def test_prepare_handoff_freezes_current_identity_and_supersession(
    tmp_path: Path, monkeypatch
) -> None:
    output_root = tmp_path / "output"
    entity_root = (
        tmp_path
        / "quwoquan_data/reference/travel/entities/china/四川省"
    )
    entity_root.mkdir(parents=True)
    (entity_root / "成都市.yaml").write_text("entity-catalog
", encoding="utf-8")
    previous = output_root / (
        "data/local/workspace/content-pre-acquisition-handoffs/"
        "four-carrier/revision-001.json"
    )
    previous.parent.mkdir(parents=True)

    source = {
        "algorithm": "sha256",
        "digest": "sha256:" + "1" * 64,
        "inputs": [],
    }
    bundle = {
        "algorithm": "sha256",
        "digest": "sha256:" + "2" * 64,
        "inputs": [],
    }
    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(
        handler_cli, "current_source_definition_snapshot",
        lambda repo_root: type("Snapshot", (), {"to_document": lambda self: source})(),
    )
    monkeypatch.setattr(
        handler_cli, "current_execution_bundle_identity",
        lambda repo_root: type("Bundle", (), {"to_document": lambda self: bundle})(),
    )
    monkeypatch.setattr(handler_cli, "entity_catalog_digest", lambda _ref: "sha256:" + "3" * 64)
    captured: dict[str, object] = {}

    def write(**kwargs):
        captured.update(kwargs)
        destination = output_root / (
            "data/local/workspace/content-pre-acquisition-handoffs/"
            "four-carrier/revision-002.json"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}
", encoding="utf-8")
        return {
            "handoffDigest": "sha256:" + "4" * 64,
            "sourceRevision": "sha256:" + "5" * 64,
            "sourceDigest": source,
            "executionBundle": bundle,
            "entityCatalogDigest": "sha256:" + "3" * 64,
            "activeCarriers": ["homepage", "article", "image", "video"],
            "workloadTargets": {carrier: 1 for carrier in ("homepage", "article", "image", "video")},
        }, destination

    monkeypatch.setattr(handler_cli, "write_pre_acquisition_handoff", write)
    handler_cli.handle_prepare_handoff(
        argparse.Namespace(
            handoff_id="four-carrier", handoff_revision=2,
            supersedes_handoff_ref=str(previous), vertical="travel",
            lifecycle="research", scope_type="region", region_ref="china/四川省",
            primary_topic_ref=None, related_topic_ref=[], run_date="20260831",
            sequence=1, retry_of=None,
            source_selection=[
                "homepage=site_primary:wikipedia",
                "article=site_primary:official_article",
                "image=search_supplement:wikimedia_commons",
                "video=search_supplement:wikimedia_commons_video",
            ],
            workload=["homepage=1", "article=1", "image=1", "video=1"],
        )
    )
    assert captured["source_digest"] == source
    assert captured["execution_bundle"] == bundle
    assert captured["supersedes_handoff"] == previous
    assert captured["workload_targets"] == {
        "homepage": 1, "article": 1, "image": 1, "video": 1,
    }
