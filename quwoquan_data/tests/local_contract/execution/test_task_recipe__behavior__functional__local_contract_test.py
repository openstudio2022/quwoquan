"""Contract tests for the single-work-package content facade."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.paths import FAMILIES_ROOT, iter_family_files  # noqa: E402
from content.execution import recipe  # noqa: E402
from content.execution.identity import build_execution_id, parse_execution_id, validate_execution_id  # noqa: E402


EXECUTION_ID = "20260711--travel-homepage-coverage--cn-zhejiang--canary-901"


def test_execution_id_is_readable_and_strict():
    identity = parse_execution_id(EXECUTION_ID)
    assert identity.vertical == "travel"
    assert identity.content_type == "homepage"
    assert identity.scope == "cn-zhejiang"
    assert identity.milestone == "canary"
    assert identity.sequence == 901
    assert build_execution_id(
        run_date="20260711",
        vertical="travel",
        content_type="homepage",
        intent="coverage",
        scope="cn-sichuan",
        milestone="m1",
        sequence=3,
    ) == "20260711--travel-homepage-coverage--cn-sichuan--m1-003"
    assert build_execution_id(
        run_date="20260711",
        vertical="travel",
        content_type="homepage",
        intent="coverage",
        scope="cn-sichuan",
        milestone="h10k",
        sequence=4,
    ) == "20260711--travel-homepage-coverage--cn-sichuan--h10k-004"
    try:
        validate_execution_id("task-a__batch-b")
        raise AssertionError("retired task/batch identity must fail")
    except ValueError:
        pass


def test_all_family_recipes_lint_clean():
    refs = [str(path.relative_to(FAMILIES_ROOT))[: -len(".recipe.yaml")] for path in iter_family_files(".recipe.yaml")]
    assert refs
    for ref in refs:
        loaded = recipe.load_recipe(ref)
        assert loaded["recipeId"] == ref


def test_execution_facade_invokes_the_canonical_data_cli():
    assert recipe._CLI_PATH == SCRIPTS_ROOT / "cli.py"
    assert recipe._CLI_PATH.is_file()


def test_readiness_calls_only_single_execution_gate():
    calls: list[list[str]] = []
    recipe._readiness(
        {
            "execution": {"maxWorkers": 1},
            "readiness": {
                "requireReviewed": True,
                "minPassRate": 0.9,
                "mode": "commercial",
                "failOnNoGo": True,
            },
        },
        EXECUTION_ID,
        lambda argv: calls.append(list(argv)) or 0,
    )
    assert calls == [
        [
            "verify",
            "execution-readiness",
            "--execution-id",
            EXECUTION_ID,
            "--min-pass-rate",
            "0.9",
            "--mode",
            "commercial",
            "--require-reviewed",
            "--fail-on-no-go",
        ]
    ]


def test_readiness_accepts_recipe_bounded_parallel_execution():
    calls: list[list[str]] = []
    recipe._readiness(
        {"execution": {"maxWorkers": 3}},
        EXECUTION_ID,
        lambda argv: calls.append(argv) or 0,
    )
    assert calls == [
        [
            "verify",
            "execution-readiness",
            "--execution-id",
            EXECUTION_ID,
            "--min-pass-rate",
            "1.0",
            "--mode",
            "commercial",
        ]
    ]


def test_preflight_evidence_belongs_to_execution_work_package():
    argv = recipe._runtime_preflight_argv(EXECUTION_ID)
    report_path = Path(argv[argv.index("--report-out") + 1])
    assert argv[:2] == ["task", "preflight"]
    assert "--json" not in argv
    assert report_path == recipe.execution_root(EXECUTION_ID) / "evidence" / "runtime_preflight.json"


def test_execute_uses_rollout_contract_with_only_execution_identity():
    received: dict[str, object] = {}
    original = recipe._run_execution

    def _capture(args: argparse.Namespace, invoke=None) -> None:
        received.update(vars(args))

    recipe._run_execution = _capture
    try:
        recipe.handle_execute(
            argparse.Namespace(
                execution_id=EXECUTION_ID,
                retry_of=None,
                rollout=recipe.HOMEPAGE_ROLLOUT,
                stage="plan-only",
                recover_stage=None,
                recovery_reason=None,
            )
        )
    finally:
        recipe._run_execution = original
    assert received["execution_id"] == EXECUTION_ID
    assert received["rollout"] == recipe.HOMEPAGE_ROLLOUT
    assert received["region"] == "中国/浙江省"
    assert received["discovery"] == "quwoquan_data/verticals/travel/coverage/中国/浙江省"
    assert "recipe" not in received and "batch" not in received and "plan" not in received


def test_execute_routes_cold_start_identity_to_policy_targets(monkeypatch):
    from governance.coverage.cold_start_supply import ColdStartExecutionParameters

    execution_id = "20260718--travel-article-cold-start--cn-sichuan--m3-001"
    homepage_execution_id = (
        "20260718--travel-homepage-coverage--cn-sichuan--m3-901"
    )
    received: dict[str, object] = {}
    parameter_call: dict[str, object] = {}

    def _parameters(**kwargs):
        parameter_call.update(kwargs)
        return ColdStartExecutionParameters(
            province="四川省",
            target_names=("海螺沟", "九寨沟"),
        )

    monkeypatch.setattr(
        "governance.coverage.cold_start_supply.cold_start_execution_parameters",
        _parameters,
    )
    monkeypatch.setattr(
        recipe,
        "_run_execution",
        lambda args, invoke=None: received.update(vars(args)),
    )

    recipe.handle_execute(
        argparse.Namespace(
            execution_id=execution_id,
            retry_of=None,
            homepage_execution_id=homepage_execution_id,
            rollout="travel-cold-start-supply",
            stage="plan-only",
            recover_stage=None,
            recovery_reason=None,
        )
    )

    assert received["execution_id"] == execution_id
    assert received["region"] == "中国/四川省"
    assert received["limit"] == 2
    assert received["mandatory"] == "海螺沟,九寨沟"
    assert received["homepage_execution_id"] == homepage_execution_id
    assert parameter_call["homepage_execution_id"] == homepage_execution_id


def test_execute_rejects_an_unpaired_recovery_request(monkeypatch):
    monkeypatch.setattr(recipe, "load_recipe", lambda _ref: {})

    try:
        recipe._run_execution(
            argparse.Namespace(
                execution_id=EXECUTION_ID,
                retry_of=None,
                rollout=recipe.HOMEPAGE_ROLLOUT,
                stage="run",
                recover_stage="build_homepage",
                recovery_reason=None,
            )
        )
        raise AssertionError("unpaired recovery request must fail")
    except SystemExit as exc:
        assert "recover-stage" in str(exc)


def test_existing_execution_resume_uses_frozen_manifest_inputs(monkeypatch):
    frozen_params = {
        "region": "中国/浙江省",
        "discovery": "quwoquan_data/verticals/travel/coverage/中国/浙江省",
        "name": "浙江省主页m1",
        "title": "浙江省主页m1",
        "intentLabel": "浙江省景区主页m1",
        "category": "景区",
        "limit": 100,
        "mandatory": "冻结对象",
        "entityHomepagesPerTarget": 1,
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 0,
        "videoWorksPerTarget": 0,
    }
    monkeypatch.setattr(recipe, "load_recipe", lambda _ref: {"runtimeProfile": "profile"})
    monkeypatch.setattr(recipe, "_apply_runtime_env", lambda _recipe: None)
    monkeypatch.setattr(recipe, "execution_manifest_path", lambda _execution_id: Path("manifest.json"))
    monkeypatch.setattr(Path, "is_file", lambda self: self.name == "manifest.json")
    monkeypatch.setattr(
        recipe,
        "load_execution_manifest",
        lambda _execution_id: {
            "recipe": {"ref": recipe.HOMEPAGE_RECIPE},
            "resolvedParams": frozen_params,
            "retryOf": "20260711--travel-homepage-coverage--cn-zhejiang--canary-900",
        },
    )

    captured: dict[str, object] = {}

    def fake_create_execution_manifest(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after manifest validation")

    monkeypatch.setattr(
        "content.execution.create_execution_manifest",
        fake_create_execution_manifest,
    )
    monkeypatch.setattr(
        "content.execution.runner.preflight_execution_models",
        lambda _recipe: {},
    )
    monkeypatch.setattr(
        "content.execution.runner.write_execution_model_readiness",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "content.execution.recipe._ensure_execution_spec",
        lambda *_args, **_kwargs: EXECUTION_ID,
    )
    monkeypatch.setattr(
        "content.release.canonical.rollout_milestone.assert_rollout_start",
        lambda _execution_id: None,
    )
    monkeypatch.setattr(
        "content.execution.workspace.frozen_target_set_sha256",
        lambda _execution_id: "digest",
    )

    try:
        recipe._run_execution(
            argparse.Namespace(
                execution_id=EXECUTION_ID,
                retry_of=None,
                rollout=recipe.HOMEPAGE_ROLLOUT,
                stage="run",
                recover_stage="download_fetch",
                recovery_reason="transport_repaired",
            )
        )
        raise AssertionError("test must stop at manifest validation")
    except RuntimeError as exc:
        assert str(exc) == "stop after manifest validation"

    assert captured["resolved_params"] == frozen_params
    assert captured["retry_of"] == (
        "20260711--travel-homepage-coverage--cn-zhejiang--canary-900"
    )


def test_task_facade_exposes_only_durable_commands():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_ROOT / "cli.py"), "task", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    choices = re.search(r"^  \{([^}]+)\}$", result.stdout, flags=re.MULTILINE)
    assert choices is not None
    command_rows = choices.group(1).split(",")
    assert command_rows == [
        "preflight",
        "execute",
    ]


def test_execute_cli_has_no_selection_or_runtime_overrides():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_ROOT / "cli.py"), "task", "execute", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    forbidden = ("--limit", "--region", "--discovery", "--max-workers", "--runtime")
    assert not any(option in result.stdout for option in forbidden)
    assert "travel-homepage-coverage" in result.stdout
    assert "travel-cold-start-supply" in result.stdout


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted((name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)):
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
