"""Canonical reset is allowed only after a matching empty-baseline receipt."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical import reset  # noqa: E402
from content.release.canonical.canonical_inventory import (  # noqa: E402
    apply_inventory_delta,
    canonical_inventory_path,
    load_or_bootstrap_inventory,
    write_inventory,
)


BASELINE_ID = "20260725--travel-content--empty--test-001"
PUBLISHED_REF = "posts/article/攻略/峨眉山/1/manifest.json"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _baseline(release_root: Path) -> None:
    _write_json(
        release_root / BASELINE_ID / "payload/release.json",
        {"releaseKind": "empty_baseline"},
    )
    _write_json(
        release_root / BASELINE_ID / "payload/desired_state.json",
        {"desiredRefs": {"creators": [], "entities": [], "posts": [], "tags": []}},
    )


def _receipt(output_root: Path, environment: str) -> None:
    _write_json(
        output_root
        / "env"
        / environment
        / "runs/data-release"
        / BASELINE_ID
        / "apply-test"
        / "applied_ref.json",
        {"releaseId": BASELINE_ID},
    )


def test_release_reset_canonical__clears_only_canonical_output_after_baseline_receipts__functional__local_contract(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "data/releases"
    output_root = tmp_path
    publish_root = tmp_path / "publish"
    _baseline(release_root)
    _receipt(output_root, "alpha")
    _receipt(output_root, "beta")
    (publish_root / "creators/example").mkdir(parents=True)
    (publish_root / "entities/example").mkdir(parents=True)
    (publish_root / "tags/Topic").mkdir(parents=True)

    removed = reset.reset_canonical_publish(
        empty_baseline_release=BASELINE_ID,
        environments=("alpha", "beta"),
        publish_root=publish_root,
        release_root=release_root,
        output_root=output_root,
    )

    assert removed == ("creators", "entities", "tags")
    assert list(publish_root.iterdir()) == []


def _publish_one_object(publish_root: Path) -> None:
    """Publish one object in the exact order an object transaction applies it."""
    publish_root.mkdir(parents=True, exist_ok=True)
    inventory = load_or_bootstrap_inventory(publish_root)
    payload = json.dumps({"schema": "quwoquan_data.post_object"}).encode("utf-8")
    destination = publish_root / PUBLISHED_REF
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    pending = apply_inventory_delta(
        inventory,
        [
            {
                "destination": PUBLISHED_REF,
                "operation": "create",
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        ],
        publish_root=publish_root,
    )
    write_inventory(publish_root, pending)


def test_release_reset_canonical__drops_the_inventory_sidecar_with_the_tree__functional__local_contract(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "data/releases"
    publish_root = tmp_path / "publish"
    _baseline(release_root)
    _receipt(tmp_path, "alpha")
    _publish_one_object(publish_root)
    assert load_or_bootstrap_inventory(publish_root)["stats"]["fileCount"] == 1

    reset.reset_canonical_publish(
        empty_baseline_release=BASELINE_ID,
        environments=("alpha",),
        publish_root=publish_root,
        release_root=release_root,
        output_root=tmp_path,
    )

    assert not canonical_inventory_path(publish_root).exists()
    cold = load_or_bootstrap_inventory(publish_root)
    assert (cold["revision"], cold["stats"]["fileCount"]) == (0, 0)
    # A retained sidecar would still hold this objectRef and fail the next wave
    # with `canonical inventory create CAS drift`.
    _publish_one_object(publish_root)
    assert load_or_bootstrap_inventory(publish_root)["stats"]["fileCount"] == 1


def test_release_reset_canonical__blocks_without_every_baseline_receipt__functional__local_contract(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "data/releases"
    _baseline(release_root)
    _receipt(tmp_path, "alpha")

    with pytest.raises(RuntimeError, match="empty baseline is not applied"):
        reset.reset_canonical_publish(
            empty_baseline_release=BASELINE_ID,
            environments=("alpha", "beta"),
            publish_root=tmp_path / "publish",
            release_root=release_root,
            output_root=tmp_path,
        )
