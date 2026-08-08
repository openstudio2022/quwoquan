#!/usr/bin/env python3
"""调用 canonical Go collector 汇聚受信 readiness receipt。

本脚本只负责构建隔离、超时、输入漂移和 0/1/2 单 JSON 进程协议；
ContractGraph slot 投影、wire schema、签名/evidence trust 与 bundle 组装全部由
`quwoquan_service/tools/collect_readiness_result_bundle` 唯一实现。
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
from typing import BinaryIO, Callable, Sequence


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "quwoquan_service"
METADATA_DIR = SERVICE_ROOT / "contracts" / "metadata"
COLLECTOR_PACKAGE = "./tools/collect_readiness_result_bundle"
DEFAULT_BUILD_ROOT = (
    ROOT
    / ".qwq_output"
    / "env"
    / "repo"
    / "local"
    / "readiness-result-bundle"
    / "cache"
)
BUILD_TIMEOUT_SECONDS = 120
RUN_TIMEOUT_SECONDS = 120
MAX_GRAPH_BYTES = 128 << 20
MAX_KEYRING_BYTES = 4 << 20
MAX_OUTPUT_BYTES = 32 << 20


class CollectionBlock(RuntimeError):
    """Collector 输入或进程协议不可信；调用方必须保持 GATE_BLOCK。"""


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
        description="Collect a schema-valid bundle from signed readiness receipts."
    )
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--runner-keyring", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--metadata-dir", type=Path, default=METADATA_DIR)
    return parser.parse_args(argv)


def read_stable_regular_file(path: Path, limit: int) -> FileIdentity:
    try:
        before = path.lstat()
    except OSError as error:
        raise CollectionBlock(f"无法读取输入 {path}: {error}") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise CollectionBlock(f"输入必须是 regular file 且不能是 symlink: {path}")
    if before.st_size <= 0 or before.st_size > limit:
        raise CollectionBlock(f"输入大小不合法: {path}")
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size != before.st_size
            ):
                raise CollectionBlock(f"输入在打开期间发生漂移: {path}")
            payload = handle.read(limit + 1)
        after = path.lstat()
    except OSError as error:
        raise CollectionBlock(f"读取输入失败 {path}: {error}") from error
    if len(payload) != before.st_size or len(payload) > limit:
        raise CollectionBlock(f"输入在读取期间发生漂移: {path}")
    if (
        after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise CollectionBlock(f"输入在读取期间发生漂移: {path}")
    return FileIdentity(
        device=before.st_dev,
        inode=before.st_ino,
        size=before.st_size,
        modified_ns=before.st_mtime_ns,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CollectionBlock(f"collector 输出包含重复 JSON key: {key}")
        result[key] = value
    return result


def parse_single_json(payload: bytes) -> dict[str, object]:
    if len(payload) == 0 or len(payload) > MAX_OUTPUT_BYTES:
        raise CollectionBlock("collector 输出大小不合法")
    try:
        text = payload.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CollectionBlock(f"collector 输出包含非法 JSON constant: {value}")
            ),
        )
        document, end = decoder.raw_decode(text.lstrip())
        offset = len(text) - len(text.lstrip()) + end
    except (UnicodeDecodeError, json.JSONDecodeError, CollectionBlock) as error:
        if isinstance(error, CollectionBlock):
            raise
        raise CollectionBlock(f"collector 输出不是合法单一 JSON: {error}") from error
    if text[offset:].strip():
        raise CollectionBlock("collector 输出包含尾随内容或多个 JSON document")
    if not isinstance(document, dict):
        raise CollectionBlock("collector 输出根必须是 JSON object")
    return document


def validate_process_protocol(exit_code: int, document: dict[str, object]) -> None:
    if exit_code == 2:
        if set(document) != {"error"} or not isinstance(document["error"], str) or not document["error"]:
            raise CollectionBlock("collector exit 2 必须输出唯一非空 error")
        return
    if set(document) == {"complete", "missingSlots"}:
        if (
            exit_code != 1
            or document["complete"] is not False
            or not isinstance(document["missingSlots"], int)
            or isinstance(document["missingSlots"], bool)
            or document["missingSlots"] <= 0
        ):
            raise CollectionBlock("collector incomplete 协议与 exit 1 不一致")
        return
    if set(document) != {"generatedAt", "results"}:
        raise CollectionBlock("collector bundle 顶层协议不合法")
    results = document["results"]
    if not isinstance(document["generatedAt"], str) or not isinstance(results, list) or not results:
        raise CollectionBlock("collector bundle identity 不完整")
    if exit_code == 0:
        for result in results:
            if not isinstance(result, dict) or result.get("status") != "passed":
                raise CollectionBlock("collector exit 0 必须只包含 passed result")


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
        raise CollectionBlock(f"命令超时（{timeout}s）") from error
    except OSError as error:
        raise CollectionBlock(f"命令无法启动: {error}") from error


def collect(
    arguments: argparse.Namespace,
    *,
    build_root: Path = DEFAULT_BUILD_ROOT,
    runner: CommandRunner = subprocess.run,
) -> tuple[int, bytes]:
    graph_identity = read_stable_regular_file(arguments.graph, MAX_GRAPH_BYTES)
    keyring_identity = read_stable_regular_file(
        arguments.runner_keyring, MAX_KEYRING_BYTES
    )
    build_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=build_root) as directory:
        binary = Path(directory) / "collect-readiness-result-bundle"
        built = run_checked(
            ["go", "build", "-trimpath", "-o", str(binary), COLLECTOR_PACKAGE],
            cwd=SERVICE_ROOT,
            timeout=BUILD_TIMEOUT_SECONDS,
            runner=runner,
        )
        if built.returncode != 0:
            raise CollectionBlock("构建 canonical readiness collector 失败")
        read_stable_regular_file(binary, 128 << 20)
        completed = run_checked(
            [
                str(binary),
                "--graph",
                os.path.abspath(arguments.graph),
                "--metadata-dir",
                os.path.abspath(arguments.metadata_dir),
                "--runner-keyring",
                os.path.abspath(arguments.runner_keyring),
                "--receipt-root",
                os.path.abspath(arguments.receipt_root),
                "--evidence-root",
                os.path.abspath(arguments.evidence_root),
            ],
            cwd=SERVICE_ROOT,
            timeout=RUN_TIMEOUT_SECONDS,
            runner=runner,
        )
    if completed.returncode not in {0, 1, 2}:
        raise CollectionBlock(f"collector 返回非法 exit={completed.returncode}")
    if completed.stderr:
        raise CollectionBlock("collector 在 stderr 输出了非协议内容")
    document = parse_single_json(completed.stdout)
    validate_process_protocol(completed.returncode, document)
    if read_stable_regular_file(arguments.graph, MAX_GRAPH_BYTES) != graph_identity:
        raise CollectionBlock("ContractGraph 在 collection 期间发生漂移")
    if (
        read_stable_regular_file(arguments.runner_keyring, MAX_KEYRING_BYTES)
        != keyring_identity
    ):
        raise CollectionBlock("runner keyring 在 collection 期间发生漂移")
    return completed.returncode, completed.stdout


def write_failure(stdout: BinaryIO, error: Exception) -> None:
    payload = (json.dumps({"error": str(error)}, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    stdout.write(payload)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: BinaryIO | None = None,
    runner: CommandRunner = subprocess.run,
    build_root: Path = DEFAULT_BUILD_ROOT,
) -> int:
    output = stdout if stdout is not None else sys.stdout.buffer
    try:
        code, payload = collect(
            parse_arguments(argv), build_root=build_root, runner=runner
        )
    except CollectionBlock as error:
        write_failure(output, error)
        return 2
    output.write(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
