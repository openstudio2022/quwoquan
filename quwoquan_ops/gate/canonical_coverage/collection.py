"""覆盖率采集执行：端侧分片 flutter test、Python trace 与 Go coverprofile。

端侧分片只是执行方式：所有测试文件都会被执行一次，合并按 `DA`/`BRDA` 明细取
并集并累加命中数，与全量运行语义等价。除 import 重组外与拆分前逐字一致；
被测试 monkeypatch 的符号（``_run``、``APP_ROOT``、``current_collection_identity``、
``collect_app`` 等）经包命名空间 ``cc`` 在调用期解析。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Sequence

import quwoquan_ops.gate.canonical_coverage as cc

from .constants import (
    APP_COLLECTION_TARGET,
    APP_SHARD_DIRECTORY_NAME,
    APP_SHARD_MAX_TEST_FILES,
    APP_SHARD_STATE_SCHEMA,
    APP_TEST_FILE_SUFFIX,
    APP_TEST_TARGET,
    PYTHON_SERVICE_TEST_TARGET,
    PYTHON_TRACE_ARTIFACT_SCHEMA,
    RULE_ID,
    SERVICE_COVERPKG_PATTERNS,
    SERVICE_EXCLUDED_PACKAGE_MARKER,
    SERVICE_GO_TEST_PACKAGE_PARALLELISM,
    SERVICE_PACKAGE_PATTERNS,
    SERVICE_ROOT,
    SHARED_RUNTIME_COLLECTION_TARGET,
    SHARED_RUNTIME_COVERPKG_PATTERNS,
    SHARED_RUNTIME_PACKAGE_PATTERNS,
    CoverageError,
    RedTestRun,
    _display,
    _tail,
)
from .app_runtime import (
    canonical_app_coverage_environment,
    guarded_app_coverage_command,
    serial_app_test_files,
)
from .parsing import merge_lcov_records, parse_lcov_records, render_lcov
from .provenance import (
    _canonical_json_digest,
    _sha256_file,
    artifact_path,
    artifact_receipt_path,
)
from .receipts import _write_artifact_receipt, _write_json_atomic, _write_text_atomic
from .units import _collection_target_language, go_collection_targets


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def app_test_files() -> tuple[str, ...]:
    """按 canonical 顺序枚举 `APP_TEST_TARGET` 下全部测试文件（相对 App 根）。

    这份清单必须与 `flutter test <APP_TEST_TARGET>` 自己会收集的集合一致：
    package:test 取该目录下所有 ``*_test.dart``，并跳过点开头的隐藏路径。排序用
    posix 路径字节序，使分片方案只由磁盘内容决定，不受文件系统遍历顺序影响。
    """
    root = cc.APP_ROOT / APP_TEST_TARGET
    if not root.is_dir() or root.is_symlink():
        raise CoverageError(f"App 测试根不是安全目录: {_display(root)}")
    files: list[str] = []
    for path in root.rglob(f"*{APP_TEST_FILE_SUFFIX}"):
        relative = path.relative_to(cc.APP_ROOT)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file():
            raise CoverageError(f"App 测试文件不是安全普通文件: {_display(path)}")
        files.append(relative.as_posix())
    if not files:
        raise CoverageError(
            f"{APP_TEST_TARGET} 下没有任何 {APP_TEST_FILE_SUFFIX}；采集范围为空即 BLOCK"
        )
    return tuple(sorted(files))


def default_app_shard_count(test_files: Sequence[str]) -> int:
    """按测试文件数派生默认片数，避免把片数写死成会随仓库增长而失效的常数。"""
    return max(1, -(-len(test_files) // APP_SHARD_MAX_TEST_FILES))


def app_shard_plan(
    test_files: Sequence[str], shard_count: int
) -> tuple[tuple[str, ...], ...]:
    """把已排序的测试文件切成 ``shard_count`` 段连续分片。

    切分只是 ``(排序后的文件清单, shard_count)`` 的纯函数：同样输入必然得到同样
    分片，覆盖率数字不会因为分片而抖动。前 ``remainder`` 片各多承载一个文件，
    保证片间大小相差不超过 1；连续切分让同一目录的测试尽量落在同一片，减少单片
    需要加载的库数量。每个文件恰好出现一次——分片是全集的划分，不是筛选。
    """
    if shard_count < 1:
        raise CoverageError(f"分片数必须 >= 1，实测 {shard_count}")
    if shard_count > len(test_files):
        raise CoverageError(
            f"分片数 {shard_count} 超过测试文件数 {len(test_files)}；空片没有意义"
        )
    size, remainder = divmod(len(test_files), shard_count)
    plan: list[tuple[str, ...]] = []
    cursor = 0
    for index in range(shard_count):
        span = size + (1 if index < remainder else 0)
        plan.append(tuple(test_files[cursor : cursor + span]))
        cursor += span
    return tuple(plan)


def app_shard_directory() -> Path:
    return cc.COVERAGE_CACHE_DIR / APP_SHARD_DIRECTORY_NAME


def _app_shard_artifact_paths(index: int, shard_count: int) -> tuple[Path, Path]:
    """返回该片的 ``(lcov, state)`` 路径；片数进文件名，换片数即换一组文件。"""
    stem = f"shard-{index:04d}-of-{shard_count:04d}"
    directory = app_shard_directory()
    return directory / f"{stem}.lcov.info", directory / f"{stem}.state.json"


def _reusable_shard_lcov(
    lcov_path: Path, state_path: Path, expected_state: dict[str, object]
) -> str | None:
    """只有「绿 + 未漂移 + 字节未被改动」的片才允许跳过重跑。

    任何一项对不上都返回 ``None`` 让调用方重跑该片：断点续跑是省时间的手段，
    不能变成让陈旧或红的片混进合并结果的路径。
    """
    if not state_path.is_file() or state_path.is_symlink():
        return None
    if not lcov_path.is_file() or lcov_path.is_symlink():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("testsGreen") is not True:
        return None
    if any(payload.get(key) != value for key, value in expected_state.items()):
        return None
    if payload.get("lcovDigest") != _sha256_file(lcov_path):
        return None
    return lcov_path.read_text(encoding="utf-8", errors="replace")


def _run_app_shard(destination: Path, test_files: Sequence[str]) -> str:
    """跑一片测试；返回失败摘要，空串表示该片全绿。

    产不出 lcov（例如该片自己被 OOM 杀掉）不是「红测试」而是采集失败，必须以
    `CoverageError` 阻断：把它当成红测试会让 receipt 记下一份不完整的产物。
    """
    serial_files = serial_app_test_files(test_files)
    phases = [("nonserial", tuple(test_files), False)]
    if serial_files:
        phases.append(("serial", serial_files, True))

    merged: dict[str, dict] = {}
    failures: list[str] = []
    phase_paths: list[Path] = []
    try:
        for phase_name, phase_files, serial_phase in phases:
            phase_path = destination.with_name(
                f"{destination.name}.{phase_name}.tmp"
            )
            phase_paths.append(phase_path)
            phase_path.unlink(missing_ok=True)
            completed = cc._run(
                guarded_app_coverage_command(
                    phase_path,
                    phase_files,
                    serial_phase=serial_phase,
                ),
                cwd=cc.APP_ROOT,
                env=canonical_app_coverage_environment(),
            )
            if not phase_path.is_file():
                raise CoverageError(
                    f"flutter test {phase_name} phase 未产出 lcov: "
                    f"{_display(phase_path)}（exit={completed.returncode}）\n"
                    f"{_tail(completed.stdout)}{_tail(completed.stderr)}"
                )
            merge_lcov_records(
                merged,
                parse_lcov_records(
                    phase_path.read_text(encoding="utf-8", errors="replace")
                ),
            )
            if completed.returncode != 0:
                failures.append(
                    f"{phase_name} phase exit={completed.returncode}\n"
                    f"{_tail(completed.stdout)}{_tail(completed.stderr)}"
                )
        _write_text_atomic(destination, render_lcov(merged))
    finally:
        for phase_path in phase_paths:
            phase_path.unlink(missing_ok=True)
    return "\n".join(failures)


def collect_app(
    destination: Path,
    *,
    shards: int | None = None,
    identity: dict[str, str] | None = None,
) -> None:
    """分片采集端侧行/分支覆盖率，合并成与全量运行语义等价的单份 lcov。

    分片只改变执行方式：所有测试文件都会被执行一次，合并按 `DA`/`BRDA` 明细取
    并集并累加命中数。任一片红都在跑完全部分片后抛 `RedTestRun`——与全量运行
    「跑完所有测试再以非零码退出」同形，产物照样落盘供诊断，但 receipt 会记
    ``testsGreen=false``，复用与写基线两条路径都被拒绝。
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()

    test_files = app_test_files()
    shard_count = default_app_shard_count(test_files) if shards is None else shards
    plan = app_shard_plan(test_files, shard_count)
    plan_digest = _canonical_json_digest([list(shard) for shard in plan])
    identity_digest = _canonical_json_digest(
        identity
        if identity is not None
        else cc.current_collection_identity(APP_COLLECTION_TARGET)
    )

    directory = app_shard_directory()
    directory.mkdir(parents=True, exist_ok=True)
    expected_names = {
        path.name
        for index in range(shard_count)
        for path in _app_shard_artifact_paths(index, shard_count)
    }
    for path in directory.iterdir():
        # 只清理本目录里不属于当前分片方案的可重建中间产物。
        if path.name not in expected_names and path.is_file():
            path.unlink()

    merged: dict[str, dict] = {}
    red: list[str] = []
    for index, shard_files in enumerate(plan):
        lcov_path, state_path = _app_shard_artifact_paths(index, shard_count)
        expected_state: dict[str, object] = {
            "schema": APP_SHARD_STATE_SCHEMA,
            "ruleId": RULE_ID,
            "shardIndex": index,
            "shardCount": shard_count,
            "planDigest": plan_digest,
            "shardDigest": _canonical_json_digest(list(shard_files)),
            "collectionIdentityDigest": identity_digest,
        }
        text = _reusable_shard_lcov(lcov_path, state_path, expected_state)
        if text is None:
            state_path.unlink(missing_ok=True)
            lcov_path.unlink(missing_ok=True)
            print(
                f"verify_canonical_coverage: app shard {index + 1}/{shard_count}"
                f" ({len(shard_files)} test file(s)) ...",
                flush=True,
            )
            failure = _run_app_shard(lcov_path, shard_files)
            text = lcov_path.read_text(encoding="utf-8", errors="replace")
            _write_json_atomic(
                state_path,
                {
                    **expected_state,
                    "lcovDigest": _sha256_file(lcov_path),
                    "testsGreen": not failure,
                },
            )
            if failure:
                red.append(f"shard {index + 1}/{shard_count}: {failure}")
        else:
            print(
                f"verify_canonical_coverage: app shard {index + 1}/{shard_count}"
                " reused (green, unchanged)",
                flush=True,
            )
        merge_lcov_records(merged, parse_lcov_records(text))

    if not merged:
        raise CoverageError(
            f"分片采集没有产出任何 lcov 记录（{shard_count} 片）；采集没有真正生效"
        )
    _write_text_atomic(destination, render_lcov(merged))
    if red:
        raise RedTestRun(
            f"flutter test 分片失败（{len(red)}/{shard_count} 片红）；"
            "覆盖率必须来自绿的测试。\n" + "\n".join(red)
        )


