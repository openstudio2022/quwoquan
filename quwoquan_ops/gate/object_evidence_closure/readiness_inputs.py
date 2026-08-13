"""动态商业 readiness 的输入摘要、绑定复核与 canonical Go evaluator 构建。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from .arguments import commercial_input_values
from .constants import (
    READINESS_EVALUATOR_BUILD_TIMEOUT_SECONDS,
    READINESS_EVALUATOR_PACKAGE,
    SERVICE_ROOT,
)
from .models import display_path, sha256_file


def digest_readiness_input(path: Path) -> dict[str, str | int]:
    """绑定商业判定输入的当前字节；目录按相对路径 + 文件字节确定性摘要。

    receipt/evidence root 是 evaluator 的受限查找边界，不是单个文件。这里不解释
    其中内容，只保证报告能精确指向本次执行看到的整棵普通文件树。symlink 与特殊文件
    一律拒绝，避免摘要与 Go resolver 实际读取的对象不一致。
    """
    if path.is_symlink():
        raise ValueError(f"input must not be a symlink: {path}")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"input does not exist or cannot be resolved: {path}: {error}") from error
    if resolved.is_file():
        return {
            "path": display_path(resolved),
            "kind": "file",
            "sha256": sha256_file(resolved),
            "fileCount": 1,
        }
    if not resolved.is_dir():
        raise ValueError(f"input must be a regular file or directory: {path}")

    digest = hashlib.sha256()
    file_count = 0
    for candidate in sorted(resolved.rglob("*"), key=lambda value: value.as_posix()):
        if candidate.is_symlink():
            raise ValueError(f"input tree must not contain symlinks: {candidate}")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise ValueError(f"input tree contains a special file: {candidate}")
        relative = candidate.relative_to(resolved).as_posix().encode("utf-8")
        payload = candidate.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
        file_count += 1
    return {
        "path": display_path(resolved),
        "kind": "directory",
        "sha256": digest.hexdigest(),
        "fileCount": file_count,
    }


def readiness_input_bindings(arguments: argparse.Namespace) -> dict[str, dict]:
    bindings: dict[str, dict] = {}
    for name, path in commercial_input_values(arguments).items():
        if path is None:
            raise ValueError(f"missing commercial readiness input: {name}")
        bindings[name] = digest_readiness_input(Path(path))
    return bindings


def verify_readiness_input_bindings(
    arguments: argparse.Namespace,
    expected: dict[str, dict],
) -> None:
    actual = readiness_input_bindings(arguments)
    if actual != expected:
        raise ValueError(
            "commercial readiness inputs changed during evaluation: "
            f"expected={expected!r} actual={actual!r}"
        )


def decode_single_json_document(stdout: str) -> dict:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    decoder = json.JSONDecoder(object_pairs_hook=reject_duplicate_keys)
    try:
        payload, offset = decoder.raw_decode(stdout.lstrip())
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"readiness evaluator emitted invalid JSON: {error}") from error
    consumed_prefix = len(stdout) - len(stdout.lstrip())
    if stdout[consumed_prefix + offset :].strip():
        raise ValueError("readiness evaluator emitted multiple JSON documents")
    if not isinstance(payload, dict):
        raise ValueError("readiness evaluator JSON must be an object")
    return payload


def build_readiness_evaluator(work_root: Path) -> tuple[Path, str]:
    binary = work_root / "evaluate_readiness"
    environment = {**os.environ, "GOFLAGS": "-mod=readonly"}
    try:
        completed = subprocess.run(
            [
                "go",
                "build",
                "-trimpath",
                "-o",
                str(binary),
                READINESS_EVALUATOR_PACKAGE,
            ],
            cwd=SERVICE_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=READINESS_EVALUATOR_BUILD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"cannot build readiness evaluator: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[:2000]
        raise ValueError(f"cannot build readiness evaluator: {detail}")
    if not binary.is_file() or binary.is_symlink():
        raise ValueError("readiness evaluator build did not produce a regular binary")
    return binary, sha256_file(binary)
