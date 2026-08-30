from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.output_paths import (
    env_run_dir,
    repo_run_dir,
    run_evidence_dir,
)

ROOT = Path(__file__).resolve().parents[3]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in shell usage
        try:
            return _load_simple_yaml(text)
        except ValueError as parse_error:
            raise RuntimeError(
                f"Cannot parse manifest without PyYAML installed: {path}"
            ) from parse_error
    return yaml.safe_load(text)


def _load_simple_yaml(text: str) -> Any:
    """Parse the small YAML subset used by local build manifests.

    Xcode script phases may run with a stripped Python environment that lacks
    PyYAML. This fallback intentionally supports only plain mappings, lists,
    quoted/unquoted scalars, booleans and nulls. Complex YAML should still use
    PyYAML in CI and developer shells.
    """

    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            raise ValueError(f"unsupported odd indentation: {raw_line!r}")
        lines.append((indent, raw_line.strip()))
    if not lines:
        return None

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(lines):
            return {}, index
        line_indent, content = lines[index]
        if line_indent != indent:
            raise ValueError(f"expected indent {indent}, got {line_indent}")
        if content.startswith("- "):
            return parse_list(index, indent)
        if content.startswith("[") or content.startswith("{"):
            return parse_flow_block(index, indent)
        return parse_mapping(index, indent)

    def parse_mapping(index: int, indent: int) -> tuple[dict[str, Any], int]:
        payload: dict[str, Any] = {}
        while index < len(lines):
            line_indent, content = lines[index]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise ValueError(f"unexpected nested mapping line: {content!r}")
            if content.startswith("- "):
                break
            key, value = split_key_value(content)
            if value is None:
                if index + 1 < len(lines) and lines[index + 1][0] > indent:
                    child, index = parse_block(index + 1, lines[index + 1][0])
                    payload[key] = child
                else:
                    payload[key] = {}
                    index += 1
            else:
                payload[key] = parse_scalar(value)
                index += 1
        return payload, index

    def parse_list(index: int, indent: int) -> tuple[list[Any], int]:
        payload: list[Any] = []
        while index < len(lines):
            line_indent, content = lines[index]
            if line_indent < indent:
                break
            if line_indent != indent or not content.startswith("- "):
                break
            item_text = content[2:].strip()
            if not item_text:
                if index + 1 < len(lines) and lines[index + 1][0] > indent:
                    child, index = parse_block(index + 1, lines[index + 1][0])
                    payload.append(child)
                else:
                    payload.append(None)
                    index += 1
                continue
            if ":" in item_text:
                item: dict[str, Any] = {}
                key, value = split_key_value(item_text)
                if value is None:
                    if index + 1 < len(lines) and lines[index + 1][0] > indent:
                        child, index = parse_block(index + 1, lines[index + 1][0])
                        item[key] = child
                    else:
                        item[key] = {}
                        index += 1
                else:
                    item[key] = parse_scalar(value)
                    index += 1
                if index < len(lines) and lines[index][0] > indent:
                    extra, index = parse_mapping(index, lines[index][0])
                    item.update(extra)
                payload.append(item)
                continue
            payload.append(parse_scalar(item_text))
            index += 1
        return payload, index

    def split_key_value(content: str) -> tuple[str, str | None]:
        if ":" not in content:
            raise ValueError(f"expected key/value line: {content!r}")
        key, value = content.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"empty key in line: {content!r}")
        value = value.strip()
        return key, value if value else None

    def parse_flow_value(value: str) -> Any:
        """Parse the JSON-like YAML flow subset used by metadata contracts."""

        cursor = 0

        def skip_whitespace() -> None:
            nonlocal cursor
            while cursor < len(value) and value[cursor].isspace():
                cursor += 1

        def parse_quoted() -> str:
            nonlocal cursor
            quote = value[cursor]
            start = cursor
            cursor += 1
            if quote == '"':
                escaped = False
                while cursor < len(value):
                    character = value[cursor]
                    cursor += 1
                    if character == '"' and not escaped:
                        return json.loads(value[start:cursor])
                    escaped = character == "\\" and not escaped
                    if character != "\\":
                        escaped = False
                raise ValueError("unterminated double-quoted flow scalar")

            characters: list[str] = []
            while cursor < len(value):
                character = value[cursor]
                cursor += 1
                if character != "'":
                    characters.append(character)
                    continue
                if cursor < len(value) and value[cursor] == "'":
                    characters.append("'")
                    cursor += 1
                    continue
                return "".join(characters)
            raise ValueError("unterminated single-quoted flow scalar")

        def parse_plain_scalar(raw_value: str) -> Any:
            normalized = raw_value.strip()
            if not normalized:
                raise ValueError("empty flow scalar")
            lowered = normalized.lower()
            if lowered in {"true", "false"}:
                return lowered == "true"
            if lowered in {"null", "none", "~"}:
                return None
            try:
                return int(normalized)
            except ValueError:
                return normalized

        def parse_value() -> Any:
            nonlocal cursor
            skip_whitespace()
            if cursor >= len(value):
                raise ValueError("missing flow value")
            if value[cursor] == "{":
                return parse_mapping()
            if value[cursor] == "[":
                return parse_list()
            if value[cursor] in {'"', "'"}:
                return parse_quoted()
            start = cursor
            while cursor < len(value) and value[cursor] not in ",]}":
                cursor += 1
            return parse_plain_scalar(value[start:cursor])

        def parse_mapping() -> dict[str, Any]:
            nonlocal cursor
            payload: dict[str, Any] = {}
            cursor += 1
            skip_whitespace()
            if cursor < len(value) and value[cursor] == "}":
                cursor += 1
                return payload
            while True:
                skip_whitespace()
                if cursor >= len(value):
                    raise ValueError("unterminated flow mapping")
                if value[cursor] in {'"', "'"}:
                    key = parse_quoted()
                else:
                    start = cursor
                    while cursor < len(value) and value[cursor] != ":":
                        if value[cursor] in "{},[]":
                            raise ValueError("invalid flow mapping key")
                        cursor += 1
                    key = value[start:cursor].strip()
                if not key or cursor >= len(value) or value[cursor] != ":":
                    raise ValueError("flow mapping entry is missing ':'")
                cursor += 1
                payload[key] = parse_value()
                skip_whitespace()
                if cursor >= len(value):
                    raise ValueError("unterminated flow mapping")
                delimiter = value[cursor]
                cursor += 1
                if delimiter == "}":
                    return payload
                if delimiter != ",":
                    raise ValueError("flow mapping entries must be comma-separated")
                skip_whitespace()
                if cursor < len(value) and value[cursor] == "}":
                    cursor += 1
                    return payload

        def parse_list() -> list[Any]:
            nonlocal cursor
            payload: list[Any] = []
            cursor += 1
            skip_whitespace()
            if cursor < len(value) and value[cursor] == "]":
                cursor += 1
                return payload
            while True:
                payload.append(parse_value())
                skip_whitespace()
                if cursor >= len(value):
                    raise ValueError("unterminated flow list")
                delimiter = value[cursor]
                cursor += 1
                if delimiter == "]":
                    return payload
                if delimiter != ",":
                    raise ValueError("flow list entries must be comma-separated")
                skip_whitespace()
                if cursor < len(value) and value[cursor] == "]":
                    cursor += 1
                    return payload

        result = parse_value()
        skip_whitespace()
        if cursor != len(value):
            raise ValueError("unexpected trailing flow content")
        return result

    def parse_flow_block(index: int, indent: int) -> tuple[Any, int]:
        fragments: list[str] = []
        expected_closer = "]" if lines[index][1].startswith("[") else "}"
        balance = 0
        quote = ""
        escaped = False
        while index < len(lines):
            line_indent, content = lines[index]
            if line_indent < indent:
                raise ValueError("flow collection continuation escaped its parent block")
            fragments.append(content)
            for character in content:
                if quote:
                    if quote == '"' and character == "\\" and not escaped:
                        escaped = True
                        continue
                    if character == quote and not escaped:
                        quote = ""
                    escaped = False
                    continue
                if character in {'"', "'"}:
                    quote = character
                    continue
                if character in "[{":
                    balance += 1
                elif character in "]}":
                    balance -= 1
                    if balance < 0:
                        raise ValueError("unexpected flow collection closer")
            index += 1
            if balance == 0:
                break
        if quote or balance != 0 or not fragments[-1].endswith(expected_closer):
            raise ValueError("unterminated flow collection block")
        return parse_flow_value(" ".join(fragments)), index

    def parse_scalar(value: str) -> Any:
        value = value.strip()
        if not value:
            return ""
        if value in {"''", '""'}:
            return ""
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if lowered in {"null", "none", "~"}:
            return None
        if value.startswith("[") or value.startswith("{"):
            return parse_flow_value(value)
        try:
            return int(value)
        except ValueError:
            return value

    result, next_index = parse_block(0, lines[0][0])
    if next_index != len(lines):
        raise ValueError("unparsed YAML content remains")
    return result


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = False,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    if env:
        merged_env.update(env)
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            argv,
            cwd=str(cwd or ROOT),
            env=merged_env,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=timeout_seconds is not None,
        )
        timed_out = False
        interrupted = False
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except KeyboardInterrupt:
            interrupted = True
            if timeout_seconds is not None:
                os.killpg(process.pid, signal.SIGINT)
            else:
                process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if timeout_seconds is not None:
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if timeout_seconds is not None:
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait()
            # The caller must observe the operator interruption even when the
            # managed child happens to translate SIGINT into exit zero.
            returncode = 130
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            returncode = 124
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read().decode("utf-8", errors="replace")
        stderr = stderr_file.read().decode("utf-8", errors="replace")
        if timed_out:
            stderr += (
                "\ncommand exceeded its deterministic deadline "
                f"after {timeout_seconds:.3f}s"
            )
        if interrupted:
            stderr += "\ncommand interrupted; managed child process was stopped"
    result = subprocess.CompletedProcess(
        argv,
        returncode,
        stdout=stdout,
        stderr=stderr,
    )
    if check and returncode != 0:
        raise subprocess.CalledProcessError(
            returncode,
            argv,
            output=stdout,
            stderr=stderr,
        )
    return result


def relpath(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def artifact_run_dir(
    env_name: str,
    command_name: str,
    *,
    target: str = "local",
    output_root: Path | None = None,
) -> Path:
    if output_root is not None:
        return run_evidence_dir(
            output_root / env_name,
            command_name,
            target,
        )
    if env_name == "repo":
        return repo_run_dir(command_name, target=target or "repo")
    return env_run_dir(env_name, command_name, target=target)
