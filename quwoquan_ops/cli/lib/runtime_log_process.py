from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.observability import (
    OBSERVABILITY_SCHEMA,
    append_canonical_log_record,
    append_log_line,
)


def _level(line: str) -> str:
    lowered = line.casefold()
    if "error" in lowered or "fatal" in lowered or "panic" in lowered:
        return "ERROR"
    if "warn" in lowered:
        return "WARN"
    return "INFO"


def run_logged_process(
    command: list[str],
    *,
    log_path: Path,
    event: str,
    diagnostic_log_path: Path | None = None,
) -> int:
    diagnostic_handle = None
    if diagnostic_log_path is not None:
        diagnostic_log_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostic_log_path.parent.chmod(0o700)
        diagnostic_handle = diagnostic_log_path.open("w", encoding="utf-8")
        os.chmod(diagnostic_log_path, 0o600)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    def forward(signum: int, _frame: object) -> None:
        if process.poll() is None:
            process.send_signal(signum)

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    append_log_line(
        log_path,
        {
            "severity": "INFO",
            "event": "process.start",
            "result": "ok",
            "message": event,
        },
    )
    assert process.stdout is not None
    try:
        for raw in process.stdout:
            if diagnostic_handle is not None:
                diagnostic_handle.write(raw)
                diagnostic_handle.flush()
            message = raw.rstrip("\r\n")
            if not message:
                continue
            canonical = _canonical_runtime_record(message)
            if canonical is not None:
                kind = str(canonical["logKind"])
                try:
                    append_canonical_log_record(
                        log_path.with_name(f"{kind}.log"),
                        canonical,
                    )
                except ValueError:
                    # 结构化子进程输出不可信时，不保留其原始内容；继续以通用事实
                    # 记录异常级别，避免将令牌或 PII 复制进可查询运行日志。
                    pass
                else:
                    continue
            level = _level(message)
            # 子进程原文可能含请求体、令牌或 PII，不能把它当成可上报的 runtime
            # message。只有已经由级别判定的异常事实进入统一日志；原始输出不落
            # observability 目录；若调用方显式指定受限 process/stdout 诊断文件，
            # 原文只保存在该文件中供本机排障。
            if level == "INFO":
                continue
            append_log_line(
                log_path,
                {
                    "severity": level,
                    "event": "process.output",
                    "result": "degraded" if level == "WARN" else "failed",
                    "message": "managed process emitted a non-info line",
                },
            )
        return_code = process.wait()
    finally:
        if diagnostic_handle is not None:
            diagnostic_handle.close()
    append_log_line(
        log_path,
        {
            "severity": "INFO" if return_code == 0 else "ERROR",
            "event": "process.exit",
            "result": "ok" if return_code == 0 else "failed",
            "message": f"{event} exit={return_code}",
        },
    )
    return return_code


def _canonical_runtime_record(message: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if parsed.get("schema") != OBSERVABILITY_SCHEMA:
        return None
    if not isinstance(parsed.get("logKind"), str):
        return None
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--diagnostic-log", type=Path)
    parser.add_argument("--event", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("command required after --")
    return run_logged_process(
        command,
        log_path=args.log_file,
        event=args.event,
        diagnostic_log_path=args.diagnostic_log,
    )


if __name__ == "__main__":
    raise SystemExit(main())
