# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
"""退役术语零容忍门的行为合约。

258 处存量清零后,这道门的价值在于「不回流」:任何新的 legacy/compat 运行时
标识直接 BLOCK,且不存在可以扩大的豁免名单——历史上这类债正是靠豁免名单
悄悄增长起来的。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_app/scripts/runtime/architecture/verify_retired_terms_zero.py"


def test_repository_has_zero_retired_runtime_identifiers() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", str(GATE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "OK" in completed.stdout


@pytest.fixture
def runtime_tree(tmp_path: Path) -> Path:
    """只复制扫描器及路径依赖，生产实现保持 exact bytes。"""
    for source in (GATE, ROOT / "quwoquan_app/scripts/_common/paths.py"):
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    runtime = tmp_path / "quwoquan_ops/cli"
    runtime.mkdir(parents=True)
    (runtime / "value.py").write_text("legacyAvailable = True\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("entry", ["scanner", "l0", "readiness"])
def test_real_retired_terms_failure_propagates(runtime_tree: Path, entry: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t2
    from quwoquan_ops.ci.local_readiness_planner import STATIC_COMMANDS

    command = STATIC_COMMANDS["retired_terms_zero"][0]
    if entry == "l0":
        source = (ROOT / "quwoquan_ops/gate/commit_gate.sh").read_text()
        function = source.split("run_static_check() {", 1)[1].split("\nexport -f", 1)[0]
        command = ["bash", "-c", "set -e\nrun_static_check() {" + function + "\nrun_static_check retired_terms_zero\nprintf unexpected-success"]
    elif entry == "readiness":
        sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
        from lib.local_readiness.core import _run_check

        result = _run_check(
            {"id": "static:retired_terms_zero", "command": command, "cwd": ".", "timeout_seconds": 30},
            runtime_tree / ".qwq_output/check.log",
            repo_root=runtime_tree,
        )
        assert result["status"] == "FAIL", result
        assert result["exit_code"] == 1
        assert "value.py:1:legacyAvailable" in Path(result["log"]).read_text()
        return
    completed = subprocess.run(command, cwd=runtime_tree, capture_output=True, text=True, timeout=30)
    assert completed.returncode != 0
    assert "value.py:1:legacyAvailable" in completed.stdout
    assert "unexpected-success" not in completed.stdout


def test_scanner_excludes_dependency_lockfile_but_scans_runtime_json(runtime_tree: Path) -> None:
    # package-lock 由 npm 生成，第三方依赖元数据不是 executable compatibility identity。
    runtime = runtime_tree / "quwoquan_data/control_plane/example"
    runtime.mkdir(parents=True)
    (runtime_tree / "quwoquan_ops/cli/value.py").unlink()
    (runtime / "package-lock.json").write_text('{"dependency": "legacy-package"}\n', encoding="utf-8")
    gate = runtime_tree / GATE.relative_to(ROOT)
    accepted = subprocess.run([sys.executable, "-B", str(gate)], capture_output=True, text=True, timeout=30)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr

    (runtime / "runtime.json").write_text('{"legacyMode": true}\n', encoding="utf-8")
    rejected = subprocess.run([sys.executable, "-B", str(gate)], capture_output=True, text=True, timeout=30)
    assert rejected.returncode == 1
    assert "runtime.json:1:legacyMode" in rejected.stdout


def test_scanner_accepts_current_names_comments_and_test_exclusion(runtime_tree: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t2
    runtime = runtime_tree / "quwoquan_ops/cli"
    (runtime / "value.py").write_text("# legacyAvailable is retired\navailability = True\n", encoding="utf-8")
    (runtime / "test_value.py").write_text("legacyFixture = True\n", encoding="utf-8")
    completed = subprocess.run([sys.executable, "-B", str(runtime_tree / GATE.relative_to(ROOT))], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("scope,phase", [("all", "all"), ("app", "all"), ("service", "all"), ("service", "packaging"), ("data", "all"), ("portal", "all"), ("ops-portal", "all"), ("patrol", "all")])
def test_gate_prefix_fails_before_heavy_commands(runtime_tree: Path, scope: str, phase: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t4
    source = ROOT / "quwoquan_ops/gate/gate_repo.sh"
    target = runtime_tree / source.relative_to(ROOT)
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    text = source.read_text()
    assert text.count("verify_retired_terms_zero.py") == 1
    assert text.index("verify_retired_terms_zero.py") < text.index("run_vertical_architecture_ratchet()")
    assert "verify_retired_terms_zero.py" not in text.split("run_app()", 1)[1]
    completed = subprocess.run(
        ["bash", str(target), "--scope", scope], cwd=runtime_tree,
        env={**os.environ, "GATE_SERVICE_PHASE": phase, "GATE_DATA_PHASE": "all"},
        capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode != 0
    assert "value.py:1:legacyAvailable" in completed.stdout, completed.stdout + completed.stderr
    assert "vertical architecture static ratchet" not in completed.stdout


POLICY_PATH = "quwoquan_ops/policies/gates/governed_schema_migration_boundaries.json"


@pytest.fixture
def migration_tree(runtime_tree: Path) -> Path:
    """复制当前生产边界 exact bytes，只在私有树注入反例。"""
    (runtime_tree / "quwoquan_ops/cli/value.py").unlink()
    policy = json.loads((ROOT / POLICY_PATH).read_text())
    boundary = policy["boundaries"][0]
    paths = [POLICY_PATH, boundary["spec_ref"].split("#")[0]]
    paths.extend(boundary[key] for key in ("cli", "registration", "handler", "implementation"))
    paths.extend("quwoquan_data/scripts/" + boundary[key].rpartition(".")[0].replace(".", "/") + ".py"
                 for key in ("current_reader", "current_writer"))
    paths.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / boundary["schema_root"]).rglob("*.schema.json"))
    for relative in paths:
        target = runtime_tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return runtime_tree


def _scan(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(root / GATE.relative_to(ROOT))],
                          cwd=root, capture_output=True, text=True, timeout=30)


# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-003.t1
def test_governed_migration_actual_boundary_passes(migration_tree: Path) -> None:
    completed = _scan(migration_tree)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("case", [
    "reader_import", "reader_alias_import", "reader_parent_import", "reader_schema",
    "reader_schema_path", "current_schema_ref", "extra_old_schema", "normal_cli",
    "remove_guard", "remove_governed_call", "remove_current_readback", "remove_current_validation",
    "unrelated_term", "same_line_term", "dynamic_import", "handler_direct_call",
    "dynamic_import_expression", "dynamic_schema", "writer_old_schema", "current_reader_validation",
    "early_return", "output_source_identity", "open_dynamic_import",
])
def test_governed_migration_rejects_actual_boundary_escape(migration_tree: Path, case: str) -> None:
    # spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-003.t2
    # spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-003.t3
    # spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-003.t4
    boundary = json.loads((migration_tree / POLICY_PATH).read_text())["boundaries"][0]
    implementation = migration_tree / boundary["implementation"]
    registration = migration_tree / boundary["registration"]
    module = "content.release.canonical.legacy_release_repackage"
    normal = migration_tree / "quwoquan_data/scripts/content/ordinary_reader.py"
    if case == "reader_import":
        normal.write_text(f"import {module}\n")
    elif case == "reader_alias_import":
        normal.write_text(f"from {module} import freeze_legacy_source as parse\n")
    elif case == "reader_parent_import":
        normal.write_text("from content.release.canonical import legacy_release_repackage as parser\n")
    elif case == "reader_schema":
        normal.write_text('from core.schema import assert_valid as validate\nvalidate({}, "release", "legacy_release_cohort_v1")\n')
    elif case == "reader_schema_path":
        normal.write_text('SCHEMA = "release/legacy_release_cohort_v1.schema.json"\n')
    elif case == "current_schema_ref":
        path = migration_tree / boundary["schema_root"] / boundary["output_schemas"][0]
        value = json.loads(path.read_text())
        value["allOf"] = [{"$ref": "legacy_release_cohort_v1.schema.json"}]
        path.write_text(json.dumps(value))
    elif case == "extra_old_schema":
        path = migration_tree / boundary["schema_root"] / boundary["input_schemas"][0]
        value = json.loads(path.read_text())
        value["allOf"] = [{"$ref": "release_cohort.schema.json"}]
        path.write_text(json.dumps(value))
    elif case == "normal_cli":
        registration.write_text(registration.read_text() + '\n    normal = commands.add_parser("read")\n    normal.set_defaults(handler=owner.handle_repackage_legacy)\n')
    elif case == "remove_guard":
        implementation.write_text(implementation.read_text().replace("source.release_id == target_id", "source.release_id != target_id"))
    elif case == "remove_governed_call":
        path = migration_tree / boundary["handler"]
        path.write_text(path.read_text().replace("governed_repackage_call(execute_repackage,", "execute_repackage("))
    elif case == "remove_current_readback":
        implementation.write_text(implementation.read_text().replace("read_producer_release_handoff(", "unverified_read("))
    elif case == "remove_current_validation":
        implementation.write_text(implementation.read_text().replace('assert_valid(document, "release", "producer_release_handoff", label="repackaged handoff")', "pass"))
    elif case == "unrelated_term":
        implementation.write_text(implementation.read_text() + "\nlegacyFallback = True\n")
    elif case == "same_line_term":
        implementation.write_text(implementation.read_text().replace('LEGACY_V1_LITERAL = "quwoquan_data.producer_release_handoff"', 'LEGACY_V1_LITERAL = "quwoquan_data.producer_release_handoff"; print("LEGACY_V1_LITERAL")'))
    elif case == "dynamic_import":
        normal.write_text(f'import importlib\nparser = importlib.import_module("{module}")\n')
    elif case == "handler_direct_call":
        normal.write_text('from content.release.canonical import handler as h\nh.handle_repackage_legacy(None)\n')
    elif case == "dynamic_import_expression":
        normal.write_text('import importlib\nparser = importlib.import_module("content.release.canonical." + "le" + "gacy_release_repackage")\n')
    elif case == "dynamic_schema":
        normal.write_text('from core.schema import assert_valid as validate\nvalidate({}, "release", "le" + "gacy_release_cohort_v1")\n')
    elif case == "writer_old_schema":
        implementation.write_text(implementation.read_text().replace('assert_valid(document, "release", "producer_release_handoff", label="repackaged handoff")', 'assert_valid(document, "release", "legacy_release_cohort_v1")\n        assert_valid(document, "release", "producer_release_handoff", label="repackaged handoff")'))
    elif case == "current_reader_validation":
        path = migration_tree / "quwoquan_data/scripts/content/release/canonical/producer_release_handoff.py"
        path.write_text(path.read_text().replace('assert_valid(value, "release", "producer_release_handoff", label="producer release handoff")', 'pass'))
    elif case == "early_return":
        implementation.write_text(implementation.read_text().replace('    source = frozen_source\n', '    return {}\n    source = frozen_source\n'))
    elif case == "output_source_identity":
        implementation.write_text(implementation.read_text().replace('write_producer_release_handoff(release_id=target_id,', 'write_producer_release_handoff(release_id=source.release_id,'))
    elif case == "open_dynamic_import":
        normal.write_text("import importlib\nparser = importlib.import_module(name)\n")
    completed = _scan(migration_tree)
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "FAIL" in completed.stdout


def test_gate_has_no_allowlist_escape() -> None:
    """禁止通过扩大豁免名单达成归零(OPEN-002 收口时的硬约束)。"""
    source = GATE.read_text(encoding="utf-8")
    for escape in ("ALLOWLIST", "allowlist_path", "exempt_paths", "baseline_path"):
        assert escape not in source, f"retired-terms gate must not grow {escape}"
