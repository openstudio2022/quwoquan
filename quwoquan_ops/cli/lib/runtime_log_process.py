from __future__ import annotations

import argparse
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.observability import append_log_line


def _level(line: str) -> str:
    lowered = line.casefold()
    if "error" in lowered or "fatal" in lowered or "panic" in lowered:
        return "ERROR"
    if "warn" in lowered:
        return "WARN"
    return "INFO"


def run_logged_process(command: list[str], *, log_path: Path, event: str) -> int:
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
        {"level": "INFO", "event": "process.start", "result": "ok", "msg": event},
    )
    assert process.stdout is not None
    for raw in process.stdout:
        message = raw.rstrip("\r\n")
        if not message:
            continue
        append_log_line(
            log_path,
            {
                "level": _level(message),
                "event": "process.output",
                "result": "ok",
                "msg": message,
            },
        )
    return_code = process.wait()
    append_log_line(
        log_path,
        {
            "level": "INFO" if return_code == 0 else "ERROR",
            "event": "process.exit",
            "result": "ok" if return_code == 0 else "failed",
            "msg": f"{event} exit={return_code}",
        },
    )
    return return_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("command required after --")
    return run_logged_process(command, log_path=args.log_file, event=args.event)


if __name__ == "__main__":
    raise SystemExit(main())
