"""Campaign capsules must reference library bytes instead of owning copies."""

from __future__ import annotations

import errno
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_data" / "scripts"))

from content.execution.campaign.source_snapshot import (  # noqa: E402
    reference_governed_inputs,
)
from content.execution.source_pool.capsule_seal import (  # noqa: E402
    capsule_tree_is_sealed,
    discard_capsule_tree,
    seal_capsule_tree,
)
from core.content_library import library_cas_root  # noqa: E402

ROOTS = ("pkg", "top.txt")


def _governed_tree(root: Path) -> Path:
    """Build the shapes a governed closure can hold, including a shared body."""
    root.mkdir(parents=True)
    (root / "top.txt").write_text("top\n", encoding="utf-8")
    package = root / "pkg"
    (package / "nested").mkdir(parents=True)
    (package / "module.py").write_text("BODY = 1\n", encoding="utf-8")
    # Equal bytes at two paths must collapse onto one library entry.
    (package / "nested/duplicate.py").write_text("BODY = 1\n", encoding="utf-8")
    runner = package / "runner.sh"
    runner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    runner.chmod(0o755)
    (package / "nested/link.py").symlink_to("../module.py")
    (package / "__pycache__").mkdir()
    (package / "__pycache__/module.pyc").write_bytes(b"stale")
    (package / "empty").mkdir()
    return root


def _regular_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*") if not path.is_symlink() and path.is_file()
    )


def _inodes(paths: list[Path]) -> set[tuple[int, int]]:
    return {(path.stat().st_dev, path.stat().st_ino) for path in paths}


def _bytes_allocated_outside(root: Path, known: set[tuple[int, int]]) -> int:
    """Sum blocks held by inodes the library did not already own."""
    total = 0
    for key in _inodes(_regular_files(root)) - known:
        for path in _regular_files(root):
            info = path.stat()
            if (info.st_dev, info.st_ino) == key:
                total += info.st_blocks * 512
                break
    return total


@pytest.fixture
def governed(tmp_path: Path) -> Iterator[tuple[Path, Path, Path]]:
    repo = _governed_tree(tmp_path / "repo")
    library = tmp_path / "content_library"
    capsule = tmp_path / "capsules/first"
    reference_governed_inputs(repo, capsule, roots=ROOTS, library_root=library)
    yield repo, library, capsule
    # Sealed capsules and library entries are read-only by design; hand the
    # temporary tree back writable so the runner can reclaim it.
    for path in sorted(tmp_path.rglob("*"), reverse=True):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | 0o700)


def _library_files(library: Path) -> list[Path]:
    return sorted(
        path
        for path in library_cas_root("source", library_root=library).rglob("*")
        if path.is_file()
    )


def test_capsule_exposes_the_governed_shapes_and_drops_caches(
    governed: tuple[Path, Path, Path],
) -> None:
    _, _, capsule = governed
    assert (capsule / "top.txt").read_text(encoding="utf-8") == "top\n"
    assert (capsule / "pkg/module.py").read_text(encoding="utf-8") == "BODY = 1\n"
    assert (capsule / "pkg/nested/link.py").is_symlink()
    assert (capsule / "pkg/empty").is_dir()
    assert not (capsule / "pkg/__pycache__").exists()


def test_every_capsule_file_shares_its_inode_with_a_library_entry(
    governed: tuple[Path, Path, Path],
) -> None:
    _, library, capsule = governed
    entries = {path.stat().st_ino for path in _library_files(library)}
    assert entries, "referencing must admit governed bytes into the library"
    files = _regular_files(capsule)
    assert files, "capsule must expose the governed closure"
    assert all(path.stat().st_ino in entries for path in files)


def test_equal_bytes_collapse_onto_one_library_entry(
    governed: tuple[Path, Path, Path],
) -> None:
    _, library, capsule = governed
    module = (capsule / "pkg/module.py").stat()
    duplicate = (capsule / "pkg/nested/duplicate.py").stat()
    assert module.st_ino == duplicate.st_ino
    # top.txt, the shared body, and the executable runner.
    assert len(_library_files(library)) == 3


def test_library_entries_are_immutable_and_keep_the_executable_bit_addressable(
    governed: tuple[Path, Path, Path],
) -> None:
    _, library, capsule = governed
    for path in _library_files(library):
        mode = path.stat().st_mode & 0o777
        assert mode in {0o444, 0o555}, f"library entry must be read-only: {path}"
        assert path.name.endswith(".x") == bool(mode & 0o111)
    assert (capsule / "pkg/runner.sh").stat().st_mode & 0o111
    assert not (capsule / "pkg/module.py").stat().st_mode & 0o111
    with pytest.raises(OSError) as failure:
        (capsule / "pkg/module.py").write_bytes(b"tamper")
    assert failure.value.errno == errno.EACCES


def test_a_repeated_capsule_allocates_no_additional_bytes(
    tmp_path: Path,
    governed: tuple[Path, Path, Path],
) -> None:
    repo, library, _ = governed
    already_held = _inodes(_library_files(library))
    second = tmp_path / "capsules/second"

    reference_governed_inputs(repo, second, roots=ROOTS, library_root=library)

    assert _regular_files(second), "second capsule must expose the governed closure"
    assert _inodes(_library_files(library)) == already_held, (
        "a repeated freeze of one revision must not grow the library"
    )
    assert _bytes_allocated_outside(second, already_held) == 0, (
        "a repeated capsule must reference existing library entries, not copy them"
    )


def test_discarding_one_capsule_keeps_its_siblings_read_only(
    tmp_path: Path,
    governed: tuple[Path, Path, Path],
) -> None:
    repo, library, capsule = governed
    doomed = tmp_path / "capsules/doomed"
    reference_governed_inputs(repo, doomed, roots=ROOTS, library_root=library)
    seal_capsule_tree(doomed)
    seal_capsule_tree(capsule)
    assert capsule_tree_is_sealed(capsule)

    discard_capsule_tree(doomed)

    assert not doomed.exists()
    assert capsule_tree_is_sealed(capsule), (
        "discarding a capsule must not relax the shared library inodes"
    )


def test_referencing_refuses_a_populated_destination(
    tmp_path: Path,
    governed: tuple[Path, Path, Path],
) -> None:
    repo, library, capsule = governed
    with pytest.raises(ValueError, match="must be empty"):
        reference_governed_inputs(repo, capsule, roots=ROOTS, library_root=library)


def test_referencing_rejects_a_missing_governed_input(
    tmp_path: Path,
    governed: tuple[Path, Path, Path],
) -> None:
    repo, library, _ = governed
    with pytest.raises(ValueError, match="input is invalid"):
        reference_governed_inputs(
            repo,
            tmp_path / "capsules/absent",
            roots=("pkg", "absent.txt"),
            library_root=library,
        )
