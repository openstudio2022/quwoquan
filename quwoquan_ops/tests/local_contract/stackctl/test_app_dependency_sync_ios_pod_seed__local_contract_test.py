"""Sealed CocoaPods home/cache must seed private sync state when Podfile.lock matches."""

from __future__ import annotations

from pathlib import Path

from quwoquan_ops.cli.commands.app_dependency_sync_builder import seed_cocoapods_private_state


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_seed_cocoapods_private_state_copies_home_and_cache_when_lock_matches(
    tmp_path: Path,
) -> None:
    capsule = tmp_path / "capsule"
    _write(capsule / "Podfile.lock", "LOCK\n")
    _write(capsule / "home/repos/trunk/marker.txt", "trunk-seed")
    _write(capsule / "cache/Pods/CryptoSwift/marker.txt", "cache-seed")
    expected = tmp_path / "Podfile.lock"
    expected.write_text("LOCK\n", encoding="utf-8")
    home = tmp_path / "pod-home"
    cache = tmp_path / "pod-cache"
    assert seed_cocoapods_private_state(
        capsule_root=capsule, expected_lock=expected, home=home, cache=cache
    )
    assert (home / "repos/trunk/marker.txt").read_text(encoding="utf-8") == "trunk-seed"
    assert (cache / "Pods/CryptoSwift/marker.txt").read_text(encoding="utf-8") == "cache-seed"


def test_seed_cocoapods_private_state_rejects_stale_lock(tmp_path: Path) -> None:
    capsule = tmp_path / "capsule"
    _write(capsule / "Podfile.lock", "OLD\n")
    _write(capsule / "home/repos/trunk/marker.txt", "trunk-seed")
    expected = tmp_path / "Podfile.lock"
    expected.write_text("NEW\n", encoding="utf-8")
    home = tmp_path / "pod-home"
    cache = tmp_path / "pod-cache"
    assert not seed_cocoapods_private_state(
        capsule_root=capsule, expected_lock=expected, home=home, cache=cache
    )
    assert not home.exists()
    assert not cache.exists()
