"""Ops UAT M1 acceptance command wiring contracts.

Mechanically split from test_app_uat_evidence_commands__local_contract_test.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_uat_evidence as subject
from quwoquan_ops.cli.lib import environment_acceptance_fact as acceptance

RELEASE_DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64
SPEC_REF = "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006"
RUNNER = "qwq_app.content_uat.feed.article.v1"
PROFILE = {"platform": "android", "deviceProfile": "promotable"}


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _write(root: Path, ref: str, value: object) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(encoded)
    return {"ref": ref, "digest": "sha256:" + hashlib.sha256(encoded).hexdigest()}


from importlib import import_module

_shared = import_module("test_app_uat_evidence_commands__local_contract_test")
_acceptance_arguments = _shared._acceptance_arguments
_m1_acceptance_arguments = _shared._m1_acceptance_arguments
_m1_cli_arguments = _shared._m1_cli_arguments
_raw = _shared._raw


def test_m1_api_consumer_append_is_same_builder_and_create_once(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _m1_acceptance_arguments(root, store)
    first = subject.build_environment_acceptance_append_command(**arguments)
    second = subject.build_environment_acceptance_append_command(**arguments)
    assert first["factId"] == second["factId"]
    assert first["factDigest"] == second["factDigest"]
    fact = json.loads((root / first["factRef"]).read_text(encoding="utf-8"))
    assert fact["acceptanceProfile"] == "m1_api_consumer"
    assert fact["releaseDigest"] == RELEASE_DIGEST
    assert fact["manifestDigest"] == MANIFEST_DIGEST
    assert fact["releaseDigest"] != fact["manifestDigest"]
    assert "targetBindingRefs" not in fact
    assert set(fact["consumerHealth"]) == {"ref", "digest"}
    assert len(fact["requiredRawResults"]) == 16
    assert len(list((store / "alpha").glob("*.json"))) == 1


def test_m1_api_consumer_public_command_rejects_promotion_only_arguments(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _m1_acceptance_arguments(root, store)
    forbidden_cases = (
        ({"required_raw_results": []}, "requiredRawResults must be non-empty"),
        (
            {"required_raw_results": arguments["required_raw_results"][:-1]},
            "exactly 16",
        ),
        (
            {"target_binding_refs": [{"ref": "binding.json"}]},
            "must not provide targetBinding",
        ),
        ({"required_target_profiles": [PROFILE]}, "must not provide requiredProfile"),
        (
            {
                "predecessor_ref": "facts/alpha.json",
                "predecessor_digest": _digest("8"),
                "predecessor_fact_id": _digest("9"),
            },
            "must not provide predecessor",
        ),
        (
            {"prod_release_facts": {"unexpected": "fact"}},
            "must not provide prodReleaseFacts",
        ),
    )
    for changes, message in forbidden_cases:
        with pytest.raises(subject.AppUatEvidenceCommandError, match=message):
            subject.build_environment_acceptance_append_command(
                **{**arguments, **changes}
            )

    first_raw = arguments["required_raw_results"][0]
    first_path = root / first_raw["ref"]
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))
    first_payload["deviceId"] = "forbidden-device"
    first_path.write_text(
        json.dumps(first_payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    first_raw["digest"] = acceptance.exact_byte_digest(first_path)
    arguments["source_fingerprint"] = acceptance.derive_m1_source_fingerprint(
        environment="alpha",
        target="alpha-local",
        release_id="release-a",
        release_digest=RELEASE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
        import_run_id="import-run-a",
        verify_run_id="verify-run-a",
        sample_plan={
            "ref": arguments["sample_plan_ref"],
            "digest": arguments["sample_plan_digest"],
        },
        data_readiness=arguments["data_readiness"],
        consumer_health=arguments["consumer_health"],
        required_raw_results=arguments["required_raw_results"],
    )
    with pytest.raises(
        acceptance.EnvironmentAcceptanceFactError, match="canonical ReadinessCaseResult"
    ):
        subject.build_environment_acceptance_append_command(**arguments)
    assert list(store.iterdir()) == []


def test_environment_promotion_public_command_keeps_existing_authority_requirements(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _acceptance_arguments(root, store)
    for changes, message in (
        ({"target_binding_refs": []}, "requires targetBinding"),
        ({"required_target_profiles": []}, "requires requiredProfile"),
    ):
        with pytest.raises(subject.AppUatEvidenceCommandError, match=message):
            subject.build_environment_acceptance_append_command(
                **{**arguments, **changes}
            )

    beta = {
        **arguments,
        "environment": "beta",
        "target": "beta-local",
        "predecessor_ref": None,
        "predecessor_digest": None,
        "predecessor_fact_id": None,
    }
    with pytest.raises(
        acceptance.EnvironmentAcceptanceFactError, match="requires exact alpha"
    ):
        subject.build_environment_acceptance_append_command(**beta)
    assert list(store.iterdir()) == []


def test_public_stackctl_m1_api_consumer_exact_create_once(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _m1_acceptance_arguments(root, store)
    command = [
        sys.executable,
        "-B",
        str(Path(subject.__file__).parents[1] / "stackctl.py"),
        *_m1_cli_arguments(arguments),
    ]
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(tmp_path / "python-cache"),
    }
    first = subprocess.run(
        command,
        cwd=Path(subject.__file__).parents[3],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        command,
        cwd=Path(subject.__file__).parents[3],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr or first.stdout
    assert second.returncode == 0, second.stderr or second.stdout
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload["factId"] == second_payload["factId"]
    assert first_payload["factDigest"] == second_payload["factDigest"]
    assert len(list((store / "alpha").glob("*.json"))) == 1


def test_predecessor_drift_blocks_before_fact_builder_and_create_once_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _acceptance_arguments(root, store)
    first = subject.build_environment_acceptance_append_command(**arguments)
    second = subject.build_environment_acceptance_append_command(**arguments)
    assert first["factId"] == second["factId"]
    assert len(list((store / "alpha").glob("*.json"))) == 1

    called = False

    def forbidden_builder(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("predecessor must fail before builder")

    monkeypatch.setattr(subject, "build_environment_acceptance_fact", forbidden_builder)
    beta = {
        **arguments,
        "environment": "beta",
        "target": "beta-local",
        "predecessor_ref": first["factRef"],
        "predecessor_digest": _digest("9"),
        "predecessor_fact_id": first["factId"],
    }
    with pytest.raises(
        acceptance.EnvironmentAcceptanceFactError, match="exact bytes drifted"
    ):
        subject.build_environment_acceptance_append_command(**beta)
    assert called is False


def test_m1_cli_rejects_caller_fingerprint_and_wrong_manifest_digest(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _m1_acceptance_arguments(root, store)
    with pytest.raises(subject.AppUatEvidenceCommandError, match="sourceFingerprint"):
        subject.build_environment_acceptance_append_command(
            **{**arguments, "source_fingerprint": _digest("a")}
        )
    with pytest.raises(subject.AppUatEvidenceCommandError, match="sourceFingerprint"):
        subject.build_environment_acceptance_append_command(
            **{**arguments, "manifest_digest": RELEASE_DIGEST}
        )
