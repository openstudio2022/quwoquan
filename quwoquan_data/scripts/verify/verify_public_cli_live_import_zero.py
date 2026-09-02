"""Fresh-process public CLI import gate for retired orchestration families."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.execution.operational_fingerprint import operational_fingerprint
from core import paths
from core.schema import assert_valid

SCHEMA = "quwoquan_data.public_cli_live_import_zero_receipt"
COMMAND_ID = "data.public_cli.live_import_zero"
ENTRYPOINT = "quwoquan_data/scripts/cli.py"
COMMAND_ARGUMENTS = ["governance", "public-cli-live-import-zero"]
FORBIDDEN_PREFIXES = (
    "content.execution.agent",
    "content.execution.queue",
    "content.execution.controller",
    "content.execution.recovery",
    "content.execution.campaign",
)
PUBLIC_COMMAND_MODULES = (
    "content.execution.handler",
    "content.source.research.handler_cli",
    "content.filter_catalog.handler",
    "content.release.canonical.handler",
    "content.release.environment.cli",
    "content.templates.handler",
    "governance.handler",
    "verify.handler",
)
PUBLIC_COMMANDS = (
    "task",
    "source-pool",
    "filter-catalog",
    "release",
    "ship",
    "template",
    "governance",
    "verify",
)


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _probe_script() -> str:
    return r'''import argparse
import contextlib
import importlib
import io
import json
import sys

scripts_root = str(sys.argv[4])
repo_root = str(sys.argv[5])
sys.path.insert(0, scripts_root)
sys.path.insert(0, repo_root)
modules = tuple(json.loads(sys.argv[1]))
forbidden = tuple(json.loads(sys.argv[2]))
commands = tuple(json.loads(sys.argv[3]))
loaded = set()
discovered = {}
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    for module_name, command in zip(modules, commands, strict=True):
        module = importlib.import_module(module_name)
        register = getattr(module, "register_parser")
        parser = argparse.ArgumentParser(prog="qwq-data")
        subparsers = parser.add_subparsers(dest="command", required=True)
        register(subparsers)
        try:
            parser.parse_args([command, "--help"])
        except SystemExit as exc:
            if exc.code != 0:
                raise
        loaded.update(sys.modules)
        discovered[command] = sorted(
            name for name in loaded
            if name == module_name or name.startswith(module_name + ".")
        )
forbidden_loaded = sorted(
    name for name in loaded
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
print(json.dumps({
    "discoveredCommands": discovered,
    "loadedModules": sorted(loaded),
    "forbiddenLoadedModules": forbidden_loaded,
}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
'''



def _run_probe() -> tuple[dict[str, Any], bytes, bytes, int]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            _probe_script(),
            json.dumps(PUBLIC_COMMAND_MODULES),
            json.dumps(FORBIDDEN_PREFIXES),
            json.dumps(PUBLIC_COMMANDS),
            str(paths.REPO_ROOT / "quwoquan_data/scripts"),
            str(paths.REPO_ROOT),
        ],
        cwd=paths.REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
    )
    try:
        value = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("public CLI live-import probe produced invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("public CLI live-import probe must produce one JSON object")
    return value, completed.stdout, completed.stderr, completed.returncode


def build_receipt() -> dict[str, Any]:
    result, stdout, stderr, exit_code = _run_probe()
    discovered = result.get("discoveredCommands")
    loaded = result.get("loadedModules")
    forbidden = result.get("forbiddenLoadedModules")
    if not isinstance(discovered, dict) or tuple(discovered) != tuple(sorted(PUBLIC_COMMANDS)):
        raise ValueError("public CLI help discovery scope is invalid")
    if not isinstance(loaded, list) or loaded != sorted(set(map(str, loaded))):
        raise ValueError("public CLI live-import probe module set is invalid")
    if not isinstance(forbidden, list) or forbidden != sorted(set(map(str, forbidden))):
        raise ValueError("public CLI live-import probe forbidden set is invalid")
    verdict = "pass" if exit_code == 0 and not forbidden else "fail"
    receipt = {
        "schema": SCHEMA,
        "sourceFingerprint": operational_fingerprint(repo_root=paths.REPO_ROOT),
        "command": {
            "commandId": COMMAND_ID,
            "entrypoint": ENTRYPOINT,
            "arguments": COMMAND_ARGUMENTS,
        },
        "exitCode": exit_code,
        "verdict": verdict,
        "capturedOutput": {
            "stdoutDigest": _digest_bytes(stdout),
            "stderrDigest": _digest_bytes(stderr),
        },
        "probeDigest": _digest_bytes(_probe_script().encode("utf-8")),
        "checkedCommands": list(PUBLIC_COMMANDS),
        "discoveredCommands": discovered,
        "forbiddenPrefixes": list(FORBIDDEN_PREFIXES),
        "importedModules": sorted(PUBLIC_COMMAND_MODULES),
        "loadedModules": loaded,
        "loadedModulesDigest": _digest_bytes(
            _canonical_bytes({"loadedModules": loaded})
        ),
        "receiptId": _digest_bytes(
            _canonical_bytes(
                {
                    "sourceFingerprint": operational_fingerprint(repo_root=paths.REPO_ROOT),
                    "probeDigest": _digest_bytes(_probe_script().encode("utf-8")),
                    "checkedCommands": list(PUBLIC_COMMANDS),
                    "forbiddenPrefixes": list(FORBIDDEN_PREFIXES),
                    "loadedModulesDigest": _digest_bytes(
                        _canonical_bytes({"loadedModules": loaded})
                    ),
                }
            )
        ),
        "forbiddenLoadedModules": forbidden,
    }
    if verdict == "pass":
        assert_valid(receipt, "execution", "public_cli_live_import_zero_receipt")
    return receipt


def _write_create_once(path: Path, receipt: Mapping[str, Any]) -> Path:
    destination = path.expanduser()
    body = _canonical_bytes(dict(receipt))
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        if destination.is_symlink() or not destination.is_file() or destination.read_bytes() != body:
            raise ValueError(f"public CLI receipt create-once collision: {destination}") from None
        return destination
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("public CLI receipt destination must be a regular file")
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def run(*, output: Path | None = None) -> tuple[dict[str, Any], Path | None]:
    receipt = build_receipt()
    if receipt["verdict"] != "pass":
        return receipt, None
    destination = _write_create_once(output, receipt) if output is not None else None
    return receipt, destination


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="verify-public-cli-live-import-zero")
    parser.add_argument("--output")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        receipt, destination = run(output=Path(args.output) if args.output else None)
    except (OSError, TypeError, ValueError) as exc:
        print(f"[verify public-cli-live-import-zero] GATE_BLOCK {exc}", file=sys.stderr)
        return 1
    print(json.dumps({**receipt, **({"receiptRef": str(destination)} if destination else {})}, ensure_ascii=False, indent=2))
    return 0 if receipt["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
