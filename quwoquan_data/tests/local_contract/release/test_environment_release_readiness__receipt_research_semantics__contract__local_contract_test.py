"""场景组：research/commercial readiness 语义与激活信封防篡改。

从 test_environment_release_readiness__receipt__contract__local_contract_test.py
按场景拆出；测试逐字搬移，共享 helper 常量留在承接模块。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.release.environment import release_readiness as readiness_subject
from core.io import write_json
from core.release_layout import payload_digest
from core.schema import assert_valid

from quwoquan_data.tests.local_contract.release.test_environment_release_readiness__receipt_environment_scope__contract__local_contract_test import (
    ENTITY_REF,
    ENVIRONMENT,
    NORMALIZED_ENTITY_REF,
    POSTS,
    RELEASE_ID,
    VERIFY_RUN_ID,
    _convert_fixture_to_research,
    _fixture,
    _resign_readiness,
    _semantic_issues,
    _write,
)


def test_environment_release_readiness__research_projects_data_readback_without_guest__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _fixture(tmp_path)
    subject_hash = _convert_fixture_to_research(paths)
    isolation_path = (
        paths["verify"] / "research-isolation-verification.json"
    )
    write_json(isolation_path, {"frozen": True})
    media_manifest = json.loads(
        (paths["release"] / "payload/media_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    isolation = {
        "subjectHash": subject_hash,
        "policyRef": "quwoquan_ops/environments/gamma/runtime.yaml",
        "policySha256": "sha256:" + "7" * 64,
        "positiveReadback": {
            "releaseId": RELEASE_ID,
            "manifestDigest": payload_digest(paths["release"]),
            "subjectHash": subject_hash,
            "entityRefs": [NORMALIZED_ENTITY_REF],
            "postIds": sorted(row[1] for row in POSTS),
            "mediaAssetIds": sorted(
                row["assetId"]
                for row in media_manifest["assets"]
                if any(
                    str(owner_ref).startswith("posts/")
                    for owner_ref in row["ownerRefs"]
                )
            ),
        },
    }

    def _load_isolation(*_args: object, **_kwargs: object) -> dict[str, object]:
        return isolation

    monkeypatch.setattr(
        readiness_subject,
        "load_research_isolation_verification",
        _load_isolation,
    )
    report = json.loads(
        _write(
            tmp_path,
            readiness_phase="research",
            research_isolation_path=isolation_path,
        ).read_text(encoding="utf-8")
    )

    assert report["releaseClass"] == "research"
    assert report["productLifecycleState"] == "research"
    assert report["internalSubjectHash"] == subject_hash
    assert "appUatEnvelope" not in report
    assert "appUatEnvelopeDigest" not in report
    isolation_binding = report["activationEnvelope"][
        "researchIsolationPolicy"
    ]
    assert isolation_binding == {
        "policyRef": "quwoquan_ops/environments/gamma/runtime.yaml",
        "policyDigest": "sha256:" + "7" * 64,
        "verificationRef": (
            f"env/{ENVIRONMENT}/runs/data-release/{RELEASE_ID}/"
            f"{VERIFY_RUN_ID}/research-isolation-verification.json"
        ),
        "verificationDigest": report["researchIsolationVerificationDigest"],
        "subjectHash": subject_hash,
    }
    assert "guestActorHash" not in report
    assert "guestLogin" not in report


def test_environment_release_readiness__activation_envelope_tamper_fails_semantic_recheck__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    readiness = json.loads(_write(tmp_path).read_text(encoding="utf-8"))
    activation = readiness["activationEnvelope"]
    assert isinstance(activation, dict)
    activation["sourceDigest"] = "sha256:" + "0" * 64
    _resign_readiness(readiness)

    issues = _semantic_issues(tmp_path, paths, readiness)

    assert any(
        "activationEnvelope drifts from release/import/readback" in issue
        for issue in issues
    )
    assert all("verificationChecksum drift" not in issue for issue in issues)


def test_environment_release_readiness__semantic_verifier_reprojects_data_activation_envelope__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    readiness = json.loads(_write(tmp_path).read_text(encoding="utf-8"))

    assert _semantic_issues(tmp_path, paths, readiness) == []


def test_environment_release_readiness__resigned_research_release_cannot_masquerade_as_commercial__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    post_report = json.loads(
        (paths["verify"] / "post-api-verification.json").read_text(
            encoding="utf-8"
        )
    )
    readiness = json.loads(_write(tmp_path).read_text(encoding="utf-8"))
    _convert_fixture_to_research(paths)
    write_json(paths["verify"] / "post-api-verification.json", post_report)
    readiness["releaseClass"] = "research"
    readiness["productLifecycleState"] = "research"
    readiness["manifestDigest"] = payload_digest(paths["release"])
    _resign_readiness(readiness)

    with pytest.raises(ValueError, match="schema violation"):
        assert_valid(
            readiness,
            "release",
            "environment_release_readiness",
            label="resigned research commercial masquerade",
        )
    issues = _semantic_issues(
        tmp_path,
        paths,
        readiness,
        post_report=post_report,
    )

    assert any(
        "readinessPhase=commercial requires "
        "releaseClass=productLifecycleState=commercial" in issue
        for issue in issues
    )
    assert all("verificationChecksum drift" not in issue for issue in issues)


def test_environment_release_readiness__rejects_retired_app_uat_authority_fields__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    readiness = json.loads(_write(tmp_path).read_text(encoding="utf-8"))
    readiness["appUatEnvelopeDigest"] = "sha256:" + "a" * 64
    _resign_readiness(readiness)

    with pytest.raises(ValueError, match="schema violation"):
        assert_valid(
            readiness,
            "release",
            "environment_release_readiness",
            label="retired app UAT authority",
        )