PYTHON_TRACE_RUNNER = r"""
import json
import os
import pathlib
import sys
import trace

import pytest

schema, destination, test_target = sys.argv[1:4]
service_root = pathlib.Path.cwd().resolve()
sources = sorted(
    path.resolve()
    for root_name in ("internal", "cmd")
    for path in (service_root / root_name).rglob("*.py")
    if path.is_file() and not path.is_symlink()
)
tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.base_prefix])
exit_code = int(tracer.runfunc(pytest.main, ["-q", test_target]))
counts = tracer.results().counts
files = {}
for source in sources:
    executable = set(trace._find_executable_linenos(str(source)))
    covered = {
        line
        for (filename, line), count in counts.items()
        if count > 0 and pathlib.Path(filename).resolve() == source
    }
    relative = source.relative_to(service_root).as_posix()
    files[relative] = {
        "coveredStatements": len(covered & executable),
        "totalStatements": len(executable),
    }
payload = {"schema": schema, "files": files}
output = pathlib.Path(destination)
output.parent.mkdir(parents=True, exist_ok=True)
temporary = output.with_name(output.name + ".tmp")
temporary.write_text(
    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    + "\n",
    encoding="utf-8",
)
os.replace(temporary, output)
raise SystemExit(exit_code)
"""


def collect_python_service(service_relative: str, destination: Path) -> None:
    """用标准库 trace 跑 Python service 的 canonical local_contract。"""
    executable = cc._python_collection_executable(service_relative)
    service_root = cc.ROOT / service_relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    completed = cc._run(
        [
            str(executable),
            "-B",
            "-c",
            PYTHON_TRACE_RUNNER,
            PYTHON_TRACE_ARTIFACT_SCHEMA,
            str(destination),
            PYTHON_SERVICE_TEST_TARGET,
        ],
        cwd=service_root,
    )
    if not destination.is_file():
        raise CoverageError(
            f"{service_relative}: Python trace 未产出 statement artifact: {destination}"
        )
    if completed.returncode != 0:
        raise RedTestRun(
            f"pytest 失败（{service_relative}, exit={completed.returncode}）；"
            "覆盖率必须来自绿的测试。\n"
            f"{_tail(completed.stdout)}{_tail(completed.stderr)}"
        )


