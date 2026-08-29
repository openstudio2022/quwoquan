from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
import tempfile
from pathlib import Path

import pytest

from quwoquan_ops.gate.verify_local_dependency_purity import (
    _verify_launcher_dependency_helper,
    _verify_locked_offline_flutter_pub_get,
    _verify_uat_static_analysis_coverage,
)

ROOT = Path(__file__).resolve().parents[4]


def _launcher_and_helper_sources() -> tuple[str, str]:
    return (
        (ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8"),
        (
            ROOT / "quwoquan_app/scripts/device/prepare_flutter_dependencies.py"
        ).read_text(encoding="utf-8"),
    )


def _helper_failures(helper_source: str) -> list[str]:
    launcher_source, _ = _launcher_and_helper_sources()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        launcher = root / "run.sh"
        helper = root / "prepare_flutter_dependencies.py"
        launcher.write_text(launcher_source, encoding="utf-8")
        helper.write_text(helper_source, encoding="utf-8")
        failures: list[str] = []
        _verify_launcher_dependency_helper(
            failures,
            launcher=launcher,
            helper=helper,
        )
        return failures


@pytest.mark.parametrize(
    "decoy",
    (
        (
            "    if False:\n"
            "        subprocess.run([flutter, 'pub', 'get', '--offline', "
            "'--enforce-lockfile'])\n"
        ),
        (
            "    def decoy():\n"
            "        return subprocess.run([flutter, 'pub', 'get', '--offline', "
            "'--enforce-lockfile'])\n"
        ),
        (
            "    decoy = lambda: subprocess.run([flutter, 'pub', 'get', "
            "'--offline', '--enforce-lockfile'])\n"
        ),
    ),
)
def test_helper_ignores_unreachable_subprocess_decoys(decoy: str) -> None:
    _, helper_source = _launcher_and_helper_sources()
    helper_source = helper_source.replace('        "--offline",\n', "", 1)
    helper_source = helper_source.replace(
        "    command = [\n", decoy + "    command = [\n", 1
    )

    failures = _helper_failures(helper_source)

    assert any("locked offline pub replay missing" in failure for failure in failures)


def test_helper_rejects_a_second_reachable_subprocess_call() -> None:
    _, helper_source = _launcher_and_helper_sources()
    reachable_decoy = (
        "    subprocess.run([flutter, 'pub', 'get', '--offline', "
        "'--enforce-lockfile'])\n"
    )
    helper_source = helper_source.replace(
        "    command = [\n", reachable_decoy + "    command = [\n", 1
    )

    failures = _helper_failures(helper_source)

    assert any("locked offline pub replay missing" in failure for failure in failures)


@pytest.mark.parametrize(
    "decoy",
    (
        (
            "cat <<'PUB_GET_DECOY'\n"
            "flutter pub get --offline --enforce-lockfile\n"
            "PUB_GET_DECOY\n"
        ),
        "printf '%s' 'flutter pub\nget --offline --enforce-lockfile'\n",
    ),
)
def test_pub_get_scanner_ignores_non_executable_multiline_decoys(decoy: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        gate = Path(tmp) / "gate_repo.sh"
        gate.write_text(decoy + "flutter pub get --offline\n", encoding="utf-8")
        failures: list[str] = []

        count = _verify_locked_offline_flutter_pub_get(failures, path=gate)

    assert count == 1
    assert len(failures) == 1
    assert "missing --enforce-lockfile" in failures[0]


def _write_uat_fixture(root: Path) -> tuple[Path, Path]:
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
    return app, root / "gate_repo.sh"


@pytest.mark.parametrize(
    "decoy",
    (
        (
            "cat <<'ANALYZE_DECOY'\n"
            "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
            "test/canonical/user_acceptance "
            "test/canonical/support/runtime/patrol)\n"
            "ANALYZE_DECOY\n"
        ),
        (
            "printf '%s' '(cd quwoquan_app/test_host/patrol && flutter analyze\n"
            "test/canonical/user_acceptance "
            "test/canonical/support/runtime/patrol)'\n"
        ),
    ),
)
def test_uat_scanner_ignores_non_executable_multiline_decoys(decoy: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_fixture(Path(tmp))
        gate.write_text(
            decoy
            + "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol)\n",
            encoding="utf-8",
        )
        failures: list[str] = []

        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)

    assert any(
        failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
        and "test/canonical/user_acceptance" in failure
        for failure in failures
    )
