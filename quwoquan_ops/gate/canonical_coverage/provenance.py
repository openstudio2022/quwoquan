"""采集 provenance：产物路径、内容摘要、输入闭包与 collection identity。

采集目标 ≠ 计量单元：端侧一次跑出全部桶，云侧按 service 跑。本模块派生每个
采集目标的产物路径、source/test/config/attribution/toolchain/scope 各摘要，
以及汇总它们的 ``current_collection_identity``。除 import 重组外与拆分前逐字
一致；被测试 monkeypatch 的符号经包命名空间 ``cc`` 在调用期解析。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

import yaml

import quwoquan_ops.gate.canonical_coverage as cc
from quwoquan_ops.gate import object_path_map as opm
from quwoquan_ops.gate import verify_app_architecture as vaa

from .constants import (
    APP_COLLECTION_TARGET,
    APP_TEST_TARGET,
    PYTHON_COVERAGE_TOOLCHAIN_LOCK,
    PYTHON_COVERAGE_TOOLCHAIN_MARKER,
    PYTHON_EXACT_REQUIREMENT_RE,
    PYTHON_MANAGED_ENV_RELATIVE,
    PYTHON_SERVICE_TEST_TARGET,
    PYTHON_TRACE_SOURCE_ROOTS,
    RULE_ID,
    SERVICE_COVERPKG_PATTERNS,
    SERVICE_EXCLUDED_PACKAGE_MARKER,
    SERVICE_GO_TEST_PACKAGE_PARALLELISM,
    SERVICE_ROOT,
    SHARED_RUNTIME_COLLECTION_TARGET,
    SHARED_RUNTIME_COVERPKG_PATTERNS,
    GIT_OBJECT_RE,
    CoverageError,
    _display,
    _tail,
)
from .app_runtime import (
    APP_FLUTTER_TEST_RUNNER,
    APP_RUNTIME_DEFINE_RESOLVER,
    APP_TEST_SELECTION_POLICY,
    app_coverage_policy_identity,
)
from .units import (
    _collection_target_language,
    cloud_collection_targets_for_unit,
    python_collection_targets,
    unit_scope,
)


def artifact_path(target: str) -> Path:
    if target == APP_COLLECTION_TARGET:
        return cc.COVERAGE_CACHE_DIR / "app.lcov.info"
    if target in python_collection_targets():
        return cc.COVERAGE_CACHE_DIR / f"{target.replace('/', '__')}.python-trace.json"
    return cc.COVERAGE_CACHE_DIR / f"{target.replace('/', '__')}.coverprofile"


def artifact_receipt_path(target: str) -> Path:
    path = artifact_path(target)
    return path.with_name(path.name + ".receipt.json")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_json_digest(payload: object) -> str:
    return _sha256_bytes(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _sha256_file(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CoverageError(f"覆盖率输入不是安全普通文件: {_display(path)}")
    return _sha256_bytes(path.read_bytes())


def _tree_digest(paths: Iterable[Path], *, label: str) -> str:
    files = sorted({Path(path) for path in paths}, key=lambda path: path.as_posix())
    if not files:
        raise CoverageError(f"{label} 没有任何受管输入")
    manifest: list[dict[str, str]] = []
    for path in files:
        if path.is_symlink():
            raise CoverageError(f"{label} 含符号链接输入: {path}")
        resolved = path.resolve()
        if not resolved.is_relative_to(cc.ROOT.resolve()) or not resolved.is_file():
            raise CoverageError(f"{label} 含不安全输入: {path}")
        manifest.append(
            {
                "path": resolved.relative_to(cc.ROOT.resolve()).as_posix(),
                "digest": _sha256_bytes(resolved.read_bytes()),
            }
        )
    return _sha256_bytes(
        json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _provenance_tree_files(
    root: Path, *, excluded_directory_names: frozenset[str] = frozenset()
) -> list[Path]:
    """返回会影响采集的普通文件/符号链接；输出目录不进入测试输入摘要。"""
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if (path.is_file() or path.is_symlink())
        and not (excluded_directory_names & set(path.relative_to(root).parts[:-1]))
    )


LOCAL_DEPENDENCY_EXCLUDED_DIRECTORY_NAMES = frozenset(
    {".dart_tool", ".git", "build", "coverage", "failures"}
)


def _app_local_path_dependency_roots() -> list[Path]:
    """从 resolver lock 派生 App 实际使用的全部本地 path package 根。

    这里不从 ``vendor/plugins`` 目录形状猜依赖，也不维护 package 名单。lock 中的
    ``source: path`` 是本次 Flutter resolver 真正选择的闭包；路径必须仍位于仓库内，
    否则 receipt 无法由仓库内容复核。
    """
    lock_path = cc.APP_ROOT / "pubspec.lock"
    if not lock_path.is_file() or lock_path.is_symlink():
        raise CoverageError(
            f"App path dependency closure 缺少安全 lock: {_display(lock_path)}"
        )
    try:
        document = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CoverageError(f"App pubspec.lock 无法解析: {error}") from error
    packages = document.get("packages") if isinstance(document, dict) else None
    if not isinstance(packages, dict):
        raise CoverageError("App pubspec.lock 缺少 packages mapping")

    roots: set[Path] = set()
    repository_root = cc.ROOT.resolve()
    for name, entry in packages.items():
        if not isinstance(entry, dict) or entry.get("source") != "path":
            continue
        description = entry.get("description")
        if not isinstance(description, dict):
            raise CoverageError(f"App path dependency {name!r} description 非 object")
        raw_path = description.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise CoverageError(f"App path dependency {name!r} 缺少 path")
        candidate = (
            cc.APP_ROOT / raw_path
            if description.get("relative") is True
            else Path(raw_path)
        )
        if candidate.is_symlink():
            raise CoverageError(
                f"App path dependency {name!r} 根不得是符号链接: {candidate}"
            )
        resolved = candidate.resolve()
        if not resolved.is_relative_to(repository_root) or not resolved.is_dir():
            raise CoverageError(
                f"App path dependency {name!r} 不在仓库内或目录不存在: {candidate}"
            )
        roots.add(resolved)
    return sorted(roots, key=lambda path: path.as_posix())


def _required_safe_files(paths: Sequence[Path], *, label: str) -> list[Path]:
    missing = [path for path in paths if not path.is_file() or path.is_symlink()]
    if missing:
        raise CoverageError(
            f"{label} 缺少安全普通文件: "
            + ", ".join(_display(path) for path in missing)
        )
    return list(paths)


def _app_source_closure_files() -> list[Path]:
    """返回会影响 App 覆盖产物的 production/package source closure。"""
    source = sorted((cc.APP_ROOT / "lib").rglob("*.dart"))
    source += _required_safe_files(
        (
            cc.APP_ROOT / ".flutter-version",
            cc.APP_ROOT / "pubspec.yaml",
            cc.APP_ROOT / "pubspec.lock",
        ),
        label="App source closure",
    )
    for dependency_root in _app_local_path_dependency_roots():
        source += _provenance_tree_files(
            dependency_root,
            excluded_directory_names=LOCAL_DEPENDENCY_EXCLUDED_DIRECTORY_NAMES,
        )
    return sorted(set(source), key=lambda path: path.as_posix())


def _app_collection_inputs() -> tuple[list[Path], list[Path]]:
    source = _app_source_closure_files()
    # Golden/fixture 也是测试输入；只排除 Flutter golden 失败时生成的 diff 输出。
    tests = _provenance_tree_files(
        cc.APP_ROOT / APP_TEST_TARGET,
        excluded_directory_names=frozenset({"failures"}),
    )
    tests += _provenance_tree_files(
        cc.APP_ROOT / "test/support",
        excluded_directory_names=frozenset({"failures"}),
    )
    return source, tests


def _service_collection_inputs(target: str) -> tuple[list[Path], list[Path]]:
    if target == SHARED_RUNTIME_COLLECTION_TARGET:
        source_candidates = [
            path
            for root_name in SHARED_RUNTIME_COVERPKG_PATTERNS
            for path in _provenance_tree_files(SERVICE_ROOT / root_name)
        ]
        source = sorted(
            path for path in source_candidates if not path.name.endswith("_test.go")
        )
        tests = sorted(
            path for path in source_candidates if path.name.endswith("_test.go")
        )
        if not source or not tests:
            raise CoverageError(
                "shared runtime coverage 必须同时拥有 production source 与 tests"
            )
        return source, tests
    language = _collection_target_language(target)
    service_root = cc.ROOT / target
    if language == "python":
        source = sorted(
            path
            for root_name in PYTHON_TRACE_SOURCE_ROOTS
            for path in _provenance_tree_files(service_root / root_name)
        )
        tests = _provenance_tree_files(service_root / PYTHON_SERVICE_TEST_TARGET)
        if not source or not tests:
            raise CoverageError(
                f"{target}: Python coverage 必须同时拥有 production source 与 "
                f"{PYTHON_SERVICE_TEST_TARGET}"
            )
        return source, tests
    source_candidates = [
        path
        for root_name in SERVICE_COVERPKG_PATTERNS
        for path in _provenance_tree_files(service_root / root_name)
    ]
    source = sorted(
        path for path in source_candidates if not path.name.endswith("_test.go")
    )
    tests = sorted(
        path
        for root_name in SERVICE_COVERPKG_PATTERNS
        for path in _provenance_tree_files(service_root / root_name)
        if path.name.endswith("_test.go")
    )
    tests += sorted(
        path
        for path in _provenance_tree_files(service_root / "tests")
        if SERVICE_EXCLUDED_PACKAGE_MARKER not in path.as_posix()
    )
    return source, tests


def _collection_config_inputs(target: str) -> list[Path]:
    if target == APP_COLLECTION_TARGET:
        ops_environment_root = cc.ROOT / "quwoquan_ops" / "environments"
        ops_cli_lib = cc.ROOT / "quwoquan_ops" / "cli" / "lib"
        required = _required_safe_files(
            (
                cc.APP_ROOT / ".flutter-version",
                cc.APP_ROOT / "pubspec.yaml",
                cc.APP_ROOT / "pubspec.lock",
                cc.APP_ROOT / APP_FLUTTER_TEST_RUNNER,
                cc.APP_ROOT / APP_RUNTIME_DEFINE_RESOLVER,
                cc.APP_ROOT / APP_TEST_SELECTION_POLICY,
                cc.APP_ROOT / "scripts/_common/__init__.py",
                ops_cli_lib / "common.py",
                ops_cli_lib / "environment_topology.py",
                ops_cli_lib / "output_paths.py",
                ops_cli_lib / "port_manifest.py",
                ops_environment_root / "domain_governance.yaml",
                ops_environment_root / "local_env_port_manifest.yaml",
                *sorted(ops_environment_root.glob("*/runtime.yaml")),
            ),
            label="App coverage config",
        )
        optional = (
            cc.APP_ROOT / "analysis_options.yaml",
            cc.APP_ROOT / "dart_test.yaml",
            cc.APP_ROOT / "test/flutter_test_config.dart",
        )
    else:
        language = _collection_target_language(target)
        if language == "python":
            service_root = cc.ROOT / target
            required = _required_safe_files(
                (
                    service_root / "Makefile",
                    service_root / "pyproject.toml",
                    service_root / PYTHON_COVERAGE_TOOLCHAIN_LOCK,
                ),
                label="Python coverage config",
            )
            optional = tuple(sorted(service_root.rglob("requirements*.txt")))
        else:
            required = _required_safe_files(
                (SERVICE_ROOT / "go.mod", SERVICE_ROOT / "go.sum"),
                label="Go coverage config",
            )
            optional = ()
    return required + [path for path in optional if path.is_file() or path.is_symlink()]


def _rule_source_files(entry_file: Path, package_name: str) -> list[Path]:
    """规则实现拆分为「薄入口 + 包」后，digest 输入必须覆盖全部实现模块。

    入口旁不存在实现包时（fixture 树用单文件替身驱动测试）退化为仅入口，
    保持拆分前的单文件语义。
    """
    entry = Path(entry_file).resolve()
    package_dir = entry.parent / package_name
    return [entry, *sorted(path.resolve() for path in package_dir.glob("*.py"))]


def _attribution_inputs() -> list[Path]:
    return [
        cc.ROOT / opm.CONTRACT_GRAPH_PATH,
        cc.ROOT / opm.PAGE_OBJECT_CONTRACT_PATH,
        *_rule_source_files(Path(opm.__file__), "object_path_map_lib"),
        *_rule_source_files(Path(vaa.__file__), "app_architecture"),
    ]


def _collection_scope_digest(target: str) -> str:
    if target == APP_COLLECTION_TARGET:
        command = [
            "<current-python>",
            APP_FLUTTER_TEST_RUNNER.as_posix(),
            "--coverage",
            "--branch-coverage",
            "--coverage-path=<artifact>",
            "--reporter=compact",
            "--dart-define=APP_RUNTIME_ENV=alpha",
            "<phase-concurrency>",
            "<exclude-serial|serial-only>",
            "<canonical-app-test-shard-phase>",
        ]
        app_runtime_policy = app_coverage_policy_identity()
        scopes = [unit_scope(unit) for unit in cc.discover_app_units()]
    else:
        language = _collection_target_language(target)
        scopes = [
            unit_scope(unit)
            for unit in cc.discover_cloud_units()
            if target in cloud_collection_targets_for_unit(unit)
        ]
        if language == "python":
            command = [
                "<managed-python>",
                "-B",
                "<stdlib-trace-runner>",
                "-q",
                PYTHON_SERVICE_TEST_TARGET,
                "--artifact=<artifact>",
            ]
        else:
            package_shape = (
                "<runtime,internal/platform,cmd>"
                if target == SHARED_RUNTIME_COLLECTION_TARGET
                else "<internal,cmd>"
            )
            command = [
                "go",
                "test",
                "-count=1",
                f"-p={SERVICE_GO_TEST_PACKAGE_PARALLELISM}",
                "-covermode=atomic",
                "-coverprofile=<artifact>",
                f"-coverpkg={package_shape}",
                "<go-list-without-api-integration>",
            ]
    payload = {
        "ruleId": RULE_ID,
        "target": target,
        "command": command,
        "scopes": scopes,
        # 门禁拆分为「薄入口 + canonical_coverage 包」后，摘要覆盖全部实现
        # 文件：任一模块的规则漂移都必须使采集范围 digest 变化。
        "gateSourceDigest": _sha256_bytes(
            "\n".join(
                _sha256_file(path)
                for path in _rule_source_files(
                    Path(__file__).resolve().parents[1]
                    / "verify_canonical_coverage.py",
                    "canonical_coverage",
                )
            ).encode("utf-8")
        ),
    }
    if target == APP_COLLECTION_TARGET:
        payload["appRuntimePolicy"] = app_runtime_policy
    return _sha256_bytes(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _identity_command(command: Sequence[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        list(command), cwd=cwd, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise CoverageError(
            f"provenance identity command 失败 ({' '.join(command)}, "
            f"exit={completed.returncode}): {_tail(completed.stderr)}"
        )
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    if not output:
        raise CoverageError(f"provenance identity command 无输出: {' '.join(command)}")
    return output


def _flutter_toolchain_identity() -> dict[str, object]:
    """Return the canonical machine-readable Flutter toolchain identity.

    Flutter can emit a transient SDK-lock wait message on stderr while another
    process is starting.  That diagnostic is not toolchain identity and must
    not make otherwise identical coverage receipts stale.  A non-zero exit or
    malformed machine JSON still fails closed.
    """
    command = ["flutter", "--version", "--machine"]
    completed = subprocess.run(
        command, cwd=cc.APP_ROOT, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise CoverageError(
            "provenance Flutter identity command 失败 "
            f"(exit={completed.returncode}): {_tail(completed.stderr)}"
        )
    try:
        identity = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CoverageError("provenance Flutter machine identity 不是合法 JSON") from exc
    if not isinstance(identity, dict) or not identity:
        raise CoverageError("provenance Flutter machine identity 必须是非空对象")
    return identity


def _python_collection_executable(target: str) -> Path:
    """返回 Recommendation Makefile 声明的受管 Python 环境。"""
    if target not in python_collection_targets():
        raise CoverageError(f"{target}: 不是 Python coverage target")
    executable = Path.home() / PYTHON_MANAGED_ENV_RELATIVE
    if not executable.exists() or not os.access(executable, os.X_OK):
        raise CoverageError(
            f"{target}: 缺少受管 Python 测试环境 {executable}；先执行 "
            f"make -C {target} prepare-test-python"
        )
    return executable


def _canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_python_coverage_toolchain_lock(text: str) -> dict[str, str]:
    """解析只允许 exact ``name==version`` 的 coverage toolchain lock。"""
    locked: dict[str, str] = {}
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PYTHON_EXACT_REQUIREMENT_RE.fullmatch(line)
        if match is None:
            raise CoverageError(
                f"Python coverage toolchain lock 第 {number} 行不是 exact requirement: "
                f"{line!r}"
            )
        name = _canonical_distribution_name(match.group("name"))
        if name in locked:
            raise CoverageError(
                f"Python coverage toolchain lock 重复 dependency: {name}"
            )
        locked[name] = match.group("version")
    if "pytest" not in locked:
        raise CoverageError("Python coverage toolchain lock 缺少 exact pytest==version")
    return locked


PYTHON_TOOLCHAIN_PROBE = r"""
import hashlib
import importlib
import importlib.metadata
import json
import pathlib
import sys
import trace

