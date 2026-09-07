"""Exact Git range and changed-hunk adapters."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from quwoquan_ops.ci.impact_planner_core import normalize_changed_paths, validate_exact_sha

_HUNK = re.compile(r"^@@ -(?P<old>\d+)(?:,(?P<old_count>\d+))? \+(?P<new>\d+)(?:,(?P<new_count>\d+))? @@")


@dataclass(frozen=True)
class Change:
    status: str
    path: str
    old_path: str | None
    added: int
    deleted: int
    changed_new_lines: frozenset[int]
    untracked: bool = False


def _run(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip() or "git command failed")
    return result.stdout


def resolve_sha(repo: Path, value: str) -> str:
    result = _run(repo, "rev-parse", "--verify", f"{value}^{{commit}}").decode().strip()
    return validate_exact_sha(result, label=value)


def blob(repo: Path, sha: str, path: str | None) -> bytes | None:
    if not path:
        return None
    result = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=repo, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else None


def in_progress_merge_parents(repo: Path) -> list[str]:
    """Exact MERGE_HEAD parents of an unfinished merge; empty when not merging."""
    path = Path(_run(repo, "rev-parse", "--git-path", "MERGE_HEAD").decode().strip())
    resolved = path if path.is_absolute() else repo / path
    if not resolved.is_file():
        return []
    return [
        validate_exact_sha(resolve_sha(repo, line.strip()), label="MERGE_HEAD")
        for line in resolved.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def blobs(repo: Path, sha: str, paths: list[str]) -> dict[str, bytes]:
    """Read many exact blobs through one cat-file process."""
    if not paths:
        return {}
    payload = b"".join(f"{sha}:{path}\n".encode("utf-8") for path in paths)
    result = subprocess.run(
        ["git", "cat-file", "--batch"], cwd=repo, input=payload,
        capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip() or "git cat-file failed")
    output = result.stdout
    cursor = 0
    resolved: dict[str, bytes] = {}
    for path in paths:
        line_end = output.find(b"\n", cursor)
        if line_end < 0:
            raise ValueError("git cat-file batch response truncated")
        header = output[cursor:line_end]
        cursor = line_end + 1
        if header.endswith(b" missing"):
            continue
        fields = header.split()
        if len(fields) != 3 or fields[1] != b"blob":
            raise ValueError(f"git cat-file unexpected response for {path}")
        size = int(fields[2])
        resolved[path] = output[cursor:cursor + size]
        cursor += size + 1
    return resolved


def changed_lines(repo: Path, base: str, head: str, path: str) -> frozenset[int]:
    output = _run(repo, "diff", "--unified=0", "--no-ext-diff", "--no-renames", base, head, "--", path).decode("utf-8", "replace")
    lines: set[int] = set()
    for raw in output.splitlines():
        match = _HUNK.match(raw)
        if not match:
            continue
        start = int(match.group("new"))
        count = int(match.group("new_count") or "1")
        lines.update(range(start, start + count))
    return frozenset(lines)


def _diff_output(
    repo: Path,
    base: str,
    head: str | None,
    *options: str,
    index_only: bool = False,
    explicit_paths: list[str] | None = None,
) -> bytes:
    args = ["-c", "core.quotePath=false", "diff", "--no-ext-diff", *options]
    if index_only:
        if head is not None:
            raise ValueError("index-only diff cannot specify a head")
        args.append("--cached")
    args.append(base)
    if head is not None:
        args.append(head)
    if explicit_paths:
        args.extend(["--", *explicit_paths])
    return _run(repo, *args)


def _parse_name_status(raw: bytes) -> list[tuple[str, str, str | None]]:
    records = raw.split(b"\0")
    index = 0
    identities: list[tuple[str, str, str | None]] = []
    while index < len(records) and records[index]:
        status = records[index].decode("utf-8", "replace")
        index += 1
        if status.startswith(("R", "C")):
            old_path = records[index].decode("utf-8", "replace")
            path = records[index + 1].decode("utf-8", "replace")
            index += 2
        else:
            old_path = None
            path = records[index].decode("utf-8", "replace")
            index += 1
        identities.append((status[0], path, old_path))
    return identities


def _parse_numstat(raw: bytes) -> dict[tuple[str, str | None], tuple[int, int]]:
    tokens = raw.split(b"\0")
    stats: dict[tuple[str, str | None], tuple[int, int]] = {}
    cursor = 0
    while cursor < len(tokens) and tokens[cursor]:
        prefix = tokens[cursor].decode("utf-8", "replace")
        cursor += 1
        added_raw, deleted_raw, embedded = prefix.split("\t", 2)
        if embedded:
            path, old_path = embedded, None
        else:
            old_path = tokens[cursor].decode("utf-8", "replace")
            path = tokens[cursor + 1].decode("utf-8", "replace")
            cursor += 2
        stats[(path, old_path)] = (
            0 if added_raw == "-" else int(added_raw),
            0 if deleted_raw == "-" else int(deleted_raw),
        )
    return stats


def _parse_changed_lines(output: bytes) -> dict[str, frozenset[int]]:
    current: str | None = None
    values: dict[str, set[int]] = {}
    for raw in output.decode("utf-8", "replace").splitlines():
        if raw.startswith("+++ "):
            value = raw[4:]
            current = None if value == "/dev/null" else value.removeprefix("b/")
            if current is not None:
                values.setdefault(current, set())
            continue
        match = _HUNK.match(raw)
        if current is None or not match:
            continue
        start = int(match.group("new"))
        count = int(match.group("new_count") or "1")
        values[current].update(range(start, start + count))
    return {path: frozenset(lines) for path, lines in values.items()}


def changed_lines_map(repo: Path, base: str, head: str) -> dict[str, frozenset[int]]:
    return _parse_changed_lines(
        _diff_output(repo, base, head, "--unified=0", "--no-renames")
    )


def changes(repo: Path, base: str, head: str, explicit_paths: list[str] | None = None) -> list[Change]:
    identities = _parse_name_status(
        _diff_output(repo, base, head, "--name-status", "-z", "--find-renames")
    )
    if explicit_paths:
        allowed = set(normalize_changed_paths(explicit_paths))
        identities = [item for item in identities if item[1] in allowed or item[2] in allowed]
    stats = _parse_numstat(
        _diff_output(repo, base, head, "--numstat", "-z", "--find-renames")
    )
    line_map = changed_lines_map(repo, base, head)
    result = []
    for status, path, old_path in identities:
        added, deleted = stats.get((path, old_path), stats.get((path, None), (0, 0)))
        result.append(Change(status, path, old_path, added, deleted, frozenset() if status == "D" else line_map.get(path, frozenset())))
    return sorted(result, key=lambda item: item.path.encode("utf-8"))


def working_tree_blob(repo: Path, path: str | None) -> bytes | None:
    if not path:
        return None
    candidate = repo / path
    try:
        return candidate.read_bytes() if candidate.is_file() else None
    except OSError as error:
        raise ValueError(f"candidate bytes unavailable for {path}") from error


def index_blob(repo: Path, path: str | None) -> bytes | None:
    if not path:
        return None
    result = subprocess.run(["git", "show", f":{path}"], cwd=repo, capture_output=True, check=False)
    if result.returncode == 0:
        return result.stdout
    missing = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        cwd=repo, capture_output=True, check=False,
    )
    if missing.returncode != 0:
        return None
    raise ValueError(
        result.stderr.decode("utf-8", "replace").strip()
        or f"index candidate bytes unavailable for {path}"
    )


def working_tree_changes(repo: Path, base: str, explicit_paths: list[str] | None = None, *, index_only: bool = False) -> list[Change]:
    base_sha = resolve_sha(repo, base)
    normalized_paths = normalize_changed_paths(explicit_paths or [])
    identities = _parse_name_status(
        _diff_output(
            repo, base_sha, None, "--name-status", "-z", "--find-renames",
            index_only=index_only,
        )
    )
    if normalized_paths:
        allowed = set(normalized_paths)
        identities = [
            item for item in identities if item[1] in allowed or item[2] in allowed
        ]
    diff_paths = [] if not normalized_paths else sorted({
        candidate
        for _, path, old_path in identities
        for candidate in (path, old_path)
        if candidate is not None
    }, key=lambda candidate: candidate.encode("utf-8"))
    stats = {} if normalized_paths and not identities else _parse_numstat(
        _diff_output(
            repo, base_sha, None, "--numstat", "-z", "--find-renames",
            index_only=index_only, explicit_paths=diff_paths,
        )
    )
    has_changed_candidate = any(status != "D" for status, _, _ in identities)
    line_map = {} if not has_changed_candidate else _parse_changed_lines(
        _diff_output(
            repo, base_sha, None, "--unified=0", "--find-renames",
            "--diff-filter=ACMRTUXB", index_only=index_only,
            explicit_paths=diff_paths,
        )
    )
    untracked_paths: set[str] = set()
    if not index_only:
        untracked_args = ["ls-files", "--others", "--exclude-standard", "-z"]
        if normalized_paths:
            untracked_args.extend(["--", *normalized_paths])
        known = {path for _, path, _ in identities}
        for raw_path in _run(repo, *untracked_args).split(b"\0"):
            if not raw_path:
                continue
            path = raw_path.decode("utf-8", "replace")
            if path in known or not (repo / path).is_file():
                continue
            identities.append(("A", path, None))
            untracked_paths.add(path)
            try:
                added = len(
                    (repo / path).read_bytes().decode("utf-8", "replace").splitlines()
                )
            except OSError as error:
                raise ValueError(f"candidate bytes unavailable for {path}") from error
            stats[(path, None)] = (added, 0)
            line_map[path] = frozenset(range(1, added + 1))
    result = []
    for status, path, old_path in identities:
        added, deleted = stats.get((path, old_path), stats.get((path, None), (0, 0)))
        result.append(Change(
            status, path, old_path, added, deleted,
            frozenset() if status == "D" else line_map.get(path, frozenset()),
            path in untracked_paths,
        ))
    return sorted(result, key=lambda item: item.path.encode("utf-8"))