def collect_service(service_relative: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    if service_relative == SHARED_RUNTIME_COLLECTION_TARGET:
        package_patterns = SHARED_RUNTIME_PACKAGE_PATTERNS
        coverpkg_patterns = SHARED_RUNTIME_COVERPKG_PATTERNS
    else:
        if service_relative not in go_collection_targets():
            raise CoverageError(f"未知覆盖率采集目标 {service_relative!r}")
        inside_module = service_relative[len(SERVICE_ROOT.name) + 1 :]
        package_patterns = tuple(
            f"{inside_module}/{pattern}" for pattern in SERVICE_PACKAGE_PATTERNS
        )
        coverpkg_patterns = tuple(
            f"{inside_module}/{pattern}" for pattern in SERVICE_COVERPKG_PATTERNS
        )
    listed = cc._run(
        ["go", "list"] + [f"./{pattern}/..." for pattern in package_patterns],
        cwd=SERVICE_ROOT,
    )
    if listed.returncode != 0:
        raise CoverageError(
            f"go list 失败（{service_relative}, exit={listed.returncode}）\n"
            f"{_tail(listed.stderr)}"
        )
    packages = [
        line.strip()
        for line in listed.stdout.splitlines()
        if line.strip() and SERVICE_EXCLUDED_PACKAGE_MARKER not in line
    ]
    if not packages:
        raise CoverageError(f"{service_relative}: go list 没有返回任何可测包")
    coverpkg = ",".join(f"./{pattern}/..." for pattern in coverpkg_patterns)
    completed = cc._run(
        [
            "go",
            "test",
            "-count=1",
            f"-p={SERVICE_GO_TEST_PACKAGE_PARALLELISM}",
            "-covermode=atomic",
            f"-coverprofile={destination}",
            f"-coverpkg={coverpkg}",
        ]
        + packages,
        cwd=SERVICE_ROOT,
    )
    if not destination.is_file():
        raise CoverageError(
            f"{service_relative}: go test 未产出 coverprofile: {destination}"
        )
    if completed.returncode != 0:
        raise RedTestRun(
            f"go test 失败（{service_relative}, exit={completed.returncode}）；"
            "覆盖率必须来自绿的测试。\n"
            f"{_tail(completed.stdout)}{_tail(completed.stderr)}"
        )


def collect(target: str, *, app_shards: int | None = None) -> None:
    destination = artifact_path(target)
    receipt = artifact_receipt_path(target)
    receipt.unlink(missing_ok=True)
    before = cc.current_collection_identity(target)
    red_error: RedTestRun | None = None
    try:
        if target == APP_COLLECTION_TARGET:
            cc.collect_app(destination, shards=app_shards, identity=before)
        elif _collection_target_language(target) == "python":
            collect_python_service(target, destination)
        else:
            collect_service(target, destination)
    except RedTestRun as error:
        red_error = error
    after = cc.current_collection_identity(target)
    if before != after:
        destination.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
        raise CoverageError(f"{target}: 覆盖率采集期间源码/测试/归属/采集范围发生漂移")
    _write_artifact_receipt(target, tests_green=red_error is None, identity=before)
    if red_error is not None:
        raise red_error
