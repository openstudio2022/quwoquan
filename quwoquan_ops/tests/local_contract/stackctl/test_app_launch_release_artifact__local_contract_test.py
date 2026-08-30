from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
DIGEST = "sha256:" + "a" * 64

def test_prod_sim_rejects_an_artifact_that_is_not_the_exact_release() -> None:
    """prod-sim 只接受 exact non-promotable simulator Release manifest。"""

    import importlib.util

    launcher_path = (
        ROOT / "quwoquan_app/scripts/device/launch_release_artifact.py"
    )
    spec = importlib.util.spec_from_file_location(
        "launch_release_artifact", launcher_path
    )
    assert spec is not None and spec.loader is not None
    launcher = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = launcher
    spec.loader.exec_module(launcher)

    with tempfile.TemporaryDirectory() as temporary:
        manifest_path = Path(temporary) / "app-artifact-manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema": "app-artifact-manifest",
                    "environment": "prod",
                    "platform": "android",
                    "buildMode": "release",
                    "distributionClass": "simulator",
                    # promotable 制品不是 prod-sim 的可运行对象。
                    "promotable": True,
                }
            ),
            encoding="utf-8",
        )
        handoff_path = manifest_path.with_name("launcher-handoff.json")
        handoff_path.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="APP.LAUNCH.prod_artifact_invalid"):
            launcher._load_inputs(
                manifest_path,
                "android",
                handoff_path,
                candidate_digest=DIGEST,
                artifact_manifest_digest=(
                    "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                ),
                launcher_handoff_digest=(
                    "sha256:" + hashlib.sha256(handoff_path.read_bytes()).hexdigest()
                ),
            )




