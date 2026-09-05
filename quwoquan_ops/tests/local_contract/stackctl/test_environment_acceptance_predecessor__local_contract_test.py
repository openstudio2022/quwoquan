"""首次环境 mutation 的前驱 acceptance 门禁本地契约。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006.t1
spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006.t2
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import environment_acceptance_predecessor as subject
from quwoquan_ops.cli.lib import environment_acceptance_fact as facts

RELEASE_ID = "release-a"
RELEASE_DIGEST = "sha256:" + "a" * 64
FACT_ID = "sha256:" + "b" * 64


def _minimal_fact(environment: str = "alpha") -> dict[str, object]:
    return {
        "schema": facts.SCHEMA,
        "factId": FACT_ID,
        "acceptanceProfile": "environment_promotion",
        "environment": environment,
        "target": f"{environment}-local",
        "releaseId": RELEASE_ID,
        "releaseDigest": RELEASE_DIGEST,
        "releaseUatSamplePlanRef": "plan.json",
        "releaseUatSamplePlanDigest": "sha256:" + "c" * 64,
        "targetBindingRefs": [],
        "requiredRawResults": [],
        "dataReadiness": {"ref": "data.json", "digest": "sha256:" + "d" * 64},
        "activeCas": {
            "ref": "cas.json",
            "digest": "sha256:" + "e" * 64,
            "readbackRef": "cas-readback.json",
            "readbackDigest": "sha256:" + "f" * 64,
            "releaseId": RELEASE_ID,
            "releaseDigest": RELEASE_DIGEST,
        },
        "lifecycleExit": {"ref": "exit.json", "digest": "sha256:" + "1" * 64},
        "providerReadiness": [{"ref": "provider.json", "digest": "sha256:" + "2" * 64}],
        "observabilityReadiness": [
            {"ref": "observability.json", "digest": "sha256:" + "3" * 64}
        ],
        "rollbackReadiness": {
            "ref": "rollback.json",
            "digest": "sha256:" + "4" * 64,
        },
        "predecessorAcceptance": None,
        "resourceFinalization": {
            "leaseRevocationRefs": [],
            "lockReleaseRefs": [],
            "gcProtectionRefs": [],
        },
        "prodReleaseFacts": None,
        "createdAt": "2026-08-29T07:00:00Z",
        "sourceFingerprint": "sha256:" + "5" * 64,
    }


def _write_raw(
    root: Path,
    *,
    payload: dict[str, object] | None = None,
    raw: bytes | None = None,
    ref: str = "facts/alpha.json",
) -> tuple[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = raw if raw is not None else json.dumps(payload or _minimal_fact()).encode()
    path.write_bytes(encoded)
    return ref, "sha256:" + hashlib.sha256(encoded).hexdigest()


def _patch_canonical_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        facts,
        "validate_environment_acceptance_fact",
        lambda payload, **_kwargs: dict(payload),
    )


def _validate(
    root: Path,
    *,
    environment: str = "beta",
    ref: str | None,
    digest: str | None,
    fact_id: str | None = FACT_ID,
    release_id: str = RELEASE_ID,
    release_digest: str = RELEASE_DIGEST,
):
    return subject.validate_predecessor_acceptance(
        environment=environment,
        release_id=release_id,
        release_digest=release_digest,
        predecessor_ref=ref,
        predecessor_digest=digest,
        predecessor_fact_id=fact_id,
        evidence_root=root,
    )


def test_alpha_accepts_only_none_without_reading_evidence_root(tmp_path: Path) -> None:
    assert (
        _validate(
            tmp_path / "missing",
            environment="alpha",
            ref=None,
            digest=None,
            fact_id=None,
            release_id="not-read",
            release_digest="not-read",
        )
        is None
    )
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="alpha"):
        _validate(
            tmp_path,
            environment="alpha",
            ref="facts/alpha.json",
            digest="sha256:" + "0" * 64,
        )


@pytest.mark.parametrize(
    ("environment", "predecessor"),
    [("beta", "alpha"), ("gamma", "beta"), ("prod", "gamma")],
)
def test_exact_chain_returns_typed_normalized_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    predecessor: str,
) -> None:
    _patch_canonical_validation(monkeypatch)
    payload = _minimal_fact(predecessor)
    ref, digest = _write_raw(
        tmp_path, payload=payload, ref=f"facts/{predecessor}.json"
    )

    assert _validate(
        tmp_path, environment=environment, ref=ref, digest=digest
    ) == {
        "environment": predecessor,
        "factId": FACT_ID,
        "ref": ref,
        "digest": digest,
    }


@pytest.mark.parametrize(
    ("ref", "digest", "fact_id"),
    [
        (None, None, None),
        ("facts/alpha.json", None, FACT_ID),
        (None, "sha256:" + "0" * 64, FACT_ID),
        ("facts/alpha.json", "sha256:" + "0" * 64, None),
    ],
)
def test_nonalpha_requires_exact_fact_id_ref_and_digest(
    tmp_path: Path, ref: str | None, digest: str | None, fact_id: str | None
) -> None:
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="requires|together"):
        _validate(tmp_path, ref=ref, digest=digest, fact_id=fact_id)


def test_digest_wrong_order_fact_id_and_release_identity_drift_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_canonical_validation(monkeypatch)
    ref, digest = _write_raw(tmp_path, payload=_minimal_fact("gamma"))
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="identity drifted"):
        _validate(tmp_path, ref=ref, digest=digest)

    root = tmp_path / "alpha"
    ref, digest = _write_raw(root)
    for kwargs in (
        {"digest": "sha256:" + "9" * 64},
        {"fact_id": "sha256:" + "8" * 64},
        {"release_id": "release-b"},
        {"release_digest": "sha256:" + "7" * 64},
    ):
        arguments = {"ref": ref, "digest": digest, **kwargs}
        with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="drift"):
            _validate(root, **arguments)


def test_duplicate_key_unknown_schema_and_fact_id_are_rejected_before_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    encoded = json.dumps(_minimal_fact())
    duplicate = encoded.replace(
        f'"schema": "{facts.SCHEMA}"',
        f'"schema": "{facts.SCHEMA}", "schema": "{facts.SCHEMA}"',
        1,
    ).encode()
    ref, digest = _write_raw(tmp_path / "duplicate", raw=duplicate)
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="duplicate JSON key"):
        _validate(tmp_path / "duplicate", ref=ref, digest=digest)

    canonical_keys = set(_minimal_fact())

    def validate_shape(payload, **_kwargs):
        if payload.get("schema") != facts.SCHEMA:
            raise facts.EnvironmentAcceptanceFactError(
                "OPS.ENVIRONMENT_ACCEPTANCE_FACT.invalid", "schema is unknown"
            )
        if set(payload) != canonical_keys:
            raise facts.EnvironmentAcceptanceFactError(
                "OPS.ENVIRONMENT_ACCEPTANCE_FACT.invalid", "fields are unknown"
            )
        return dict(payload)

    monkeypatch.setattr(facts, "validate_environment_acceptance_fact", validate_shape)
    value = _minimal_fact()
    value["schema"] = "unknown"
    ref, digest = _write_raw(tmp_path / "schema", payload=value)
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="schema is unknown"):
        _validate(tmp_path / "schema", ref=ref, digest=digest)

    value = _minimal_fact()
    value["unknown"] = True
    ref, digest = _write_raw(tmp_path / "unknown", payload=value)
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="fields are unknown"):
        _validate(tmp_path / "unknown", ref=ref, digest=digest)

    value = _minimal_fact()
    value["factId"] = "sha256:" + "6" * 64
    ref, digest = _write_raw(tmp_path / "fact-id", payload=value)
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="identity drifted"):
        _validate(tmp_path / "fact-id", ref=ref, digest=digest)


def test_symlink_root_parent_and_file_are_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    ref, digest = _write_raw(real_root)
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="non-symlink"):
        _validate(linked_root, ref=ref, digest=digest)

    outside = tmp_path / "outside"
    _write_raw(outside, ref="alpha.json")
    parent_root = tmp_path / "parent"
    parent_root.mkdir()
    (parent_root / "facts").symlink_to(outside, target_is_directory=True)
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="linked"):
        _validate(parent_root, ref="facts/alpha.json", digest=digest)

    file_root = tmp_path / "file"
    real_ref, real_digest = _write_raw(file_root, ref="real/alpha.json")
    linked_file = file_root / "facts/alpha.json"
    linked_file.parent.mkdir()
    linked_file.symlink_to(file_root / real_ref)
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="linked"):
        _validate(file_root, ref="facts/alpha.json", digest=real_digest)


@pytest.mark.parametrize("ref", ["../alpha.json", "/tmp/alpha.json", "facts/../alpha.json"])
def test_ref_is_explicit_relative_and_contained(tmp_path: Path, ref: str) -> None:
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="contained"):
        _validate(tmp_path, ref=ref, digest="sha256:" + "0" * 64)


def test_no_latest_discovery_occurs(tmp_path: Path) -> None:
    _write_raw(tmp_path, ref="facts/latest.json")
    with pytest.raises(subject.EnvironmentAcceptancePredecessorError, match="requires"):
        _validate(tmp_path, ref=None, digest=None, fact_id=None)
