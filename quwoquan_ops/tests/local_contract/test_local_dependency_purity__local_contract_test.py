from __future__ import annotations

import tempfile
from pathlib import Path

from quwoquan_ops.gate.verify_local_dependency_purity import _verify_ios_pods


LOCK = """PODS:\n  - DemoPod (1.0.0)\nSPEC REPOS:\n  trunk:\n    - DemoPod\n"""


def test_clean_checkout_uses_podfile_lock_without_requiring_generated_pods() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        podfile_lock = root / "Podfile.lock"
        podfile_lock.write_text(LOCK, encoding="utf-8")
        failures: list[str] = []

        _verify_ios_pods(
            failures,
            podfile_lock=podfile_lock,
            pods_manifest_lock=root / "Pods/Manifest.lock",
            pods_dir=root / "Pods",
        )

        assert failures == []


def test_materialized_pods_require_matching_manifest_and_trunk_directories() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pods_dir = root / "Pods"
        pods_dir.mkdir()
        podfile_lock = root / "Podfile.lock"
        podfile_lock.write_text(LOCK, encoding="utf-8")
        failures: list[str] = []

        _verify_ios_pods(
            failures,
            podfile_lock=podfile_lock,
            pods_manifest_lock=pods_dir / "Manifest.lock",
            pods_dir=pods_dir,
        )

        assert any("Manifest.lock" in failure for failure in failures)

        (pods_dir / "Manifest.lock").write_text(LOCK, encoding="utf-8")
        failures.clear()
        _verify_ios_pods(
            failures,
            podfile_lock=podfile_lock,
            pods_manifest_lock=pods_dir / "Manifest.lock",
            pods_dir=pods_dir,
        )
        assert any("DemoPod" in failure for failure in failures)

        (pods_dir / "DemoPod").mkdir()
        failures.clear()
        _verify_ios_pods(
            failures,
            podfile_lock=podfile_lock,
            pods_manifest_lock=pods_dir / "Manifest.lock",
            pods_dir=pods_dir,
        )
        assert failures == []