trace_path = pathlib.Path(trace.__file__).resolve()
pytest_path = pathlib.Path(importlib.import_module("pytest").__file__).resolve()
print(json.dumps({
    "basePrefix": sys.base_prefix,
    "pythonExecutable": sys.executable,
    "pythonVersion": sys.version,
    "pytestPath": str(pytest_path),
    "pytestVersion": importlib.metadata.version("pytest"),
    "traceDigest": "sha256:" + hashlib.sha256(trace_path.read_bytes()).hexdigest(),
    "tracePath": str(trace_path),
}, sort_keys=True, separators=(",", ":")))
"""


def _python_toolchain_state(target: str) -> dict[str, object]:
    """验证并返回会完整进入 ``toolchainDigest`` 的 Python runner 身份。"""
    executable = cc._python_collection_executable(target)
    service_root = cc.ROOT / target
    lock_path = service_root / PYTHON_COVERAGE_TOOLCHAIN_LOCK
    if not lock_path.is_file() or lock_path.is_symlink():
        raise CoverageError(f"{target}: 缺少安全 coverage toolchain lock: {lock_path}")
    locked = _parse_python_coverage_toolchain_lock(
        lock_path.read_text(encoding="utf-8")
    )
    lock_digest = _sha256_file(lock_path)
    marker_path = executable.parent.parent / PYTHON_COVERAGE_TOOLCHAIN_MARKER
    if not marker_path.is_file() or marker_path.is_symlink():
        raise CoverageError(
            f"{target}: 缺少受管 coverage toolchain marker: {marker_path}"
        )
    marker = marker_path.read_text(encoding="utf-8").strip()
    if marker != lock_digest.removeprefix("sha256:"):
        raise CoverageError(f"{target}: coverage toolchain marker 与 tracked lock 漂移")
    try:
        probe = json.loads(
            cc._identity_command(
                [str(executable), "-B", "-c", PYTHON_TOOLCHAIN_PROBE],
                cwd=service_root,
            )
        )
    except json.JSONDecodeError as error:
        raise CoverageError(
            f"{target}: Python coverage toolchain probe 非 JSON"
        ) from error
    required_probe_fields = {
        "basePrefix",
        "pythonExecutable",
        "pythonVersion",
        "pytestPath",
        "pytestVersion",
        "traceDigest",
        "tracePath",
    }
    if not isinstance(probe, dict) or set(probe) != required_probe_fields:
        raise CoverageError(
            f"{target}: Python coverage toolchain probe fields mismatch"
        )
    if Path(str(probe["pythonExecutable"])) != executable:
        raise CoverageError(
            f"{target}: collection Python executable 漂移: "
            f"{probe['pythonExecutable']!r} != {str(executable)!r}"
        )
    expected_pytest = locked["pytest"]
    if probe["pytestVersion"] != expected_pytest:
        raise CoverageError(
            f"{target}: pytest version 漂移: "
            f"expected={expected_pytest!r}, actual={probe['pytestVersion']!r}"
        )
    pytest_path = Path(str(probe["pytestPath"]))
    if (
        not pytest_path.is_absolute()
        or not pytest_path.is_file()
        or pytest_path.is_symlink()
        or not pytest_path.resolve().is_relative_to(executable.parent.parent.resolve())
    ):
        raise CoverageError(
            f"{target}: pytest 不是受管 rec-model environment 文件: {pytest_path}"
        )
    trace_path = Path(str(probe["tracePath"]))
    base_prefix = Path(str(probe["basePrefix"])).resolve()
    if (
        not trace_path.is_absolute()
        or not trace_path.is_file()
        or trace_path.is_symlink()
        or not trace_path.resolve().is_relative_to(base_prefix)
    ):
        raise CoverageError(
            f"{target}: trace module 不是 collection Python 的安全 stdlib 文件: "
            f"{trace_path}"
        )
    actual_trace_digest = _sha256_file(trace_path)
    if probe["traceDigest"] != actual_trace_digest:
        raise CoverageError(f"{target}: trace module bytes 在 probe 期间漂移")
    freeze_lines = sorted(
        line.strip()
        for line in cc._identity_command(
            [str(executable), "-m", "pip", "freeze", "--all"],
            cwd=service_root,
        ).splitlines()
        if line.strip()
    )
    frozen: dict[str, str] = {}
    for line in freeze_lines:
        match = PYTHON_EXACT_REQUIREMENT_RE.fullmatch(line)
        if match is None:
            raise CoverageError(
                f"{target}: pip freeze 含非 exact dependency，不能形成 toolchain identity: "
                f"{line!r}"
            )
        name = _canonical_distribution_name(match.group("name"))
        if name in frozen:
            raise CoverageError(f"{target}: pip freeze 重复 dependency: {name}")
        frozen[name] = match.group("version")
    drifted = {
        name: {"expected": version, "actual": frozen.get(name)}
        for name, version in locked.items()
        if frozen.get(name) != version
    }
    if drifted:
        raise CoverageError(
            f"{target}: coverage toolchain lock 与 pip freeze 漂移: {drifted}"
        )
    return {
        "lockDigest": lock_digest,
        "lockedRequirements": locked,
        "pipFreeze": freeze_lines,
        "pythonExecutable": probe["pythonExecutable"],
        "pythonResolvedExecutable": str(executable.resolve()),
        "pythonVersion": probe["pythonVersion"],
        "pytestPath": probe["pytestPath"],
        "pytestVersion": probe["pytestVersion"],
        "traceDigest": actual_trace_digest,
        "tracePath": str(trace_path),
    }


def _git_head_identity() -> dict[str, str]:
    identity = {
        "headCommit": cc._identity_command(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=cc.ROOT
        ),
        "headTree": cc._identity_command(
            ["git", "rev-parse", "--verify", "HEAD^{tree}"], cwd=cc.ROOT
        ),
    }
    malformed = sorted(
        key for key, value in identity.items() if GIT_OBJECT_RE.fullmatch(value) is None
    )
    if malformed:
        raise CoverageError(
            "HEAD provenance 非 canonical git object id: " + ", ".join(malformed)
        )
    return identity


def _toolchain_digest(target: str) -> str:
    identity: dict[str, object] = {
        "pythonImplementation": platform.python_implementation(),
        "pythonVersion": platform.python_version(),
    }
    if target == APP_COLLECTION_TARGET:
        identity["flutter"] = cc._flutter_toolchain_identity()
        identity["dart"] = cc._identity_command(["dart", "--version"], cwd=cc.APP_ROOT)
    elif _collection_target_language(target) == "python":
        identity["coverageToolchain"] = _python_toolchain_state(target)
    else:
        identity["go"] = cc._identity_command(["go", "version"], cwd=SERVICE_ROOT)
        identity["goEnvironment"] = cc._identity_command(
            ["go", "env", "GOVERSION", "GOOS", "GOARCH", "CGO_ENABLED"],
            cwd=SERVICE_ROOT,
        )
    return _canonical_json_digest(identity)


def current_collection_identity(target: str) -> dict[str, str]:
    if target == APP_COLLECTION_TARGET:
        source, tests = cc._app_collection_inputs()
    else:
        source, tests = _service_collection_inputs(target)
    return {
        **cc._git_head_identity(),
        "sourceTreeDigest": _tree_digest(source, label=f"{target} production source"),
        "testTreeDigest": _tree_digest(tests, label=f"{target} tests"),
        "attributionDigest": _tree_digest(
            cc._attribution_inputs(), label="coverage attribution"
        ),
        "configDigest": _tree_digest(
            cc._collection_config_inputs(target), label=f"{target} collection config"
        ),
        "toolchainDigest": cc._toolchain_digest(target),
        "collectionScopeDigest": cc._collection_scope_digest(target),
    }
