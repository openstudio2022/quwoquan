"""TargetUatBinding strict authoring and create-once storage tests.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-005
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from quwoquan_ops.cli.lib.target_uat_binding import (
    TARGET_UAT_BINDING_SCHEMA,
    TargetUatBindingError,
    build_target_uat_binding,
    canonical_target_uat_binding_bytes,
    read_target_uat_binding,
    target_uat_binding_digest,
    target_uat_binding_id,
    target_uat_binding_ref,
    validate_target_uat_binding,
    write_create_once_target_uat_binding,
)

ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = ROOT / "quwoquan_ops/environments/evidence/target_uat_binding.schema.json"


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _runtime(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "environment": "alpha",
        "target": "alpha-local",
        "releaseId": "release-a",
        "manifestDigest": _digest("1"),
        "candidateDigest": _digest("2"),
        "packageDigest": _digest("3"),
        "runtimeConfigDigest": _digest("4"),
        "environmentRuntimeDigest": _digest("5"),
        "startupIdentity": {"configurationDigest": _digest("6")},
    }
    value.update(overrides)
    return value


def _launch(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "environment": "alpha",
        "target": "alpha-local",
        "platform": "android",
        "deviceId": "emulator-5554",
        "artifactDigest": _digest("7"),
        "applicationId": "com.leadwise.quwoquan.nonprod.debug",
    }
    value.update(overrides)
    return value


def _sample_plan(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "releaseId": "release-a",
        "releaseUatSamplePlanRef": "data/releases/release-a/uat-sample-plan.json",
        "releaseUatSamplePlanDigest": _digest("8"),
    }
    value.update(overrides)
    return value


def _provider(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "identity": "first-party-https",
        "class": "first_party",
        "type": "https",
        "registered": False,
        "conformanceEvidence": {
            "ref": "env/alpha/provider/conformance.json",
            "digest": _digest("f"),
        },
    }
    value.update(overrides)
    return value


def _device(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "identity": "emulator-5554",
        "class": "emulator",
        "registered": False,
    }
    value.update(overrides)
    return value


def _runner(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "identity": "app-content-uat",
        "sourcePath": "quwoquan_ops/tests/acceptance/user_acceptance/app_content_uat.py",
        "digest": _digest("9"),
        "registered": False,
    }
    value.update(overrides)
    return value


def _binding(**overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "runtime_binding": _runtime(),
        "launch_binding": _launch(),
        "sample_plan_binding": _sample_plan(),
        "active_cas": {
            "ref": "env/alpha/runs/activation/active-cas.json",
            "digest": _digest("a"),
        },
        "readback": {
            "ref": "env/alpha/runs/activation/readback.json",
            "digest": _digest("b"),
        },
        "artifact_class": "production_behavior",
        "build_mode": "debug",
        "build_profile": "nonprod",
        "provider": _provider(),
        "device": _device(),
        "runner": _runner(),
        "profile": "rehearsal",
        "non_promotable": True,
        "created_at": "2026-08-29T07:00:00Z",
    }
    arguments.update(overrides)
    return build_target_uat_binding(**arguments)  # type: ignore[arg-type]


def _schema_validator() -> Draft202012Validator:
    assert SCHEMA_PATH is not None, "TargetUatBinding schema is missing"
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_builder_emits_complete_schema_valid_binding_and_canonical_newline() -> None:
    binding = _binding()
    _schema_validator().validate(binding)
    assert binding["schema"] == TARGET_UAT_BINDING_SCHEMA
    assert binding["device"] == _device()
    assert binding["runner"] == _runner()
    assert binding["activeCas"]["digest"] == _digest("a")  # type: ignore[index]
    assert binding["readback"]["digest"] == _digest("b")  # type: ignore[index]
    assert binding["environmentRuntimeDigest"] == _digest("5")

    encoded = canonical_target_uat_binding_bytes(binding)
    assert encoded.endswith(b"\n") and not encoded.endswith(b"\n\n")
    assert encoded == (
        json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    assert target_uat_binding_digest(binding) == (
        "sha256:" + hashlib.sha256(encoded).hexdigest()
    )
    assert target_uat_binding_digest(encoded) == target_uat_binding_digest(binding)


def test_json_schema_matches_closed_shape_and_profile_constraints() -> None:
    validator = _schema_validator()
    binding = _binding()

    unknown = dict(binding)
    unknown["promotable"] = False
    with pytest.raises(ValidationError):
        validator.validate(unknown)

    invalid_rehearsal = dict(binding)
    invalid_rehearsal["device"] = _device(**{"class": "physical"}, registered=True)
    with pytest.raises(ValidationError):
        validator.validate(invalid_rehearsal)

    invalid_production = dict(binding)
    invalid_production.update(
        {
            "profile": "production",
            "nonPromotable": False,
        }
    )
    with pytest.raises(ValidationError):
        validator.validate(invalid_production)


def test_binding_id_is_derived_from_exact_slot_and_recomputed_by_validator() -> None:
    binding = _binding()
    expected = target_uat_binding_id(
        target="alpha-local",
        release_id="release-a",
        release_digest=_digest("1"),
        platform="android",
        provider=_provider(),
        device_identity="emulator-5554",
        profile="rehearsal",
        runner=_runner(),
    )
    assert binding["bindingId"] == expected
    assert target_uat_binding_ref(binding) == f"target-uat-bindings/{expected}.json"

    arbitrary = dict(binding)
    arbitrary["bindingId"] = _digest("f")
    with pytest.raises(TargetUatBindingError, match="slot identity"):
        validate_target_uat_binding(arbitrary)

    for field, changed in (
        ("target", "beta-local"),
        ("releaseId", "release-b"),
        ("platform", "ios"),
        ("profile", "promotable"),
    ):
        drifted = dict(binding)
        drifted[field] = changed
        with pytest.raises(TargetUatBindingError, match="bindingId|profile"):
            validate_target_uat_binding(drifted)


def test_provider_runner_and_device_are_part_of_slot_identity() -> None:
    original = _binding()["bindingId"]
    provider_identity_changed = _binding(
        provider=_provider(identity="first-party-https-v2")
    )["bindingId"]
    provider_class_changed = _binding(
        provider=_provider(**{"class": "external"})
    )["bindingId"]
    provider_type_changed = _binding(
        provider=_provider(**{"type": "device_lab"})
    )["bindingId"]
    provider_evidence_changed = _binding(
        provider=_provider(
            conformanceEvidence={
                "ref": "env/alpha/provider/conformance-v2.json",
                "digest": _digest("e"),
            }
        )
    )["bindingId"]
    runner_changed = _binding(runner=_runner(digest=_digest("c")))["bindingId"]
    device_changed = _binding(
        launch_binding=_launch(deviceId="emulator-5556"),
        device=_device(identity="emulator-5556"),
    )["bindingId"]
    assert len(
        {
            original,
            provider_identity_changed,
            provider_class_changed,
            provider_type_changed,
            provider_evidence_changed,
            runner_changed,
            device_changed,
        }
    ) == 7


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda value: value.update({"unknown": "x"}), "unknown"),
        (lambda value: value.pop("readback"), "missing"),
        (lambda value: value.update({"packageDigest": "7" * 64}), "packageDigest"),
        (
            lambda value: value["artifact"].update({"unknown": "x"}),  # type: ignore[union-attr]
            "artifact.*unknown",
        ),
        (
            lambda value: value["provider"].update({"identity": ""}),  # type: ignore[union-attr]
            "provider.identity",
        ),
        (
            lambda value: value["provider"].update({"class": "unknown"}),  # type: ignore[union-attr]
            "provider.class",
        ),
        (
            lambda value: value["provider"]["conformanceEvidence"].update(  # type: ignore[index,union-attr]
                {"digest": "f" * 64}
            ),
            "provider.conformanceEvidence.digest",
        ),
        (
            lambda value: value["device"].update({"class": "virtual"}),  # type: ignore[union-attr]
            "device.class",
        ),
        (
            lambda value: value["runner"].update({"digest": "9" * 64}),  # type: ignore[union-attr]
            "runner.digest",
        ),
        (
            lambda value: value.update({"releaseUatSamplePlanRef": "../plan.json"}),
            "contained relative",
        ),
        (
            lambda value: value["activeCas"].update(
                {"ref": "https://secret.example/x"}
            ),  # type: ignore[union-attr]
            "URL",
        ),
    ),
)
def test_validator_rejects_unknown_missing_digest_and_unsafe_refs(
    mutation: Callable[[dict[str, object]], object], message: str
) -> None:
    binding = _binding()
    mutation(binding)
    with pytest.raises(TargetUatBindingError, match=message):
        validate_target_uat_binding(binding)


def test_expected_binding_rejects_stale_nested_and_top_level_facts() -> None:
    binding = _binding()
    validate_target_uat_binding(
        binding,
        expected_bindings={
            "target": "alpha-local",
            "releaseId": "release-a",
            "activeCas": {"digest": _digest("a")},
            "readback": {"digest": _digest("b")},
            "artifact": {"digest": _digest("7")},
        },
    )
    for expected in (
        {"releaseId": "release-b"},
        {"activeCas": {"digest": _digest("c")}},
        {"readback": {"digest": _digest("d")}},
    ):
        with pytest.raises(TargetUatBindingError, match="stale"):
            validate_target_uat_binding(binding, expected_bindings=expected)


def test_rehearsal_only_allows_nonpromotable_emulator_or_simulator() -> None:
    validate_target_uat_binding(_binding())
    validate_target_uat_binding(
        _binding(
            launch_binding=_launch(platform="ios", deviceId="ios-sim-a"),
            device=_device(identity="ios-sim-a", **{"class": "simulator"}),
        )
    )
    for changed in (
        {"device": _device(**{"class": "physical"}, registered=True)},
        {"non_promotable": False},
        {"artifact_class": "production"},
    ):
        arguments = dict(changed)
        with pytest.raises(TargetUatBindingError, match="rehearsal"):
            _binding(**arguments)


def test_promotable_requires_registered_physical_production_behavior() -> None:
    promotable = _binding(
        launch_binding=_launch(deviceId="pixel-uat-01"),
        device=_device(
            identity="pixel-uat-01", **{"class": "physical"}, registered=True
        ),
        provider=_provider(registered=True),
        runner=_runner(registered=True),
        profile="promotable",
        non_promotable=False,
    )
    validate_target_uat_binding(promotable)
    _schema_validator().validate(promotable)
    for changed in (
        {
            "device": _device(
                identity="pixel-uat-01", **{"class": "physical"}, registered=False
            )
        },
        {
            "device": _device(
                identity="pixel-uat-01", **{"class": "emulator"}, registered=True
            )
        },
        {"provider": _provider(registered=False)},
        {"runner": _runner(registered=False)},
        {"non_promotable": True},
        {"artifact_class": "production"},
    ):
        arguments: dict[str, object] = {
            "launch_binding": _launch(deviceId="pixel-uat-01"),
            "device": _device(
                identity="pixel-uat-01", **{"class": "physical"}, registered=True
            ),
            "provider": _provider(registered=True),
            "runner": _runner(registered=True),
            "profile": "promotable",
            "non_promotable": False,
        }
        arguments.update(changed)
        with pytest.raises(TargetUatBindingError, match="promotable"):
            _binding(**arguments)


def test_production_is_prod_registered_physical_release_prod_only() -> None:
    production = _binding(
        runtime_binding=_runtime(environment="prod", target="prod-hosted"),
        launch_binding=_launch(
            environment="prod",
            target="prod-hosted",
            platform="ios",
            deviceId="ios-prod-01",
        ),
        device=_device(
            identity="ios-prod-01", **{"class": "physical"}, registered=True
        ),
        artifact_class="production",
        build_mode="release",
        build_profile="prod",
        provider=_provider(registered=True),
        runner=_runner(registered=True),
        profile="production",
        non_promotable=False,
    )
    validate_target_uat_binding(production)
    _schema_validator().validate(production)
    for changed in (
        {"runtime_binding": _runtime(environment="gamma", target="gamma-local")},
        {"artifact_class": "production_behavior"},
        {"build_mode": "debug"},
        {"build_profile": "nonprod"},
        {"non_promotable": True},
    ):
        arguments: dict[str, object] = {
            "runtime_binding": _runtime(environment="prod", target="prod-hosted"),
            "launch_binding": _launch(
                environment="prod",
                target="prod-hosted",
                platform="ios",
                deviceId="ios-prod-01",
            ),
            "device": _device(
                identity="ios-prod-01", **{"class": "physical"}, registered=True
            ),
            "artifact_class": "production",
            "build_mode": "release",
            "build_profile": "prod",
            "provider": _provider(registered=True),
            "runner": _runner(registered=True),
            "profile": "production",
            "non_promotable": False,
        }
        arguments.update(changed)
        runtime = arguments["runtime_binding"]
        if changed.get("runtime_binding") is not None and isinstance(runtime, dict):
            arguments["launch_binding"] = _launch(
                environment=runtime["environment"],
                target=runtime["target"],
                platform="ios",
                deviceId="ios-prod-01",
            )
        with pytest.raises(TargetUatBindingError, match="production"):
            _binding(**arguments)


def test_prod_rejects_nonproduction_profile() -> None:
    with pytest.raises(TargetUatBindingError, match="prod target"):
        _binding(
            runtime_binding=_runtime(environment="prod", target="prod-hosted"),
            launch_binding=_launch(
                environment="prod", target="prod-hosted", deviceId="pixel-prod"
            ),
            device=_device(
                identity="pixel-prod", **{"class": "physical"}, registered=True
            ),
            provider=_provider(registered=True),
            runner=_runner(registered=True),
            profile="promotable",
            non_promotable=False,
        )


def test_create_once_uses_canonical_slot_path_and_exact_byte_replay(
    tmp_path: Path,
) -> None:
    binding = _binding()
    first = write_create_once_target_uat_binding(output_root=tmp_path, binding=binding)
    assert first.created is True
    assert first.ref == target_uat_binding_ref(binding)
    assert first.path == tmp_path / first.ref
    assert first.path.read_bytes() == canonical_target_uat_binding_bytes(binding)
    assert first.digest == target_uat_binding_digest(binding)
    original_inode = first.path.stat().st_ino

    replay = write_create_once_target_uat_binding(
        output_root=tmp_path, binding=dict(binding)
    )
    assert replay.created is False
    assert replay.path.stat().st_ino == original_inode
    assert read_target_uat_binding(first.path) == binding

    drifted = dict(binding)
    drifted["createdAt"] = "2026-08-29T07:01:00Z"
    with pytest.raises(TargetUatBindingError, match="different bytes"):
        write_create_once_target_uat_binding(output_root=tmp_path, binding=drifted)


def test_create_once_rejects_noncanonical_existing_bytes(tmp_path: Path) -> None:
    binding = _binding()
    reference = target_uat_binding_ref(binding)
    path = tmp_path / reference
    path.parent.mkdir()
    path.write_text(
        json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(TargetUatBindingError, match="different bytes"):
        write_create_once_target_uat_binding(output_root=tmp_path, binding=binding)


def test_read_rejects_duplicate_key_and_missing_newline(tmp_path: Path) -> None:
    binding = _binding()
    encoded = canonical_target_uat_binding_bytes(binding)
    duplicate = encoded[:-2] + b',"schema":"quwoquan_ops.target_uat_binding.v1"}\n'
    path = tmp_path / "duplicate.json"
    path.write_bytes(duplicate)
    with pytest.raises(TargetUatBindingError, match="duplicate"):
        read_target_uat_binding(path)
    with pytest.raises(TargetUatBindingError, match="newline"):
        target_uat_binding_digest(encoded[:-1])


def test_create_once_rejects_destination_and_parent_symlinks(tmp_path: Path) -> None:
    binding = _binding()
    store = tmp_path / "target-uat-bindings"
    store.mkdir()
    occupied = tmp_path / "occupied.json"
    occupied.write_bytes(canonical_target_uat_binding_bytes(binding))
    destination = tmp_path / target_uat_binding_ref(binding)
    destination.symlink_to(occupied)
    with pytest.raises(TargetUatBindingError, match="non-symlink"):
        write_create_once_target_uat_binding(output_root=tmp_path, binding=binding)

    destination.unlink()
    store.rmdir()
    real_store = tmp_path / "real-store"
    real_store.mkdir()
    store.symlink_to(real_store, target_is_directory=True)
    with pytest.raises(TargetUatBindingError, match="real directory"):
        write_create_once_target_uat_binding(output_root=tmp_path, binding=binding)


def test_same_slot_under_different_binding_path_fails_closed(tmp_path: Path) -> None:
    binding = _binding()
    store = tmp_path / "target-uat-bindings"
    store.mkdir()
    alias = store / "sha256-legacy-alias.json"
    alias.write_bytes(canonical_target_uat_binding_bytes(binding))
    with pytest.raises(TargetUatBindingError, match="noncanonical path|same slot"):
        write_create_once_target_uat_binding(output_root=tmp_path, binding=binding)


def test_create_once_requires_real_output_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(TargetUatBindingError, match="real directory"):
        write_create_once_target_uat_binding(
            output_root=linked_root, binding=_binding()
        )
