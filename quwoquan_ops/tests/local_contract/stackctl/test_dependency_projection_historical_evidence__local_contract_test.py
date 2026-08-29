"""Historical package evidence survives deletion of its private build projection."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from quwoquan_ops.cli.commands.package_app_artifact import (
    _validate_persisted_dependency_evidence,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_projection_verify import (
    load_dependency_projection_cas_evidence,
    load_dependency_projection_cas_readback,
    load_historical_dependency_projection_cas_evidence,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_projection_contract import (
    COMPONENT_LOGICAL_PATHS,
    EXPECTATION_SCHEMA,
    READBACK_SCHEMA,
    environment_identity,
    source_identity,
)


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _digest(encoded: bytes) -> str:
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _write_private(path: Path, value: dict[str, Any]) -> str:
    encoded = _canonical(value)
    path.write_bytes(encoded)
    path.chmod(0o600)
    return _digest(encoded)


def _expectation_manifest(
    *, projection_root: Path, source_manifest: Path
) -> dict[str, Any]:
    values = {
        "PUB_CACHE": str(projection_root / "quwoquan_app/.dart_tool/qwq_pub_cache"),
        "HOME": str(projection_root / ".dependency-state/home"),
        "XDG_CONFIG_HOME": str(projection_root / ".dependency-state/config"),
        "XDG_CACHE_HOME": str(projection_root / ".dependency-state/cache"),
        "FLUTTER_SWIFT_PACKAGE_MANAGER": "false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return {
        "schema": EXPECTATION_SCHEMA,
        "projectionRoot": str(projection_root),
        "source": {
            "manifestPath": str(source_manifest),
            "manifestDigest": "sha256:" + "1" * 64,
            "baselineId": "sha256:" + "2" * 64,
            "inputDigest": "sha256:" + "3" * 64,
            "inputCount": 1,
            "dependencyMarkers": [
                {
                    "logicalPath": COMPONENT_LOGICAL_PATHS["productionPub"],
                    "digest": "sha256:" + "4" * 64,
                    "size": 17,
                }
            ],
        },
        "components": {
            "productionPub": {
                "kind": "pub",
                "treePath": "quwoquan_app/.dart_tool/qwq_pub_cache",
                "lockPath": "quwoquan_app/pubspec.lock",
                "manifestDigest": "sha256:" + "5" * 64,
                "treeDigest": "sha256:" + "6" * 64,
                "entryCount": 7,
                "directoryCount": 8,
                "lockDigest": "sha256:" + "9" * 64,
            }
        },
        "environments": {"production": environment_identity(values)},
        "patrolCommandEnvelope": None,
    }


def _readback_manifest(
    *, projection_root: Path, expectation_digest: str
) -> dict[str, Any]:
    return {
        "schema": READBACK_SCHEMA,
        "expectationDigest": expectation_digest,
        "projectionRoot": str(projection_root),
        "sourceManifestDigest": "sha256:" + "1" * 64,
        "components": {
            "productionPub": {
                "manifestDigest": "sha256:" + "5" * 64,
                "treeDigest": "sha256:" + "6" * 64,
                "entryCount": 7,
                "directoryCount": 8,
                "lockDigest": "sha256:" + "9" * 64,
            }
        },
        "patrolCommandEnvelopeDigest": None,
    }


def test_historical_expectation_and_readbacks_survive_projection_cleanup(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    source_manifest = attempt / "input-capsule-manifest.json"
    source_manifest.write_text("{}\n", encoding="utf-8")
    with tempfile.TemporaryDirectory(dir=tmp_path) as raw_projection:
        projection_root = Path(raw_projection) / "repo"
        projection_root.mkdir()
        expectation_path = attempt / "dependency-projection-expectation.json"
        expectation_digest = _write_private(
            expectation_path,
            _expectation_manifest(
                projection_root=projection_root,
                source_manifest=source_manifest,
            ),
        )
        readback = _readback_manifest(
            projection_root=projection_root,
            expectation_digest=expectation_digest,
        )
        prebuild_path = attempt / "dependency-projection-prebuild-readback.json"
        postbuild_path = attempt / "dependency-projection-postbuild-readback.json"
        prebuild_digest = _write_private(prebuild_path, readback)
        postbuild_digest = _write_private(postbuild_path, readback)

    assert not projection_root.exists()
    _validate_persisted_dependency_evidence(
        attempt_dir=attempt,
        deleted_projection_root=projection_root,
        evidence={
            "dependencyProjectionExpectationRef": str(expectation_path),
            "dependencyProjectionExpectationDigest": expectation_digest,
            "dependencyProjectionPrebuildReadbackRef": str(prebuild_path),
            "dependencyProjectionPrebuildReadbackDigest": prebuild_digest,
            "dependencyProjectionPostbuildReadbackRef": str(postbuild_path),
            "dependencyProjectionPostbuildReadbackDigest": postbuild_digest,
        },
    )
    historical = load_historical_dependency_projection_cas_evidence(
        evidence_path=expectation_path,
        expected_digest=expectation_digest,
    )
    assert historical.projection_root == projection_root
    for path, digest in (
        (prebuild_path, prebuild_digest),
        (postbuild_path, postbuild_digest),
    ):
        loaded = load_dependency_projection_cas_readback(
            evidence_path=path,
            expected_digest=digest,
            expected_expectation_digest=expectation_digest,
        )
        assert loaded.manifest == readback
    with pytest.raises(ValueError, match="projection root is unavailable"):
        load_dependency_projection_cas_evidence(
            projection_root=projection_root,
            evidence_path=expectation_path,
            expected_digest=expectation_digest,
        )


def test_source_identity_reads_canonical_package_input_closure_fields(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "baselineId": "sha256:" + "1" * 64,
                "deploymentInputDigest": "sha256:" + "2" * 64,
                "deploymentInputFileCount": 1,
                "entries": [
                    {
                        "logicalPath": COMPONENT_LOGICAL_PATHS["productionPub"],
                        "digest": "sha256:" + "3" * 64,
                        "size": 9,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    source = source_identity(manifest)

    assert source["inputDigest"] == "sha256:" + "2" * 64
    assert source["inputCount"] == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(schema="wrong"),
        lambda value: value.update(projectionRoot="relative/projection"),
        lambda value: value.update(source={}),
        lambda value: value["components"]["productionPub"].update(treePath="/tmp"),
        lambda value: value["environments"]["production"].update(
            digest="sha256:" + "0" * 64
        ),
    ],
    ids=("schema", "projection-root", "source", "components", "environments"),
)
def test_historical_expectation_rejects_structural_drift(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest = _expectation_manifest(
        projection_root=tmp_path / "deleted-projection",
        source_manifest=source,
    )
    mutate(manifest)
    path = tmp_path / "expectation.json"
    digest = _write_private(path, manifest)

    with pytest.raises(ValueError, match="projection_expectation_invalid"):
        load_historical_dependency_projection_cas_evidence(
            evidence_path=path,
            expected_digest=digest,
        )


@pytest.mark.parametrize("fault", ("mode", "hardlink", "digest", "canonical"))
def test_historical_expectation_rejects_non_private_or_noncanonical_bytes(
    tmp_path: Path,
    fault: str,
) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest = _expectation_manifest(
        projection_root=tmp_path / "deleted-projection",
        source_manifest=source,
    )
    path = tmp_path / "expectation.json"
    digest = _write_private(path, manifest)
    if fault == "mode":
        path.chmod(0o644)
    elif fault == "hardlink":
        os.link(path, tmp_path / "second-link.json")
    elif fault == "digest":
        digest = "sha256:" + "0" * 64
    else:
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        path.chmod(0o600)
        digest = _digest(path.read_bytes())

    with pytest.raises(ValueError, match="projection_expectation_invalid"):
        load_historical_dependency_projection_cas_evidence(
            evidence_path=path,
            expected_digest=digest,
        )
