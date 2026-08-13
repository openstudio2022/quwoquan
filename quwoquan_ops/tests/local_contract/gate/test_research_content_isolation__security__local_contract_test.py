from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from quwoquan_ops.cli.lib.research_content_isolation import (
    verify_research_content_isolation,
)


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _checksum(value: dict[str, object]) -> str:
    return _sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def test_static_runtime_policy_alone_never_passes_research_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """静态 runtime 策略绿永远不等于隔离通过。

    仓库现状下 identity（IssueWhitelistedResearchSession）与 signed-media
    （ReserveOriginalImageAccessGrant + TTL policy）契约都已真实落地，因此缺少
    canonical Data 运行时证据时 blocker 必须是 RUNTIME_PROOF_INCOMPLETE——
    这同时锁定两个前置 adapter 契约仍然存在；任何一个漂移，blocker code 变化，
    本断言即红。identity adapter 缺失的分支用注入缺失单独保持覆盖。
    """
    for environment in ("alpha", "beta", "gamma", "prod"):
        with pytest.raises(
            ValueError,
            match="DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE",
        ):
            verify_research_content_isolation(
                environment,
                release_id="research-release-a",
                verify_run_id="verify-research-a",
                manifest_digest="sha256:" + "1" * 64,
                data_readiness=None,
                data_readiness_path=None,
            )

    import quwoquan_ops.cli.lib.research_content_isolation as isolation

    monkeypatch.setattr(isolation, "_identity_adapter_available", lambda: False)
    for environment in ("alpha", "beta", "gamma", "prod"):
        with pytest.raises(
            ValueError,
            match="DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE",
        ):
            verify_research_content_isolation(
                environment,
                release_id="research-release-a",
                verify_run_id="verify-research-a",
                manifest_digest="sha256:" + "1" * 64,
                data_readiness=None,
                data_readiness_path=None,
            )


def test_missing_whitelist_proof_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = {
        "productLifecycleState": "research",
        "researchContentIsolation": {},
    }
    path = tmp_path / "quwoquan_ops/environments/alpha/runtime.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(runtime), encoding="utf-8")

    import quwoquan_ops.cli.lib.research_content_isolation as isolation

    monkeypatch.setattr(isolation, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="identityWhitelistRequired"):
        isolation.verify_research_content_isolation(
            "alpha",
            release_id="research-release-a",
            verify_run_id="verify-research-a",
            manifest_digest="sha256:" + "1" * 64,
            data_readiness=None,
            data_readiness_path=None,
        )


def test_handwritten_pass_receipt_cannot_bypass_missing_identity_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import quwoquan_ops.cli.lib.research_content_isolation as isolation

    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    release_id = "research-release-a"
    verify_run_id = "verify-research-a"
    manifest_digest = "sha256:" + "1" * 64
    ref = (
        Path("env/alpha/runs/data-release")
        / release_id
        / verify_run_id
        / "research-isolation-verification.json"
    ).as_posix()
    path = tmp_path / ref
    policy_path = isolation.ROOT / "quwoquan_ops/environments/alpha/runtime.yaml"
    receipt: dict[str, object] = {
        "schema": "quwoquan_data.research_isolation_verification",
        "environment": "alpha",
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "verifyRunId": verify_run_id,
        "policyRef": "quwoquan_ops/environments/alpha/runtime.yaml",
        "policySha256": _sha256(policy_path.read_bytes()),
        "outcome": "PASS",
        "subjectHash": "sha256:" + "2" * 64,
        "identityIssuance": {},
        "identityAttestation": {},
        "internalAppReadback": {},
        "anonymousContentProbe": {},
        "anonymousMediaProbe": {},
        "networkExposureReadback": {},
        "deniedCapabilities": {},
        "signedMedia": {},
        "positiveReadback": {},
        "verifiedAt": "2026-08-05T00:00:00Z",
    }
    receipt["verificationChecksum"] = _checksum(receipt)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    readiness = {
        "researchIsolationVerificationRef": ref,
        "researchIsolationVerificationDigest": _sha256(path.read_bytes()),
        "entityRefs": ["entity-a"],
        "postIds": ["post-a"],
        "mediaAssetIds": ["asset-a"],
    }

    # identity 契约现已真实落地；要证明「手写 PASS receipt 绕不过 identity
    # adapter 缺失」，必须注入缺失，而不是依赖仓库恰好没有该契约。
    monkeypatch.setattr(isolation, "_identity_adapter_available", lambda: False)
    with pytest.raises(
        ValueError,
        match="DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE",
    ):
        verify_research_content_isolation(
            "alpha",
            release_id=release_id,
            verify_run_id=verify_run_id,
            manifest_digest=manifest_digest,
            data_readiness=readiness,
            data_readiness_path=path.with_name("release-readiness.json"),
        )

    monkeypatch.setattr(isolation, "_identity_adapter_available", lambda: True)
    monkeypatch.setattr(isolation, "_signed_media_adapter_available", lambda: True)
    with pytest.raises(ValueError, match="runtime decisions"):
        verify_research_content_isolation(
            "alpha",
            release_id=release_id,
            verify_run_id=verify_run_id,
            manifest_digest=manifest_digest,
            data_readiness=readiness,
            data_readiness_path=path.with_name("release-readiness.json"),
        )

    readiness["researchIsolationVerificationDigest"] = "sha256:" + "9" * 64
    with pytest.raises(ValueError, match="file digest drift"):
        verify_research_content_isolation(
            "alpha",
            release_id=release_id,
            verify_run_id=verify_run_id,
            manifest_digest=manifest_digest,
            data_readiness=readiness,
            data_readiness_path=path.with_name("release-readiness.json"),
        )
