"""EnvironmentReleaseOrderView stays a pure projection over facts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006.t1
spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006.t2
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_ops.cli.lib import environment_acceptance_fact as facts
from quwoquan_ops.cli.lib import environment_release_order_view as subject

ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = ROOT / "quwoquan_ops/environments/evidence/environment_release_order_view.schema.json"
RELEASE_DIGEST = "sha256:" + "a" * 64
MANIFEST_DIGEST = "sha256:" + "b" * 64
SPEC_REF = (
    "specs/feature-tree/runtime/runtime-config/"
    "environment-topology-and-packaging/spec.md#gwt-006"
)


def _write_json(root: Path, ref: str, value: object) -> tuple[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return ref, facts.exact_byte_digest(path)


def _fact_arguments(
    root: Path,
    environment: str,
    target: str,
    predecessor: dict[str, str] | None,
) -> dict[str, object]:
    from quwoquan_ops.tests.local_contract.stackctl.test_environment_acceptance_fact__local_contract_test import _evidence

    arguments, _ = _evidence(
        root,
        environment,
        target,
        ({"platform": "android", "deviceProfile": "production"},)
        if environment == "prod"
        else ({"platform": "android", "deviceProfile": "promotable"},),
    )
    arguments["predecessor_acceptance"] = predecessor
    if environment == "prod":
        identity = {
            "environment": environment,
            "target": target,
            "deploymentTarget": target,
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
        }
        def prod_fact(name: str, status: str, **extra: str) -> dict[str, str]:
            ref, digest = _write_json(root, f"evidence/prod/{name}.json", {**identity, "status": status, **extra})
            return {"ref": ref, "digest": digest}
        arguments["prod_release_facts"] = {
            "engineeringEligibility": prod_fact("engineering", "eligible", factType="engineeringEligibility"),
            "durableApproval": prod_fact("approval", "approved", factType="durableApproval"),
            "rolloutStages": [
                {"stage": stage, **prod_fact(f"rollout-{stage}", "completed", factType="rolloutStage", stage=stage)}
                for stage in facts.PROD_ROLLOUT_STAGES
            ],
            "rollbackReadiness": prod_fact("prod-rollback", "ready", factType="rollbackReadiness"),
        }
    return arguments

def _write_fact(
    root: Path,
    environment: str,
    target: str,
    predecessor: dict[str, str] | None,
) -> tuple[str, str]:
    fact = facts.build_environment_acceptance_fact(
        **_fact_arguments(root, environment, target, predecessor)  # type: ignore[arg-type]
    )
    ref = f"facts/{environment}.json"
    store = root / "facts"
    store.mkdir(exist_ok=True)
    path = facts.write_environment_acceptance_fact(
        root=store,
        fact=fact,
        evidence_root=root,
        required_target_profiles=[
            {"platform": item["platform"], "deviceProfile": item["deviceProfile"]}
            for item in fact["targetBindingRefs"]
        ],
    )
    ref = path.relative_to(root).as_posix()
    return ref, facts.exact_byte_digest(path)


def _chain(root: Path, through: str) -> dict[str, str | None]:
    refs: dict[str, str | None] = {name: None for name in facts.ENVIRONMENTS}
    predecessor: dict[str, str] | None = None
    targets = {
        "alpha": "alpha-local",
        "beta": "beta-local",
        "gamma": "gamma-local",
        "prod": "prod-hosted",
    }
    for environment in facts.ENVIRONMENTS:
        ref, digest = _write_fact(root, environment, targets[environment], predecessor)
        refs[environment] = ref
        predecessor = {
            "environment": environment,
            "ref": ref,
            "factId": json.loads((root / ref).read_text())["factId"],
            "digest": digest,
        }
        if environment == through:
            break
    return refs


def _derive(root: Path, refs: dict[str, str | None]) -> dict[str, object]:
    return subject.derive_environment_release_order_view(
        release_id="release-a",
        derived_at="2026-08-29T08:00:00Z",
        artifact_root=root,
        acceptance_refs=refs,
    )


def test_empty_view_is_deterministic_and_only_alpha_is_actionable(tmp_path: Path) -> None:
    refs = {environment: None for environment in facts.ENVIRONMENTS}
    first = _derive(tmp_path, refs)
    second = _derive(tmp_path, refs)
    assert first == second
    assert [row["environment"] for row in first["environments"]] == list(facts.ENVIRONMENTS)
    assert [row["state"] for row in first["environments"]] == ["no_acceptance"] * 4
    assert first["environments"][0]["availableActions"] == ["create_acceptance"]
    assert all(row["availableActions"] == [] for row in first["environments"][1:])


def test_chain_projection_exposes_closed_available_actions(tmp_path: Path) -> None:
    refs = _chain(tmp_path, "beta")
    view = _derive(tmp_path, refs)
    _schema_validator().validate(view)
    rows = view["environments"]
    assert [row["state"] for row in rows] == ["accepted", "accepted", "no_acceptance", "no_acceptance"]
    assert [row["predecessorSatisfied"] for row in rows] == [True, True, True, False]
    assert [row["availableActions"] for row in rows] == [[], [], ["create_acceptance"], []]
    assert not {"command", "checkpoint", "version", "ledger"}.intersection(view)
    assert "J0" not in json.dumps(view)


def test_missing_failed_and_digest_drifted_fact_do_not_create_second_state(tmp_path: Path) -> None:
    refs = _chain(tmp_path, "beta")
    (tmp_path / refs["alpha"]).chmod(0o644)
    (tmp_path / refs["alpha"]).write_bytes((tmp_path / refs["alpha"]).read_bytes() + b" ")
    view = _derive(tmp_path, refs)
    rows = view["environments"]
    assert rows[0]["state"] == "accepted"
    assert rows[1]["state"] == "no_acceptance"
    assert rows[2]["availableActions"] == []

    failed_root = tmp_path / "failed"
    failed_refs = _chain(failed_root, "alpha")
    failed_path = failed_root / failed_refs["alpha"]
    failed_document = json.loads(failed_path.read_text(encoding="utf-8"))
    failed_document["passed"] = False
    failed_path.chmod(0o644)
    failed_path.write_text(json.dumps(failed_document, sort_keys=True) + "\n")
    failed_view = _derive(failed_root, failed_refs)
    assert failed_view["environments"][0]["state"] == "no_acceptance"
    assert set(failed_view["environments"][0]) == {
        "environment",
        "state",
        "acceptanceRef",
        "acceptanceDigest",
        "predecessorSatisfied",
        "availableActions",
    }

    polluted = deepcopy(view)
    polluted["environments"][0]["state"] = "failed"
    with pytest.raises(subject.EnvironmentReleaseOrderViewError, match="unknown"):
        subject.validate_environment_release_order_view(polluted)


def test_wrong_order_and_cross_release_fact_are_projected_as_absent(tmp_path: Path) -> None:
    refs = _chain(tmp_path, "alpha")
    refs["beta"] = refs["alpha"]
    wrong_order = _derive(tmp_path, refs)
    assert wrong_order["environments"][1]["state"] == "no_acceptance"

    cross_release = subject.derive_environment_release_order_view(
        release_id="release-b",
        derived_at="2026-08-29T08:00:00Z",
        artifact_root=tmp_path,
        acceptance_refs=refs,
    )
    assert all(row["state"] == "no_acceptance" for row in cross_release["environments"])


def test_schema_and_library_exclude_command_checkpoint_version_and_action_drift(tmp_path: Path) -> None:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    assert all(token not in schema_text for token in ('"command"', '"checkpoint"', '"version"', '"ledger"'))
    view = _derive(tmp_path, {environment: None for environment in facts.ENVIRONMENTS})
    polluted = deepcopy(view)
    polluted["command"] = "advance"
    assert list(_schema_validator().iter_errors(polluted))
    with pytest.raises(subject.EnvironmentReleaseOrderViewError, match="fields mismatch"):
        subject.validate_environment_release_order_view(polluted)

    unknown_action = deepcopy(view)
    unknown_action["environments"][0]["availableActions"] = ["advance"]
    with pytest.raises(subject.EnvironmentReleaseOrderViewError, match="closed set"):
        subject.validate_environment_release_order_view(unknown_action)


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())
