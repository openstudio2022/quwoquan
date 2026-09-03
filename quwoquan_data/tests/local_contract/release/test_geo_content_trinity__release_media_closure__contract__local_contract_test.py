# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md#gwt-001
"""Legacy checked-in publish data must not bypass the current media gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
PUBLISH = ROOT / "quwoquan_data" / "publish"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.aggregate_release import (
    build_aggregate_release,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from content.release.canonical.rehydrate_media_holdings import (
    main as admit_carried_media_holdings,
)
from core import content_library
from core.source_digest import content_source_revision

ENTITY_CATALOG_DIGEST = "sha256:" + "e" * 64


@pytest.fixture(autouse=True)
def _carried_media_holdings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rebuild the checked-in golden holdings in this test's private library.

    Pytest deliberately redirects the writable carried-media root away from the
    repository, while this legacy-tree test needs the repository's immutable
    golden bytes as input. Point reads at that checked-in source and admissions
    at a temporary CAS so the result cannot depend on or mutate a developer's
    machine-level content library.
    """

    monkeypatch.setenv(
        "QWQ_CARRIED_MEDIA_ROOT",
        str(ROOT / "quwoquan_data" / "reference" / "golden_media"),
    )
    monkeypatch.setitem(
        content_library.LIBRARY_CAS_ROOT_BY_KIND,
        content_library.MEDIA_KIND,
        tmp_path / "content-library" / "_media_cas",
    )
    assert admit_carried_media_holdings(publish_root=PUBLISH) == 0


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def _manifest_paths(kind: str) -> list[Path]:
    return sorted((PUBLISH / kind).rglob("manifest.json"))


def test_geo_content_trinity_legacy_golden_cannot_bypass_current_release_gates(
    tmp_path: Path,
) -> None:
    manifests = [
        _object(path)
        for path in _manifest_paths("entities") + _manifest_paths("posts")
    ]
    assert manifests, "legacy publish evidence must remain inspectable"

    by_source_digest: dict[str, list[dict[str, object]]] = {}
    for manifest in manifests:
        source = manifest.get("sourceDigest")
        assert isinstance(source, dict)
        digest = str(source.get("digest") or "")
        by_source_digest.setdefault(digest, []).append(manifest)
    carriers = {
        str(manifest.get("contentType") or "homepage") for manifest in manifests
    }
    assert carriers == {"homepage", "article", "image", "video"}
    assert len(by_source_digest) > 1, (
        "legacy evidence must exercise cross-source-identity reuse"
    )
    source_digest = sorted(by_source_digest)[0]
    execution_ids = sorted(
        {
            str(manifest.get("executionId") or "")
            for manifest in manifests
            if str(manifest.get("executionId") or "")
        }
    )

    with pytest.raises(
        ObjectTransactionError,
        match=(
            "(requires one frozen sourceDigest|lacks a valid frozen sourceDigest|"
            "article media (closure|coverage))"
        ),
    ):
        build_aggregate_release(
            publish_root=PUBLISH,
            release_root=tmp_path / "releases",
            release_id="legacy-golden-must-not-be-reused",
            execution_ids=execution_ids,
            release_class="research",
            source_revision=content_source_revision(
                source_digest=source_digest,
                entity_catalog_digest=ENTITY_CATALOG_DIGEST,
            ),
            entity_catalog_digest=ENTITY_CATALOG_DIGEST,
        )
