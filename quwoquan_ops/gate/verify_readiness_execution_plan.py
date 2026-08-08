#!/usr/bin/env python3
"""从 ContractGraph 提取只读 readiness execution plan。

本脚本不重算 readiness policy，也不生产 result、receipt、signature 或
ReadinessResultBundle。唯一业务投影由 Go `tools/plan_readiness_execution`
完成；Python 只负责进程隔离、输入/输出摘要、超时、0/2 退出协议和单 JSON 校验。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "quwoquan_service"
DEFAULT_REPORT_DIR = (
    ROOT / ".qwq_output" / "env" / "repo" / "runs" / "readiness-execution-plan"
)
DEFAULT_BUILD_ROOT = (
    ROOT / ".qwq_output" / "env" / "repo" / "local" / "readiness-execution-plan"
)
PLANNER_PACKAGE = "./tools/plan_readiness_execution"
PLAN_SCHEMA = "readiness-execution-plan/v1"
REPORT_SCHEMA = "readiness-execution-plan-report/v1"
BUILD_TIMEOUT_SECONDS = 120
RUN_TIMEOUT_SECONDS = 60
MAX_GRAPH_BYTES = 128 << 20
MAX_PLAN_BYTES = 32 << 20
SHA256_HEX_LENGTH = 64


class GateBlock(RuntimeError):
    """输入或 planner 协议不可信，调用方必须保持 GATE_BLOCK。"""


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    sha256: str


CommandRunner = Callable[..., subprocess.CompletedProcess[bytes]]


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract the graph-authored readiness execution plan."
    )
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    return parser.parse_args(argv)


def read_stable_regular_file(path: Path, limit: int) -> tuple[bytes, FileIdentity]:
    try:
        before = path.lstat()
    except OSError as error:
        raise GateBlock(f"无法读取输入 {path}: {error}") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise GateBlock(f"输入必须是 regular file 且不能是 symlink: {path}")
    if before.st_size <= 0 or before.st_size > limit:
        raise GateBlock(f"输入大小不合法: {path}")
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size != before.st_size
            ):
                raise GateBlock(f"输入在打开期间发生漂移: {path}")
            payload = handle.read(limit + 1)
        after = path.lstat()
    except OSError as error:
        raise GateBlock(f"读取输入失败 {path}: {error}") from error
    if len(payload) != before.st_size or len(payload) > limit:
        raise GateBlock(f"输入在读取期间发生漂移: {path}")
    if (
        after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise GateBlock(f"输入在读取期间发生漂移: {path}")
    digest = hashlib.sha256(payload).hexdigest()
    return payload, FileIdentity(
        device=before.st_dev,
        inode=before.st_ino,
        size=before.st_size,
        modified_ns=before.st_mtime_ns,
        sha256=digest,
    )


def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise GateBlock(f"planner 输出包含重复 JSON key: {key}")
        result[key] = value
    return result


def parse_single_json(payload: bytes) -> dict[str, object]:
    if len(payload) == 0 or len(payload) > MAX_PLAN_BYTES:
        raise GateBlock("planner 输出大小不合法")
    try:
        text = payload.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                GateBlock(f"planner 输出包含非法 JSON constant: {value}")
            ),
        )
        document, end = decoder.raw_decode(text.lstrip())
        offset = len(text) - len(text.lstrip()) + end
    except (UnicodeDecodeError, json.JSONDecodeError, GateBlock) as error:
        if isinstance(error, GateBlock):
            raise
        raise GateBlock(f"planner 输出不是合法单一 JSON: {error}") from error
    if text[offset:].strip():
        raise GateBlock("planner 输出包含尾随内容或多个 JSON document")
    if not isinstance(document, dict):
        raise GateBlock("planner 输出根必须是 JSON object")
    return document


def require_exact_keys(
    document: dict[str, object], expected: set[str], label: str
) -> None:
    actual = set(document)
    if actual != expected:
        raise GateBlock(
            f"{label} keys 不匹配: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def validate_plan_protocol(plan: dict[str, object]) -> None:
    require_exact_keys(
        plan,
        {
            "schema",
            "contractGraphSourceHash",
            "caseCount",
            "executionSlotCount",
            "runnerSourceCount",
            "slots",
        },
        "plan",
    )
    if plan["schema"] != PLAN_SCHEMA:
        raise GateBlock(f"planner schema 不匹配: {plan['schema']!r}")
    source_hash = plan["contractGraphSourceHash"]
    if (
        not isinstance(source_hash, str)
        or len(source_hash) != SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in source_hash)
    ):
        raise GateBlock("planner contractGraphSourceHash 不合法")
    slots = plan["slots"]
    if not isinstance(slots, list):
        raise GateBlock("planner slots 必须是数组")
    for key in ("caseCount", "executionSlotCount", "runnerSourceCount"):
        value = plan[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise GateBlock(f"planner {key} 必须是非负整数")
    if plan["executionSlotCount"] != len(slots):
        raise GateBlock("planner executionSlotCount 与 slots 长度不一致")
    runner_sources: set[str] = set()
    for index, raw_slot in enumerate(slots):
        if not isinstance(raw_slot, dict):
            raise GateBlock(f"planner slots[{index}] 必须是 object")
        require_exact_keys(
            raw_slot,
            {
                "objectId",
                "specRef",
                "caseId",
                "producer",
                "layer",
                "target",
                "runnerSourcePath",
                "sourcePath",
                "execution",
            },
            f"slots[{index}]",
        )
        target = raw_slot["target"]
        execution = raw_slot["execution"]
        if not isinstance(target, dict) or set(target) != {"kind", "id"}:
            raise GateBlock(f"planner slots[{index}].target shape 不合法")
        if not isinstance(execution, dict) or set(execution) != {
            "environment",
            "platform",
            "deviceClass",
            "provider",
            "digestBinding",
        }:
            raise GateBlock(f"planner slots[{index}].execution shape 不合法")
        scalar_values = [
            raw_slot[key]
            for key in (
                "objectId",
                "specRef",
                "caseId",
                "producer",
                "layer",
                "runnerSourcePath",
                "sourcePath",
            )
        ] + list(target.values()) + list(execution.values())
        if any(not isinstance(value, str) or not value.strip() for value in scalar_values):
            raise GateBlock(f"planner slots[{index}] 含空或非字符串 identity")
        runner_sources.add(str(raw_slot["runnerSourcePath"]))
    if plan["runnerSourceCount"] != len(runner_sources):
        raise GateBlock("planner runnerSourceCount 与 slots 不一致")


def run_checked(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    runner: CommandRunner,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return runner(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise GateBlock(f"命令超时（{timeout}s）: {' '.join(command)}") from error
    except OSError as error:
        raise GateBlock(f"命令无法启动: {' '.join(command)}: {error}") from error


def extract_plan(
    graph_path: Path,
    report_dir: Path,
    *,
    build_root: Path = DEFAULT_BUILD_ROOT,
    runner: CommandRunner = subprocess.run,
) -> Path:
    _, graph_identity = read_stable_regular_file(graph_path, MAX_GRAPH_BYTES)
    build_root.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=build_root) as directory:
        binary = Path(directory) / "plan-readiness-execution"
        build = run_checked(
            ["go", "build", "-trimpath", "-o", str(binary), PLANNER_PACKAGE],
            cwd=SERVICE_ROOT,
            timeout=BUILD_TIMEOUT_SECONDS,
            runner=runner,
        )
        if build.returncode != 0:
            detail = build.stderr.decode("utf-8", errors="replace").strip()
            raise GateBlock(f"构建 readiness planner 失败: {detail}")
        _, binary_identity = read_stable_regular_file(binary, 128 << 20)
        outputs: list[bytes] = []
        for _ in range(2):
            completed = run_checked(
                [str(binary), "--graph", str(graph_path.resolve())],
                cwd=SERVICE_ROOT,
                timeout=RUN_TIMEOUT_SECONDS,
                runner=runner,
            )
            if completed.returncode not in {0, 2}:
                raise GateBlock(
                    f"readiness planner 返回非法 exit={completed.returncode}; 只允许 0/2"
                )
            if completed.returncode == 2:
                try:
                    failure = parse_single_json(completed.stdout)
                except GateBlock as error:
                    raise GateBlock(f"readiness planner exit=2 且输出非法: {error}") from error
                raise GateBlock(f"readiness planner 拒绝 ContractGraph: {failure}")
            outputs.append(completed.stdout)
        if outputs[0] != outputs[1]:
            raise GateBlock("同一 planner/graph 的两次 execution plan 输出不一致")
        plan = parse_single_json(outputs[0])
        validate_plan_protocol(plan)

    _, graph_after = read_stable_regular_file(graph_path, MAX_GRAPH_BYTES)
    if graph_after != graph_identity:
        raise GateBlock("ContractGraph 在 execution plan 提取期间发生漂移")
    plan_digest = hashlib.sha256(outputs[0]).hexdigest()
    report = {
        "schema": REPORT_SCHEMA,
        "contractGraph": {
            "path": str(graph_path.resolve()),
            "sha256": graph_identity.sha256,
        },
        "planner": {
            "package": PLANNER_PACKAGE,
            "binarySha256": binary_identity.sha256,
        },
        "planSha256": plan_digest,
        "plan": plan,
    }
    report_path = report_dir / (
        "readiness_execution_plan."
        f"{graph_identity.sha256[:16]}.{plan_digest[:16]}."
        f"{binary_identity.sha256[:16]}.json"
    )
    report_bytes = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(
            report_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        if report_path.read_bytes() != report_bytes:
            raise GateBlock(f"同 identity execution plan report 已存在但字节不同: {report_path}")
    else:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(report_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    _, graph_final = read_stable_regular_file(graph_path, MAX_GRAPH_BYTES)
    if graph_final != graph_identity:
        report_path.unlink(missing_ok=True)
        raise GateBlock("ContractGraph 在 execution plan report 落盘期间发生漂移")
    return report_path


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        report = extract_plan(arguments.graph, arguments.report_dir)
    except GateBlock as error:
        print(f"GATE_BLOCK {error}", file=sys.stderr)
        return 2
    document = json.loads(report.read_text(encoding="utf-8"))
    plan = document["plan"]
    print(
        "READINESS_EXECUTION_PLAN PASS "
        f"cases={plan['caseCount']} slots={plan['executionSlotCount']} "
        f"runners={plan['runnerSourceCount']} planSha256={document['planSha256']}"
    )
    print(f"report={report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
