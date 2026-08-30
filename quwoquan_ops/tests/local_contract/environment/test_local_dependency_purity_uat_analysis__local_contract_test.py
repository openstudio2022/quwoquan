from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
import tempfile
from pathlib import Path

from quwoquan_ops.gate.verify_local_dependency_purity import (
    _verify_uat_static_analysis_coverage,
)

def _uat_analysis_gate(command: str, *, dispatch: bool = True) -> str:
    script = "run_app() {\n" + command + "\n}\n"
    if dispatch:
        script += (
            'case "$scope" in\n'
            "  all)\n    run_app\n    ;;\n"
            "  app)\n    run_app\n    ;;\n"
            "esac\n"
        )
    return script


def _write_uat_analysis_coverage_fixture(root: Path) -> tuple[Path, Path]:
    app = root / "quwoquan_app"
    (app / "test/user_acceptance/journeys/startup").mkdir(parents=True)
    (app / "test/support/runtime/patrol").mkdir(parents=True)
    (app / "test_host/patrol/test").mkdir(parents=True)
    (app / "test/user_acceptance/journeys/startup/startup_test.dart").write_text(
        "void main() {}\n", encoding="utf-8"
    )
    (app / "test/support/runtime/patrol/patrol_test_support.dart").write_text(
        "void support() {}\n", encoding="utf-8"
    )
    (app / "analysis_options.yaml").write_text(
        "analyzer:\n"
        "  exclude:\n"
        "    - test/user_acceptance/**\n"
        "    - test/support/runtime/patrol/**\n",
        encoding="utf-8",
    )
    (app / "test_host/patrol/test/canonical").symlink_to(
        Path("../../../test"), target_is_directory=True
    )
    gate = root / "gate_repo.sh"
    gate.write_text(
        _uat_analysis_gate(
            "(cd quwoquan_app/test_host/patrol && flutter analyze \\\n"
            "  lib test/patrol test/canonical/user_acceptance "
            "test/canonical/support/runtime/patrol)"
        ),
        encoding="utf-8",
    )
    return app, gate


def test_uat_analysis_coverage_accepts_symlinked_test_host_analysis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert failures == []


def test_uat_analysis_coverage_rejects_exclusion_without_test_host_analysis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        gate.write_text(
            _uat_analysis_gate("flutter analyze lib test"), encoding="utf-8"
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/canonical/user_acceptance" in failure
        ]


def test_uat_analysis_coverage_rejects_copied_canonical_uat() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        canonical_link = app / "test_host/patrol/test/canonical"
        canonical_link.unlink()
        (canonical_link / "user_acceptance/journeys/startup").mkdir(parents=True)
        (
            canonical_link / "user_acceptance/journeys/startup/startup_test.dart"
        ).write_text("void main() {}\n", encoding="utf-8")
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "must be a symlink" in failure
        ]


def test_uat_analysis_coverage_rejects_unexcluded_main_app_analysis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        (app / "analysis_options.yaml").write_text(
            "analyzer:\n  exclude:\n    - build/**\n", encoding="utf-8"
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/user_acceptance/**" in failure
        ]


def test_uat_analysis_coverage_rejects_a_new_exclude_without_a_witness() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        (app / "analysis_options.yaml").write_text(
            "analyzer:\n"
            "  exclude:\n"
            "    - test/user_acceptance/**\n"
            "    - test/support/runtime/patrol/**\n"
            "    - test/support/runtime/device/**\n",
            encoding="utf-8",
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/support/runtime/device/**" in failure
        ]


def test_uat_analysis_coverage_rejects_a_commented_out_analysis_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        gate.write_text(
            "# test/canonical/user_acceptance test/canonical/support/runtime/patrol\n"
            + _uat_analysis_gate(
                "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol)"
            ),
            encoding="utf-8",
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/canonical/user_acceptance" in failure
        ]


def test_uat_analysis_coverage_rejects_a_complete_commented_command() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        gate.write_text(
            "# (cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
            "test/canonical/user_acceptance test/canonical/support/runtime/patrol)\n"
            + _uat_analysis_gate(
                "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol)"
            ),
            encoding="utf-8",
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/canonical/user_acceptance" in failure
        ]


def test_uat_analysis_coverage_rejects_test_host_excluding_canonical_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        (app / "test_host/patrol/analysis_options.yaml").write_text(
            "analyzer:\n  exclude:\n    - test/canonical/**\n", encoding="utf-8"
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "must not exclude test/canonical/**" in failure
        ]
