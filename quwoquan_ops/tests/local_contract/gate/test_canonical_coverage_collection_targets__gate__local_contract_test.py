# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-002
"""`verify_canonical_coverage.py` 采集目标与 coverage 工具链的本地契约。

由 test_canonical_coverage__gate__local_contract_test.py（Python 1000 行硬顶
治理）按场景拆出：Go/Python 采集目标从 domain YAML 派生并按语言实存收窄、
Python coverage 工具链单一精确锁与漂移阻断、App source closure 绑定 pubspec
与全部本地 path 依赖。测试逐字搬移，断言语义不变。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm
from quwoquan_ops.gate import verify_canonical_coverage as vcr
from quwoquan_ops.gate.canonical_coverage import provenance as coverage_provenance


RECOMMENDATION_SERVICE_ROOT = (
    ROOT / "quwoquan_service" / "services" / "recommendation-service"
)
RECOMMENDATION_MAKEFILE_PATH = RECOMMENDATION_SERVICE_ROOT / "Makefile"
RECOMMENDATION_COVERAGE_LOCK_PATH = (
    RECOMMENDATION_SERVICE_ROOT / vcr.PYTHON_COVERAGE_TOOLCHAIN_LOCK
)
RECOMMENDATION_RUNTIME_REQUIREMENTS_PATH = (
    RECOMMENDATION_SERVICE_ROOT
    / "internal/recommendation/recommendation_model_release/"
    "infrastructure/model_runtime/requirements.txt"
)


def test_cloud_collection_targets_are_derived_from_domain_yaml_not_a_hand_list() -> (
    None
):
    """采集目标同源于 `object_path_map.service_domains()`，并按有无 Go 代码收窄。"""
    targets = vcr.go_collection_targets()
    expected = {
        relative: domain
        for relative, (_owner, domain) in opm.service_domains().items()
        if vcr._has_go_sources(ROOT / relative)
    }

    assert targets == expected
    # 非 Go 实现的 service 必须被排除，否则 go list 返回空集、门禁误报。
    excluded = set(opm.service_domains()) - set(targets)
    for relative in excluded:
        assert not vcr._has_go_sources(ROOT / relative)
    # 同一 domain 可以横跨多个 service，但对象单元必须保留物理 service 身份。
    domains = list(targets.values())
    assert len(set(domains)) < len(domains)
    cloud_units = vcr.discover_cloud_units()
    ops_services = {
        vcr.unit_bucket(unit).split("/", 1)[0]
        for unit in cloud_units
        if unit.startswith(vcr.CLOUD_UNIT_PREFIX)
        and not unit.startswith(vcr.CLOUD_CROSS_CUTTING_UNIT_PREFIX)
        and vcr.unit_bucket(unit).split("/", 1)[0]
        in {
            opm.app_service_segment("product-ops-service"),
            opm.app_service_segment("platform-ops"),
        }
    }
    assert ops_services == {"product_ops_service", "platform_ops"}


def test_python_recommendation_target_and_seven_objects_are_not_dropped() -> None:
    target = "quwoquan_service/services/recommendation-service"

    assert target not in vcr.go_collection_targets()
    assert vcr.python_collection_targets()[target] == "recommendation"
    assert vcr.artifact_path(target).name.endswith(".python-trace.json")

    prefix = "cloud:recommendation_service/recommendation/"
    object_units = {
        unit for unit in vcr.discover_cloud_units() if unit.startswith(prefix)
    }
    assert object_units == {
        prefix + object_name
        for object_name in {
            "ranked_recommendation_window",
            "recommendation_candidate_index_view",
            "recommendation_exposure_fact",
            "recommendation_feature_profile_view",
            "recommendation_feedback_fact",
            "recommendation_model_release",
            "recommendation_subject_closure_fact",
        }
    }
    assert all(
        vcr.cloud_collection_targets_for_unit(unit) == [target] for unit in object_units
    )
    assert target in vcr.cloud_collection_targets_for_unit(
        vcr.cloud_cross_cutting_unit("cmd")
    )


def test_python_coverage_toolchain_has_one_tracked_exact_dependency_truth() -> None:
    lock_text = RECOMMENDATION_COVERAGE_LOCK_PATH.read_text(encoding="utf-8")
    locked = vcr._parse_python_coverage_toolchain_lock(lock_text)

    assert locked == {
        "iniconfig": "2.3.0",
        "packaging": "26.2",
        "pluggy": "1.6.0",
        "pygments": "2.20.0",
        "pytest": "9.1.1",
    }
    runtime_requirements = RECOMMENDATION_RUNTIME_REQUIREMENTS_PATH.read_text(
        encoding="utf-8"
    )
    assert "pytest" not in runtime_requirements.lower()

    makefile = RECOMMENDATION_MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "COVERAGE_TOOLCHAIN_LOCK := resources/coverage-toolchain.lock" in makefile
    assert (
        "COVERAGE_TOOLCHAIN_MARKER := $(REC_PYTHON_ROOT)/coverage-toolchain.sha256"
        in makefile
    )
    assert (
        'pip install --disable-pip-version-check -r "$(COVERAGE_TOOLCHAIN_LOCK)"'
        in makefile
    )
    assert "coverage pytest drift" in makefile


@pytest.mark.parametrize(
    "lock_text",
    (
        "pytest>=9.1.1\n",
        "pluggy==1.6.0\n",
        "pytest==9.1.1\npytest==9.1.1\n",
    ),
)
def test_python_coverage_toolchain_rejects_ranges_missing_pytest_or_duplicates(
    lock_text: str,
) -> None:
    with pytest.raises(vcr.CoverageError):
        vcr._parse_python_coverage_toolchain_lock(lock_text)


def test_python_toolchain_state_blocks_missing_marker_and_version_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "quwoquan_service/services/probe-service"
    service_root = tmp_path / target
    service_root.mkdir(parents=True)
    lock_path = service_root / vcr.PYTHON_COVERAGE_TOOLCHAIN_LOCK
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("pytest==9.1.1\npluggy==1.6.0\n", encoding="utf-8")

    environment_root = tmp_path / "managed-python"
    executable = environment_root / "bin/python"
    executable.parent.mkdir(parents=True)
    executable.write_text("managed\n", encoding="utf-8")
    pytest_path = environment_root / "lib/python/site-packages/pytest/__init__.py"
    pytest_path.parent.mkdir(parents=True)
    pytest_path.write_text("__version__ = '9.1.1'\n", encoding="utf-8")
    base_prefix = tmp_path / "python-base"
    trace_path = base_prefix / "lib/python/trace.py"
    trace_path.parent.mkdir(parents=True)
    trace_path.write_text("class Trace: pass\n", encoding="utf-8")
    trace_digest = vcr._sha256_file(trace_path)

    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(
        vcr, "_python_collection_executable", lambda _target: executable
    )
    pytest_version = "9.1.1"

    def identity(command: list[str], *, cwd: Path) -> str:
        assert cwd == service_root
        if "freeze" in command:
            return "pluggy==1.6.0\npytest==9.1.1\npip==25.1.1\n"
        return json.dumps(
            {
                "basePrefix": str(base_prefix),
                "pythonExecutable": str(executable),
                "pythonVersion": "3.13.3 controlled",
                "pytestPath": str(pytest_path),
                "pytestVersion": pytest_version,
                "traceDigest": trace_digest,
                "tracePath": str(trace_path),
            }
        )

    monkeypatch.setattr(vcr, "_identity_command", identity)

    with pytest.raises(vcr.CoverageError, match="缺少受管 coverage toolchain marker"):
        vcr._python_toolchain_state(target)

    marker = environment_root / vcr.PYTHON_COVERAGE_TOOLCHAIN_MARKER
    marker.write_text(vcr._sha256_file(lock_path).removeprefix("sha256:") + "\n")
    pytest_version = "9.2.0"
    with pytest.raises(vcr.CoverageError, match="pytest version 漂移"):
        vcr._python_toolchain_state(target)

    pytest_version = "9.1.1"
    state = vcr._python_toolchain_state(target)
    assert state["pytestVersion"] == "9.1.1"
    assert state["traceDigest"] == trace_digest
    assert state["pipFreeze"] == [
        "pip==25.1.1",
        "pluggy==1.6.0",
        "pytest==9.1.1",
    ]


def test_flutter_toolchain_identity_ignores_transient_stderr_and_canonicalizes_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = iter(
        [
            subprocess.CompletedProcess(
                args=["flutter"],
                returncode=0,
                stdout='{"frameworkVersion":"3.47.0","channel":"stable"}\n',
                stderr="Waiting for another flutter command to release the startup lock...\n",
            ),
            subprocess.CompletedProcess(
                args=["flutter"],
                returncode=0,
                stdout=' { "channel": "stable", "frameworkVersion": "3.47.0" } ',
                stderr="",
            ),
        ]
    )

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert command == ["flutter", "--version", "--machine"]
        assert cwd == vcr.APP_ROOT
        assert text is True
        assert capture_output is True
        assert check is False
        return next(outputs)

    monkeypatch.setattr(coverage_provenance.subprocess, "run", fake_run)

    first = vcr._flutter_toolchain_identity()
    second = vcr._flutter_toolchain_identity()

    assert first == second == {
        "channel": "stable",
        "frameworkVersion": "3.47.0",
    }


@pytest.mark.parametrize(
    ("completed", "message"),
    [
        (
            subprocess.CompletedProcess(
                args=["flutter"], returncode=1, stdout="", stderr="SDK unavailable"
            ),
            "Flutter identity command 失败",
        ),
        (
            subprocess.CompletedProcess(
                args=["flutter"], returncode=0, stdout="not-json", stderr=""
            ),
            "machine identity 不是合法 JSON",
        ),
        (
            subprocess.CompletedProcess(
                args=["flutter"], returncode=0, stdout="[]", stderr=""
            ),
            "machine identity 必须是非空对象",
        ),
        (
            subprocess.CompletedProcess(
                args=["flutter"], returncode=0, stdout="{}", stderr=""
            ),
            "machine identity 必须是非空对象",
        ),
    ],
)
def test_flutter_toolchain_identity_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    completed: subprocess.CompletedProcess[str],
    message: str,
) -> None:
    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert command == ["flutter", "--version", "--machine"]
        assert cwd == vcr.APP_ROOT
        assert text is True
        assert capture_output is True
        assert check is False
        return completed

    monkeypatch.setattr(coverage_provenance.subprocess, "run", fake_run)

    with pytest.raises(vcr.CoverageError, match=message):
        vcr._flutter_toolchain_identity()


def test_a_test_only_go_service_never_becomes_a_collection_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = "quwoquan_service/services/probe-service"
    service_root = tmp_path / relative
    (service_root / "internal/probe").mkdir(parents=True)
    (service_root / "tests/local_contract").mkdir(parents=True)
    (service_root / "internal/probe/probe_test.go").write_text(
        "package probe\n", encoding="utf-8"
    )
    (service_root / "tests/local_contract/helper.go").write_text(
        "package local_contract\n", encoding="utf-8"
    )
    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(
        opm, "service_domains", lambda: {relative: ("probe-service", "probe")}
    )
    vcr.go_collection_targets.cache_clear()
    try:
        assert vcr.go_collection_targets() == {}
        (service_root / "internal/probe/probe.go").write_text(
            "package probe\n", encoding="utf-8"
        )
        vcr.go_collection_targets.cache_clear()
        assert vcr.go_collection_targets() == {relative: "probe"}
    finally:
        vcr.go_collection_targets.cache_clear()


def test_a_test_only_python_service_never_becomes_a_collection_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = "quwoquan_service/services/probe-service"
    service_root = tmp_path / relative
    (service_root / "internal/probe").mkdir(parents=True)
    (service_root / "tests/local_contract").mkdir(parents=True)
    (service_root / "internal/probe/__init__.py").write_text("", encoding="utf-8")
    (service_root / "tests/local_contract/test_probe.py").write_text(
        "def test_probe(): assert True\n", encoding="utf-8"
    )
    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(
        opm, "service_domains", lambda: {relative: ("probe-service", "probe")}
    )
    vcr.go_collection_targets.cache_clear()
    vcr.python_collection_targets.cache_clear()
    try:
        assert vcr.python_collection_targets() == {}
        (service_root / "internal/probe/service.py").write_text(
            "def execute(): return True\n", encoding="utf-8"
        )
        vcr.python_collection_targets.cache_clear()
        assert vcr.python_collection_targets() == {relative: "probe"}
    finally:
        vcr.python_collection_targets.cache_clear()
        vcr.go_collection_targets.cache_clear()


def test_app_source_closure_binds_flutter_pubspec_and_every_local_path_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_root = tmp_path / "quwoquan_app"
    (app_root / "lib").mkdir(parents=True)
    (app_root / "packages/local_one/native").mkdir(parents=True)
    (tmp_path / "shared/local_two/lib").mkdir(parents=True)
    (app_root / "lib/main.dart").write_text("void main() {}\n", encoding="utf-8")
    (app_root / ".flutter-version").write_text("3.44.3\n", encoding="utf-8")
    (app_root / "pubspec.yaml").write_text("name: probe\n", encoding="utf-8")
    (app_root / "pubspec.lock").write_text(
        """packages:
  local_one:
    source: path
    description:
      path: packages/local_one
      relative: true
  local_two:
    source: path
    description:
      path: ../shared/local_two
      relative: true
""",
        encoding="utf-8",
    )
    first_dependency_file = app_root / "packages/local_one/native/probe.mm"
    second_dependency_file = tmp_path / "shared/local_two/lib/probe.dart"
    first_dependency_file.write_text("// native\n", encoding="utf-8")
    second_dependency_file.write_text("const probe = 1;\n", encoding="utf-8")
    ignored_cache = app_root / "packages/local_one/.dart_tool/package_config.json"
    ignored_cache.parent.mkdir(parents=True)
    ignored_cache.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(vcr, "APP_ROOT", app_root)

    closure = vcr._app_source_closure_files()
    assert app_root / ".flutter-version" in closure
    assert app_root / "pubspec.yaml" in closure
    assert app_root / "pubspec.lock" in closure
    assert first_dependency_file in closure
    assert second_dependency_file in closure
    assert ignored_cache not in closure

    before = vcr._tree_digest(closure, label="app source closure")
    second_dependency_file.write_text("const probe = 2;\n", encoding="utf-8")
    after = vcr._tree_digest(
        vcr._app_source_closure_files(), label="app source closure"
    )
    assert after != before
