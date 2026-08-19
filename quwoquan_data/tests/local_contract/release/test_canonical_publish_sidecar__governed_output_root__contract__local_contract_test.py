"""The publish fence and inventory index are governed output, not canonical content.

The process fence and the inventory index are derived state on the same reset
consistency boundary as the canonical publish tree, yet they are not content: the
tree is audited and version controlled, while these two are rebuilt from it
whenever they are absent. That leaves exactly one place they may live. Below the
governed output root they stay inside the reclamation window and the isolation
root; anywhere else — the system temporary directory in particular — they escape
the output budget and accumulate across clones and sessions, and a second clone
of the same tree would fence against a different file.
"""

from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import (  # noqa: E402
    DATA_EXECUTIONS_ROOT,
    OUTPUT_ROOT,
    PUBLISH_ROOT,
    canonical_publish_sidecar_root,
    publish_lock_path,
)


def _is_below(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-007
def test_sidecar_lives_below_the_governed_output_root(tmp_path: Path) -> None:
    """Only inside the governed output root is it a reclaimable process product."""

    for publish_root in (None, tmp_path / "publish"):
        sidecar = canonical_publish_sidecar_root(publish_root)

        assert _is_below(sidecar, OUTPUT_ROOT), (
            f"{sidecar} escapes the governed output root, so it is exempt from the "
            "output budget and invisible to the collector"
        )


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/design.md#dec-003
def test_sidecar_is_not_inside_the_canonical_publish_tree(tmp_path: Path) -> None:
    """Canonical publish holds reviewed consumer objects and nothing derived."""

    for publish_root in (PUBLISH_ROOT, tmp_path / "publish"):
        sidecar = canonical_publish_sidecar_root(publish_root)

        assert not _is_below(sidecar, publish_root), (
            f"{sidecar} would put derived fence/index state inside the audited "
            "canonical publish tree"
        )


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/design.md#dec-003
def test_sidecar_is_not_inside_any_execution_work_package(tmp_path: Path) -> None:
    """Lanes of one campaign are separate executions publishing to one tree.

    A fence owned by one execution work package cannot mutually exclude the other
    lanes writing the same publish tree.
    """

    sidecar = canonical_publish_sidecar_root(tmp_path / "publish")

    assert not _is_below(sidecar, DATA_EXECUTIONS_ROOT)


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#req-004
def test_process_fence_is_addressed_inside_its_own_publish_sidecar(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"

    lock = publish_lock_path(publish_root)

    assert lock.parent == canonical_publish_sidecar_root(publish_root)
    assert _is_below(lock, OUTPUT_ROOT)


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#req-004
def test_every_alias_of_one_publish_tree_resolves_to_one_sidecar(
    tmp_path: Path,
) -> None:
    """`reset-canonical` needs a single fence per tree, not per spelling of it."""

    publish_root = tmp_path / "publish"
    publish_root.mkdir()
    dotted_alias = tmp_path / "publish" / ".." / "publish"
    symlink_alias = tmp_path / "alias"
    symlink_alias.symlink_to(publish_root, target_is_directory=True)

    expected = canonical_publish_sidecar_root(publish_root)

    assert canonical_publish_sidecar_root(dotted_alias) == expected
    assert canonical_publish_sidecar_root(symlink_alias) == expected


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#req-004
def test_distinct_publish_trees_never_share_one_fence(tmp_path: Path) -> None:
    """An isolated test root must not contend with the repository publish tree."""

    first = canonical_publish_sidecar_root(tmp_path / "publish-a")
    second = canonical_publish_sidecar_root(tmp_path / "publish-b")

    assert first != second
    assert canonical_publish_sidecar_root(PUBLISH_ROOT) not in {first, second}
