#!/usr/bin/env python3
"""生成全仓目录整洁审计报告。

该命令只读取 Git 与工作树，不删除、不修改源码。报告写入统一的
``.qwq_output/env/repo/runs``，用于在清理前冻结当前脏工作树和候选证据。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from quwoquan_ops.cli.lib.output_paths import repo_run_dir

CACHE_SEGMENTS = {
    ".dart_tool",
    ".gradle",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}

PROTECTED_LOCAL_CONFIG_NAMES = {
    "credentials.json",
    "google-services.json",
    "GoogleService-Info.plist",
}
PROTECTED_LOCAL_CONFIG_SUFFIXES = {
    ".jks",
    ".keystore",
    ".p12",
    ".pem",
}

GENERATED_MARKERS = {
    "generated",
    "generated_manifest.json",
    "contract_graph.json",
}
REFERENCE_EXCLUDED_PATHS = {"quwoquan_ops/cli/repo_hygiene_audit.py"}


def _run_git(args: list[str]) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def _split_z(data: bytes) -> list[str]:
    return [item.decode("utf-8", errors="surrogateescape") for item in data.split(b"\0") if item]


def _tracked_paths() -> set[str]:
    return set(_split_z(_run_git(["ls-files", "-z"])))


def _status_paths() -> dict[str, str]:
    """返回 path -> porcelain XY；ignored 文件由磁盘扫描统一补齐。"""
    records = _split_z(
        _run_git(
            [
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "-z",
            ]
        )
    )
    statuses: dict[str, str] = {}
    for record in records:
        # `git status --porcelain -z` 会为 rename/copy 将旧路径作为第二个、
        # 不带状态的 NUL 记录输出；不能把它解析成 `"qu"` 加截断路径。
        if len(record) < 4 or record[2] != " ":
            continue
        status = record[:2]
        path = record[3:]
        statuses[path] = status
    return statuses


def _disk_file_paths() -> set[str]:
    paths: set[str] = set()
    for current, directories, files in os.walk(ROOT, topdown=True):
        current_path = Path(current)
        visible_directories = [name for name in directories if name != ".git"]
        for name in visible_directories:
            path = current_path / name
            if path.is_symlink() or name in CACHE_SEGMENTS:
                paths.add(path.relative_to(ROOT).as_posix())
        directories[:] = [
            name
            for name in visible_directories
            if name not in CACHE_SEGMENTS
            and not (current_path / name).is_symlink()
        ]
        for name in files:
            paths.add((current_path / name).relative_to(ROOT).as_posix())
    return paths


def _ignored_paths(paths: set[str]) -> set[str]:
    if not paths:
        return set()
    payload = b"\0".join(
        path.encode("utf-8", errors="surrogateescape") for path in sorted(paths)
    ) + b"\0"
    result = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"],
        cwd=ROOT,
        check=False,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(
            result.stderr.decode("utf-8", errors="replace").strip()
            or "git check-ignore failed"
        )
    return set(_split_z(result.stdout))


def _hash_file(path: Path, max_bytes: int | None) -> str | None:
    try:
        if max_bytes == 0:
            return None
        if not path.is_file() or path.is_symlink():
            return None
        size = path.stat().st_size
        if max_bytes is not None and size > max_bytes:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, ValueError):
        return None


def _empty_directories() -> list[str]:
    empty: list[str] = []
    for current, directories, files in os.walk(ROOT, topdown=True):
        current_path = Path(current)
        directories[:] = [name for name in directories if name != ".git"]
        if current_path != ROOT and not directories and not files:
            empty.append(current_path.relative_to(ROOT).as_posix())
    return sorted(empty)


def _reference_matches(path: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "grep",
            "-l",
            "--fixed-strings",
            "--",
            path,
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return [
        item
        for item in result.stdout.splitlines()
        if item and item != path and item not in REFERENCE_EXCLUDED_PATHS
    ][:20]


def _category(path: str, status: str, tracked: bool) -> tuple[str, str]:
    if status == "!!":
        name = Path(path).name
        if (
            name == ".env"
            or name.startswith(".env.")
            or name in PROTECTED_LOCAL_CONFIG_NAMES
            or Path(name).suffix.lower() in PROTECTED_LOCAL_CONFIG_SUFFIXES
        ):
            return (
                "protected_local_configuration",
                "被 Git 忽略的本机环境或凭据配置，不得按可再生产缓存自动清理",
            )
        return "reproducible_local_output", "被 Git 忽略或位于可再生产缓存/构建目录"
    if status.strip():
        return "protected_wip", f"当前 Git 状态为 {status!r}，清理批次硬排除"

    parts = Path(path).parts
    if any(part in CACHE_SEGMENTS for part in parts):
        return "reproducible_local_output", "被 Git 忽略或位于可再生产缓存/构建目录"

    if path.startswith("quwoquan_app/vendor/"):
        return "vendored_dependency", "App pubspec dependency_overrides 或平台构建引用的受控 vendor"

    if (
        "generated" in parts
        or Path(path).name in GENERATED_MARKERS
        or Path(path).name.endswith(".g.dart")
        or Path(path).name.endswith(".g.go")
    ):
        return "managed_generated", "位于生成目录或符合受保护生成产物命名，需由 generator/manifest 管理"

    if (
        path.startswith("quwoquan_service/contracts/")
        or path.startswith("quwoquan_data/control_plane/")
        or path.startswith("quwoquan_data/schema/")
        or path.startswith("quwoquan_data/reference/")
    ):
        return "runtime_or_fixture_asset", "契约、控制面、schema 或 reference 真相源"

    if tracked:
        return "reachable_source", "Git 跟踪源码/测试/配置，需以入口和引用证据继续判断"
    return "review_required_candidate", "未跟踪且不属于可自动判定的缓存或受保护资产"


def _iter_inventory(
    tracked: set[str],
    statuses: dict[str, str],
    hash_limit: int | None,
) -> Iterable[dict[str, object]]:
    paths = sorted(tracked | set(statuses))
    for path in paths:
        status = statuses.get(path, "  ")
        category, reason = _category(path, status, path in tracked)

        disk_path = ROOT / path
        size = None
        is_file = False
        is_symlink = False
        try:
            is_symlink = disk_path.is_symlink()
            is_file = disk_path.is_file()
            if is_file:
                size = disk_path.stat().st_size
        except OSError:
            pass

        yield {
            "path": path,
            "git_status": status,
            "tracked": path in tracked,
            "ignored": status == "!!",
            "exists_on_disk": disk_path.exists() or disk_path.is_symlink(),
            "is_file": is_file,
            "is_symlink": is_symlink,
            "broken_symlink": is_symlink and not disk_path.exists(),
            "size_bytes": size,
            "sha256": _hash_file(disk_path, hash_limit),
            "category": category,
            "reason": reason,
        }


def _write_report(
    output_dir: Path,
    records: list[dict[str, object]],
    hash_limit: int | None,
    empty_directories: list[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = output_dir / "inventory.jsonl"
    with inventory_path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    by_category: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    bytes_by_category: Counter[str] = Counter()
    for record in records:
        category = str(record["category"])
        by_category[category] += 1
        by_status[str(record["git_status"])] += 1
        size = record["size_bytes"]
        if isinstance(size, int):
            bytes_by_category[category] += size

    candidates: list[dict[str, object]] = []
    for record in records:
        if record["category"] != "review_required_candidate":
            continue
        path = str(record["path"])
        candidates.append(
            {
                **record,
                "reference_matches": _reference_matches(path),
            }
        )

    largest_reproducible_outputs = sorted(
        (
            {
                "path": str(record["path"]),
                "size_bytes": int(record["size_bytes"]),
            }
            for record in records
            if record["category"] == "reproducible_local_output"
            and isinstance(record["size_bytes"], int)
        ),
        key=lambda item: item["size_bytes"],
        reverse=True,
    )[:25]
    zero_byte_tracked_files = sorted(
        str(record["path"])
        for record in records
        if record["tracked"]
        and record["is_file"]
        and record["size_bytes"] == 0
    )
    broken_symlinks = sorted(
        str(record["path"])
        for record in records
        if record["broken_symlink"]
    )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(ROOT),
        "command": "python3 quwoquan_ops/cli/repo_hygiene_audit.py",
        "hash_policy": {
            "sha256_generated_for_files_up_to_bytes": hash_limit,
            "large_or_unreadable_files_have_null_sha256": True,
        },
        "record_count": len(records),
        "category_counts": dict(sorted(by_category.items())),
        "category_bytes": dict(sorted(bytes_by_category.items())),
        "git_status_counts": dict(sorted(by_status.items())),
        "review_required_candidates": [
            item for item in candidates if item["category"] == "review_required_candidate"
        ],
        "largest_reproducible_local_outputs": largest_reproducible_outputs,
        "zero_byte_tracked_files": zero_byte_tracked_files,
        "broken_symlinks": broken_symlinks,
        "empty_directories": empty_directories,
        "wip_paths": [
            str(record["path"])
            for record in records
            if record["category"] == "protected_wip"
        ],
        "inventory_file": inventory_path.name,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只读生成全仓目录整洁审计 inventory 与 summary"
    )
    parser.add_argument(
        "--output-dir",
        help="报告目录；默认写入 .qwq_output/env/repo/runs/<timestamp>-repo-hygiene-audit-repo",
    )
    parser.add_argument(
        "--hash-mode",
        choices=("none", "small", "all"),
        default="small",
        help="哈希范围：none、small（默认 1MiB 内）或 all",
    )
    parser.add_argument(
        "--max-hash-bytes",
        type=int,
        default=1024 * 1024,
        help="hash-mode=small 时允许计算 SHA-256 的最大文件大小",
    )
    args = parser.parse_args()

    tracked = _tracked_paths()
    disk_paths = _disk_file_paths()
    statuses = _status_paths()
    for path in _ignored_paths(disk_paths - tracked):
        statuses[path] = "!!"
    for path in disk_paths - tracked - set(statuses):
        statuses[path] = "??"
    if args.hash_mode == "none":
        hash_limit = 0
    elif args.hash_mode == "all":
        hash_limit = None
    else:
        hash_limit = max(0, args.max_hash_bytes)

    records = list(_iter_inventory(tracked, statuses, hash_limit))
    empty_directories = _empty_directories()
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else repo_run_dir("repo-hygiene-audit", target="repo")
    )
    _write_report(output_dir, records, hash_limit, empty_directories)

    print(
        json.dumps(
            {
                "reportDir": str(output_dir.relative_to(ROOT))
                if output_dir.is_relative_to(ROOT)
                else str(output_dir),
                "recordCount": len(records),
                "reviewRequiredCount": sum(
                    record["category"] == "review_required_candidate"
                    for record in records
                ),
                "wipCount": sum(
                    record["category"] == "protected_wip" for record in records
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
