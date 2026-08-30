"""The data script gate rejects retired ambiguous orchestration modules."""
from pathlib import Path

import pytest

from verify import verify_script_architecture


def _minimal_scripts_root(root: Path) -> Path:
    scripts = root / "scripts"
    for relative in (
        "core",
        "content/post/article",
        "content/post/image",
        "content/post/video",
        "content/execution/controller",
        "governance",
        "verify",
    ):
        (scripts / relative).mkdir(parents=True, exist_ok=True)
    (scripts / "cli.py").write_text("", encoding="utf-8")
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    return scripts


def test_script_architecture_rejects_retired_workflow_and_controller_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    retired = (
        scripts / "content/post/video/workflow.py",
        scripts / "content/execution/controller/run.py",
    )
    for path in retired:
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert sum("retired ambiguous module" in issue for issue in issues) == 2


def test_script_architecture_rejects_execution_root_non_kernel_module(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    misplaced = scripts / "content/execution/campaign_orchestrator.py"
    misplaced.write_text("", encoding="utf-8")
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert any(
        "execution root only permits stable kernel" in issue
        for issue in issues
    )


def test_script_architecture_rejects_environment_lookup_dependency(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    lookup = (
        scripts
        / "content/release/canonical/build_lookup_indexes.py"
    )
    lookup.parent.mkdir(parents=True, exist_ok=True)
    lookup.write_text(
        "from core.paths import OUTPUT_ROOT\n"
        "from content.release.environment.topology import target\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert sum("immutable lookup indexes" in issue for issue in issues) == 2


def test_script_architecture_rejects_data_tool_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    cache = tmp_path / ".ruff_cache"
    cache.mkdir()
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert any(".ruff_cache" in issue for issue in issues)


def test_script_architecture_rejects_weak_types_in_control_modules(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    (scripts / "content/post/video/authoring.py").write_text(
        "from typing import Any, Mapping\n"
        "def author(payload: Mapping[str, Any]) -> None:\n"
        "    return None\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert any("strong control module" in issue for issue in issues)


def test_script_architecture_rejects_weak_types_in_release_control_module(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    release = scripts / "content/release/canonical/release_attestation.py"
    release.parent.mkdir(parents=True, exist_ok=True)
    release.write_text(
        "from typing import Mapping\n"
        "class Receipt:\n"
        "    @classmethod\n"
        "    def from_document(cls, payload: Mapping[str, object]):\n"
        "        return cls()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert any("release_attestation.py is a strong control module" in issue for issue in issues)


@pytest.mark.parametrize(
    "bad_name",
    [
        "runner_" + "t1" + ".py",
        "runner_" + "t2" + ".py",
        "runner_" + "t3" + ".py",
        "runner_" + "t4" + ".py",
        "gate_" + "m6" + ".py",
        "gate_" + "m7" + ".py",
        "gate_" + "b" + "10" + ".py",
        "reverify_" + "phase" + "0" + ".py",
        "bootstrap_tags_topic_verticals_" + "part" + "1" + ".py",
        "bootstrap_tags_topic_verticals_" + "part" + "2" + ".py",
    ],
)
def test_script_architecture_rejects_milestone_filenames(
    tmp_path: Path,
    monkeypatch,
    bad_name: str,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    (scripts / "governance" / bad_name).write_text("", encoding="utf-8")
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert any("T/M/B/phase/part milestones" in issue for issue in issues)


@pytest.mark.parametrize(
    "safe_name",
    [
        "participant.py",
        "bootstrap_tags_topic_travel.py",
        "partition_helpers.py",
        "phase_helpers.py",
    ],
)
def test_script_architecture_allows_non_milestone_filenames(
    tmp_path: Path,
    monkeypatch,
    safe_name: str,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    (scripts / "governance" / safe_name).write_text("", encoding="utf-8")
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert not any("T/M/B/phase/part milestones" in issue for issue in issues)


def _retirement_inventory(root: Path, state: str) -> None:
    path = root / verify_script_architecture.RETIREMENT_INVENTORY_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "{\n"
        '  "schema": "quwoquan_data.legacy_orchestration_retirement_inventory",\n'
        f'  "state": "{state}",\n'
        '  "deleteFamilies": ["agent", "queue", "controller", "recovery", "campaign"],\n'
        '  "preserveProtocolKernels": ["closure", "runtime_evidence", "scale"],\n'
        '  "forbiddenCompatibility": ["alias", "dual_read", "dual_write", "shim"]\n'
        "}\n",
        encoding="utf-8",
    )


def _minimal_post_delete_scripts_root(root: Path) -> Path:
    scripts = _minimal_scripts_root(root)
    (scripts / "content/execution/controller").rmdir()
    return scripts


def test_legacy_orchestration_families_are_canonical() -> None:
    assert verify_script_architecture.LEGACY_ORCHESTRATION_FAMILIES == (
        "agent",
        "queue",
        "controller",
        "recovery",
        "campaign",
    )


def test_retirement_inventory_preserves_protocol_kernels_and_forbids_compatibility() -> None:
    inventory = (
        Path(verify_script_architecture.REPO_ROOT)
        / verify_script_architecture.RETIREMENT_INVENTORY_RELATIVE
    ).read_text(encoding="utf-8")
    assert '"preserveProtocolKernels": ["closure", "runtime_evidence", "scale"]' in inventory
    assert '"deleteFamilies": ["agent", "queue", "controller", "recovery", "campaign"]' in inventory
    assert '"forbiddenCompatibility": ["alias", "dual_read", "dual_write", "shim"]' in inventory


def test_retired_inventory_rejects_deleted_family_and_preserved_kernel_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_post_delete_scripts_root(tmp_path)
    _retirement_inventory(tmp_path, "retired")
    inventory_path = tmp_path / verify_script_architecture.RETIREMENT_INVENTORY_RELATIVE
    inventory_path.write_text(
        inventory_path.read_text(encoding="utf-8").replace(
            '["closure", "runtime_evidence", "scale"]', '["closure", "scale"]'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)
    issues = verify_script_architecture.script_architecture_issues()
    assert any("preserveProtocolKernels drifted" in issue for issue in issues)


def test_script_architecture_pre_delete_inventory_keeps_legacy_families_allowed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    _retirement_inventory(tmp_path, "pre_delete")
    for family in verify_script_architecture.LEGACY_ORCHESTRATION_FAMILIES:
        (scripts / "content/execution" / family).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)
    issues = verify_script_architecture.script_architecture_issues()

    assert not any("legacy orchestration" in issue for issue in issues)
    assert not any("GATE_BLOCK" in issue for issue in issues)


@pytest.mark.parametrize(
    "family",
    verify_script_architecture.LEGACY_ORCHESTRATION_FAMILIES,
)
def test_script_architecture_retirement_seal_rejects_each_legacy_family_directory(
    tmp_path: Path,
    monkeypatch,
    family: str,
) -> None:
    scripts = _minimal_post_delete_scripts_root(tmp_path)
    _retirement_inventory(tmp_path, "retired")
    (scripts / "content/execution" / family).mkdir(parents=True)
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)
    issues = verify_script_architecture.script_architecture_issues()

    assert any(
        "GATE_BLOCK" in issue
        and "legacy orchestration directory remains" in issue
        and family in issue
        for issue in issues
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "from content.execution import queue as durable_pipeline\n",
            "retired Python orchestration module reference",
        ),
        (
            "import content.execution.recovery as recovery_adapter\n",
            "retired Python orchestration module reference",
        ),
        (
            "from content.execution import (\n    queue as durable_pipeline,\n)\n",
            "retired Python orchestration module reference",
        ),
        (
            "register_prepare_campaign_parser(commands)\n",
            "retired orchestration CLI parser/handler registration",
        ),
        (
            'commands.add_parser("controller-recover")\n',
            "retired orchestration CLI parser/handler registration",
        ),
    ],
)
def test_script_architecture_retirement_seal_rejects_python_and_cli_revival(
    tmp_path: Path,
    monkeypatch,
    source: str,
    expected: str,
) -> None:
    scripts = _minimal_post_delete_scripts_root(tmp_path)
    _retirement_inventory(tmp_path, "retired")
    adapter = scripts / "content/post/article/adapter.py"
    adapter.write_text(source, encoding="utf-8")
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)
    issues = verify_script_architecture.script_architecture_issues()

    assert any("GATE_BLOCK" in issue and expected in issue for issue in issues)


@pytest.mark.parametrize(
    ("relative", "source", "expected"),
    [
        (
            "quwoquan_service/services/content-service/cmd/data-content-worker/main.go",
            "package main\n",
            "Go data-content-worker path",
        ),
        (
            "quwoquan_service/runtime/reliabletask/data_content_worker.go",
            "package reliabletask\n",
            "ReliableTask worker path",
        ),
        (
            "quwoquan_service/runtime/reliabletask/safe.go",
            'package reliabletask\nconst queue = "reliabletask.data.content_supply"\n',
            "ReliableTask worker wire",
        ),
        (
            "quwoquan_service/runtime/reliabletask/safe.go",
            "package reliabletask\ntype Job DataContentJob\n",
            "ReliableTask worker wire",
        ),
        (
            "quwoquan_service/runtime/reliabletask/safe.go",
            "package reliabletask\ntype Binding DataContentCampaignBinding\n",
            "Go campaign/fleet wire",
        ),
        (
            "quwoquan_service/services/content-service/internal/content/post/application/importer/data_fleet.go",
            "package importer\n",
            "Go campaign/fleet path",
        ),
        (
            "quwoquan_ops/environments/compose/docker-compose.data-execution-fleet.yaml",
            "services: {}\n",
            "Ops data-execution-fleet path",
        ),
        (
            "quwoquan_ops/environments/topology.yaml",
            "controlPlane: data-execution-fleet\n",
            "Ops data-execution-fleet topology reference",
        ),
        (
            "quwoquan_ops/environments/compose/runtime.yaml",
            "services:\n  data-content-worker: {}\n",
            "Ops data-execution-fleet topology reference",
        ),
    ],
)
def test_script_architecture_retirement_seal_rejects_cross_repo_revival(
    tmp_path: Path,
    monkeypatch,
    relative: str,
    source: str,
    expected: str,
) -> None:
    scripts = _minimal_post_delete_scripts_root(tmp_path)
    _retirement_inventory(tmp_path, "retired")
    revived = tmp_path / relative
    revived.parent.mkdir(parents=True, exist_ok=True)
    revived.write_text(source, encoding="utf-8")
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)
    issues = verify_script_architecture.script_architecture_issues()

    assert any("GATE_BLOCK" in issue and expected in issue for issue in issues)


def test_script_architecture_retirement_seal_ignores_spec_plan_and_test_self_references(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_post_delete_scripts_root(tmp_path)
    _retirement_inventory(tmp_path, "retired")
    for relative in (
        "specs/retirement/spec.yaml",
        "plans/retirement/plan.json",
        "quwoquan_service/tests/runtime/legacy_test.go",
    ):
        self_reference = tmp_path / relative
        self_reference.parent.mkdir(parents=True, exist_ok=True)
        self_reference.write_text(
            "content.execution.queue data-content-worker data-execution-fleet\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)
    issues = verify_script_architecture.script_architecture_issues()

    assert not any("GATE_BLOCK" in issue for issue in issues)


def test_script_architecture_retirement_seal_passes_after_zero_reference_deletion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_post_delete_scripts_root(tmp_path)
    _retirement_inventory(tmp_path, "retired")
    source = tmp_path / "quwoquan_service/runtime/reliabletask/runtime.go"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("package reliabletask\n", encoding="utf-8")
    topology = tmp_path / "quwoquan_ops/environments/topology.yaml"
    topology.parent.mkdir(parents=True, exist_ok=True)
    topology.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)
    issues = verify_script_architecture.script_architecture_issues()

    assert issues == []


def test_script_architecture_retirement_seal_rejects_shim_directory_and_alias_import(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_post_delete_scripts_root(tmp_path)
    _retirement_inventory(tmp_path, "retired")
    shim = scripts / "content/execution/controller/__init__.py"
    shim.parent.mkdir(parents=True)
    shim.write_text("from content.execution import queue as kernel\n", encoding="utf-8")
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)
    issues = verify_script_architecture.script_architecture_issues()

    assert any("legacy orchestration directory remains" in issue for issue in issues)
    assert any("retired Python orchestration module reference" in issue for issue in issues)
