# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
"""M1000 sampling authority is exact-byte, authenticated, and projection-only."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.release_uat_sampling_authority import (  # noqa: E402
    ReleaseUatSamplingAuthorityError,
    exact_document_bytes,
    project_release_uat_sampling_authority,
)

RELEASE_DIGEST = "sha256:" + "1" * 64
AUTH_DIGEST = "sha256:" + "2" * 64
CLI = ROOT / "quwoquan_data" / "scripts" / "cli.py"


def _write(root: Path, ref: str, value: dict[str, object]) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    return {"ref": ref, "digest": "sha256:" + hashlib.sha256(raw).hexdigest()}


def _inputs(root: Path) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    strategy = {
        "schema": "quwoquan_data.m1000_app_uat_sampling_strategy",
        "strategyId": "m1000-joint-v1",
        "milestone": "M1000",
        "releaseId": "release-m1000",
        "releaseDigest": RELEASE_DIGEST,
        "sampleDistribution": {"homepage": 13, "article": 17, "image": 19, "video": 7},
        "selector": {"name": "stratified_exact", "version": 1, "sortKey": "identity", "direction": "ascending"},
        "createdAt": "2026-08-30T00:00:00Z",
    }
    strategy_ref = _write(root, "authority/strategy.json", strategy)
    def readback(role: str, authority: str) -> dict[str, object]:
        return {
            "schema": "quwoquan_data.m1000_app_uat_sampling_authority_readback",
            "role": role,
            "authorityId": authority,
            "authenticationContextDigest": AUTH_DIGEST,
            "decision": "approved",
            "strategyRef": strategy_ref["ref"],
            "strategyDigest": strategy_ref["digest"],
            "releaseId": "release-m1000",
            "releaseDigest": RELEASE_DIGEST,
            "observedAt": "2026-08-30T00:01:00Z",
        }
    product = _write(root, "authority/product.json", readback("product_owner", "product-a"))
    quality = _write(root, "authority/quality.json", readback("quality_owner", "quality-b"))
    return strategy_ref, product, quality


def test_projection__binds_exact_strategy_and_distinct_authenticated_authorities(tmp_path: Path) -> None:
    strategy, product, quality = _inputs(tmp_path)
    result = project_release_uat_sampling_authority(
        artifact_root=tmp_path,
        release_id="release-m1000",
        release_digest=RELEASE_DIGEST,
        strategy_binding=strategy,
        product_owner_readback=product,
        quality_owner_readback=quality,
    )
    assert result["strategy"]["sampleDistribution"] == {
        "homepage": 13, "article": 17, "image": 19, "video": 7,
    }
    assert result["productOwner"]["role"] == "product_owner"
    assert result["qualityOwner"]["role"] == "quality_owner"


def test_projection__fails_closed_without_authority_or_with_drift(tmp_path: Path) -> None:
    strategy, product, quality = _inputs(tmp_path)
    with pytest.raises(ReleaseUatSamplingAuthorityError, match="AUTHORITY_MISSING"):
        project_release_uat_sampling_authority(
            artifact_root=tmp_path,
            release_id="release-m1000",
            release_digest=RELEASE_DIGEST,
            strategy_binding=None,
            product_owner_readback=product,
            quality_owner_readback=quality,
        )
    product_path = tmp_path / product["ref"]
    payload = json.loads(product_path.read_text())
    payload["strategyDigest"] = "sha256:" + "9" * 64
    product = _write(tmp_path, product["ref"], payload)
    with pytest.raises(ReleaseUatSamplingAuthorityError, match="identity drifted"):
        project_release_uat_sampling_authority(
            artifact_root=tmp_path,
            release_id="release-m1000",
            release_digest=RELEASE_DIGEST,
            strategy_binding=strategy,
            product_owner_readback=product,
            quality_owner_readback=quality,
        )



def _run_cli(
    root: Path,
    strategy: dict[str, str],
    product: dict[str, str],
    quality: dict[str, str],
    *,
    release_id: str = "release-m1000",
    output: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-B",
        str(CLI),
        "release",
        "project-uat-sampling-authority",
        "--artifact-root",
        str(root),
        "--release-id",
        release_id,
        "--release-digest",
        RELEASE_DIGEST,
        "--strategy-ref",
        strategy["ref"],
        "--strategy-digest",
        strategy["digest"],
        "--product-readback-ref",
        product["ref"],
        "--product-readback-digest",
        product["digest"],
        "--quality-readback-ref",
        quality["ref"],
        "--quality-readback-digest",
        quality["digest"],
    ]
    if output is not None:
        command.extend(("--output", str(output)))
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_cli_projection__happy_fixture_create_once_and_never_discovers_latest(
    tmp_path: Path,
) -> None:
    strategy, product, quality = _inputs(tmp_path)
    # These tempting aliases must be ignored; the command has no latest lookup path.
    _write(
        tmp_path,
        "authority/latest.json",
        {"schema": "not-an-authority", "releaseId": "release-other"},
    )
    _write(
        tmp_path,
        "latest.json",
        {"schema": "not-an-authority", "releaseId": "release-other"},
    )
    output = tmp_path / "projected/m1000-authority.json"

    first = _run_cli(tmp_path, strategy, product, quality, output=output)
    assert first.returncode == 0, first.stderr
    projected = json.loads(first.stdout)
    assert projected["releaseId"] == "release-m1000"
    assert projected["strategy"]["ref"] == strategy["ref"]
    assert output.read_bytes() == exact_document_bytes(projected)

    second = _run_cli(tmp_path, strategy, product, quality, output=output)
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout) == projected
    assert output.read_bytes() == exact_document_bytes(projected)
    assert "latest" not in first.stdout


def test_cli_projection__missing_readback_is_stable_gate_block(tmp_path: Path) -> None:
    strategy, product, quality = _inputs(tmp_path)
    (tmp_path / quality["ref"]).unlink()

    result = _run_cli(tmp_path, strategy, product, quality)

    assert result.returncode != 0
    assert "GATE_BLOCK" in result.stderr
    assert "unavailable" in result.stderr


def test_cli_projection__same_authenticated_authority_is_rejected(
    tmp_path: Path,
) -> None:
    strategy, product, quality = _inputs(tmp_path)
    quality_path = tmp_path / quality["ref"]
    payload = json.loads(quality_path.read_text())
    payload["authorityId"] = "product-a"
    quality = _write(tmp_path, quality["ref"], payload)

    result = _run_cli(tmp_path, strategy, product, quality)

    assert result.returncode != 0
    assert "GATE_BLOCK" in result.stderr
    assert "distinct authenticated authorities" in result.stderr


def test_cli_projection__exact_digest_and_release_identity_drift_fail_closed(
    tmp_path: Path,
) -> None:
    strategy, product, quality = _inputs(tmp_path)
    digest_drift = _run_cli(
        tmp_path,
        {**strategy, "digest": "sha256:" + "f" * 64},
        product,
        quality,
    )
    assert digest_drift.returncode != 0
    assert "GATE_BLOCK" in digest_drift.stderr
    assert "exact-byte digest drifted" in digest_drift.stderr

    release_drift = _run_cli(
        tmp_path,
        strategy,
        product,
        quality,
        release_id="release-other",
    )
    assert release_drift.returncode != 0
    assert "GATE_BLOCK" in release_drift.stderr
    assert "release identity drifted" in release_drift.stderr


def test_cli_pool_build__declares_projected_authority_exact_pair() -> None:
    result = subprocess.run(
        [sys.executable, "-B", str(CLI), "release", "pool-build", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--sampling-authority-artifact-root" in result.stdout
    assert "--sampling-authority-ref" in result.stdout
    assert "--sampling-authority-digest" in result.stdout
