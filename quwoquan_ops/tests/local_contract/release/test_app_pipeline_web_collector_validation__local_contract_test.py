from __future__ import annotations

from pathlib import Path

import pytest

from quwoquan_ops.ci import collect_stackctl_app_shard as shard_collector
from quwoquan_ops.cli.commands import package_app_artifact as artifact_producer
from quwoquan_ops.cli.commands import package_app_artifact_helpers as artifact_helpers
from quwoquan_ops.tests.local_contract.release.test_app_pipeline_candidate_chain__local_contract_test import (
    ROOT,
    _source,
    _stackctl_result,
    _web_release_manifest,
)
from quwoquan_ops.tests.support.app_pipeline_web_artifact_test_support import (
    write_valid_web_artifact,
)


@pytest.fixture(autouse=True)
def _bind_fake_producer_semantic_readback(monkeypatch: pytest.MonkeyPatch) -> None:
    revision, tree = _source()
    monkeypatch.setattr(
        artifact_helpers,
        "_current_build_input_identity",
        lambda: {
            "sourceGitSha": revision,
            "sourceTreeDigest": tree,
            "sourceCapsuleDigest": "sha256:" + "3" * 64,
            "sourceStatusDigest": artifact_producer._EMPTY_STATUS_DIGEST,
            "flutterVersion": "3.35.1",
            "commandResolutionDigest": "sha256:" + "6" * 64,
            "displayVersion": "1.0.0",
            "buildNumber": "1",
        },
    )
    monkeypatch.setattr(
        artifact_helpers,
        "_artifact_semantic_identity",
        lambda **_kwargs: ("sha256:" + "1" * 64, "sha256:" + "4" * 64),
    )


@pytest.mark.parametrize(
    "invalid_artifact",
    ("invalid-pwa", "missing-bootstrap", "embedded-runtime", "missing-font"),
)
def test_collector_rejects_digest_bound_but_nonofficial_web_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_artifact: str,
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "shared-web"
    write_valid_web_artifact(artifact)
    if invalid_artifact == "invalid-pwa":
        (artifact / "manifest.json").write_text("{}", encoding="utf-8")
    elif invalid_artifact == "missing-bootstrap":
        (artifact / "qwq_bootstrap.js").unlink()
    elif invalid_artifact == "embedded-runtime":
        (artifact / "runtime-config-package.json").write_text("{}", encoding="utf-8")
    else:
        (artifact / "assets/FontManifest.json").unlink()

    result = _stackctl_result(
        tmp_path,
        build_product_id="web-shared",
        artifact=artifact,
    )
    official = _web_release_manifest(tmp_path, result)
    bundle = tmp_path / "must-not-seal"

    with pytest.raises(ValueError, match="shared Web artifact is not official"):
        shard_collector.collect(
            result,
            bundle,
            web_release_manifest=official,
        )
    assert not bundle.exists()
