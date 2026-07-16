"""Contract tests for the single-work-package content facade."""
from __future__ import annotations

import argparse
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
        {"execution": {"maxWorkers": 1}, "readiness": {"requireReviewed": True}},
        EXECUTION_ID,
        lambda argv: calls.append(list(argv)) or 0,
    )
    assert calls == [["verify", "execution-readiness", "--execution-id", EXECUTION_ID, "--require-reviewed"]]


def test_readiness_accepts_recipe_bounded_parallel_execution():
    calls: list[list[str]] = []
    recipe._readiness(
        {"execution": {"maxWorkers": 3}},
        EXECUTION_ID,
        lambda argv: calls.append(argv) or 0,
    )
    assert calls == [["verify", "execution-readiness", "--execution-id", EXECUTION_ID]]


def test_preflight_evidence_belongs_to_execution_work_package():
    argv = recipe._env_ready_argv(
        recipe.load_recipe(recipe.GEO_HOMEPAGE_RECIPE),
        EXECUTION_ID,
    )
    report_path = Path(argv[argv.index("--report-out") + 1])
    assert argv[:2] == ["task", "preflight"]
    assert "--json" not in argv
    assert report_path == recipe.execution_root(EXECUTION_ID) / "evidence" / "environment_readiness.json"


def test_geo_homepages_uses_internal_recipe_with_only_execution_identity():
    received: dict[str, object] = {}
    original = recipe._run_geo_homepage_execution

    def _capture(args: argparse.Namespace, invoke=None) -> None:
        received.update(vars(args))

    recipe._run_geo_homepage_execution = _capture
    try:
        recipe.handle_geo_homepages(
            argparse.Namespace(
                execution_id=EXECUTION_ID,
                retry_of=None,
                rollout=recipe.GEO_HOMEPAGE_ROLLOUT,
                region=None,
                discovery=None,
                limit=None,
                mandatory=None,
                name=None,
                title=None,
                intent_label=None,
                stage="plan-only",
                force_execution_write=False,
                recover_stage=None,
                recovery_reason=None,
            )
        )
    finally:
        recipe._run_geo_homepage_execution = original
    assert received["execution_id"] == EXECUTION_ID
    assert received["rollout"] == recipe.GEO_HOMEPAGE_ROLLOUT
    assert received["region"] == "中国/浙江省"
    assert received["discovery"] == "quwoquan_data/verticals/travel/coverage/中国/浙江省"
    assert "recipe" not in received and "batch" not in received and "plan" not in received


def test_geo_homepages_rejects_an_unpaired_recovery_request(monkeypatch):
    monkeypatch.setattr(recipe, "load_recipe", lambda _ref: {})

    try:
        recipe._run_geo_homepage_execution(
            argparse.Namespace(
                execution_id=EXECUTION_ID,
                retry_of=None,
                stage="run",
                force_execution_write=False,
                recover_stage="build_homepage",
                recovery_reason=None,
            )
        )
        raise AssertionError("unpaired recovery request must fail")
    except SystemExit as exc:
        assert "recover-stage" in str(exc)


def test_checkpoint_recovery_reuses_frozen_execution_selection(monkeypatch, tmp_path):
    manifest_path = tmp_path / "execution_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    frozen = {
        "region": "中国/浙江省",
        "discovery": "quwoquan_data/verticals/travel/coverage/中国/浙江省",
        "mandatory": "普陀山,东钱湖",
        "limit": 2,
    }
    monkeypatch.setattr(recipe, "execution_manifest_path", lambda _execution_id: manifest_path)
    monkeypatch.setattr(
        recipe,
        "load_execution_manifest",
        lambda _execution_id: {"resolvedParams": frozen},
    )
    resolved = recipe._resolve_execution_recipe(
        {
            "selection": {"region": "中国/浙江"},
            "contract": {"targetObjectCount": 100},
            "readiness": {"target": 100},
        },
        argparse.Namespace(region="中国/浙江", discovery="other", limit=99),
        execution_id=EXECUTION_ID,
        recover_stage="build_homepage",
    )
    assert resolved["selection"] == frozen
    assert resolved["contract"]["targetObjectCount"] == 2
    assert resolved["readiness"]["target"] == 2


def test_checkpoint_recovery_rejects_a_manifest_without_frozen_selection(monkeypatch, tmp_path):
    manifest_path = tmp_path / "execution_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recipe, "execution_manifest_path", lambda _execution_id: manifest_path)
    monkeypatch.setattr(recipe, "load_execution_manifest", lambda _execution_id: {"resolvedParams": {}})
    try:
        recipe._resolve_execution_recipe(
            {"selection": {}},
            argparse.Namespace(),
            execution_id=EXECUTION_ID,
            recover_stage="build_homepage",
        )
        raise AssertionError("missing frozen selection must fail")
    except ValueError as exc:
        assert "resolvedParams" in str(exc)


def test_task_facade_exposes_only_durable_commands():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_ROOT / "cli.py"), "task", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    command_rows = [line.strip().split(maxsplit=1)[0] for line in result.stdout.splitlines() if line.startswith("    ")]
    assert command_rows == ["preflight", "geo-homepages"]


def test_governed_rollout_rejects_selection_overrides():
    try:
        recipe.handle_geo_homepages(
            argparse.Namespace(
                execution_id=EXECUTION_ID,
                retry_of=None,
                rollout=recipe.GEO_HOMEPAGE_ROLLOUT,
                region=None,
                discovery=None,
                limit=2,
                mandatory=None,
                name=None,
                title=None,
                intent_label=None,
                stage="plan-only",
                force_execution_write=False,
                recover_stage=None,
                recovery_reason=None,
            )
        )
        raise AssertionError("governed rollout must reject a CLI limit")
    except SystemExit as exc:
        assert "rejects selection overrides" in str(exc)


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
