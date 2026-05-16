#!/usr/bin/env python3
"""
禁止在结构化配置 / fixture YAML、JSON payload 中使用带 `.vN` 后缀的 `schemaVersion`。

- JSON：尽量 `json.loads` 后递归遍历；
- YAML：仅在「可 Strict 解析的配置/契约 fixture 路径」内做 `yaml.safe_load`；跳过 specs 叙述稿、feature-tree/changelog、`metadata/**/tests/**` 等非严格 YAML，
  避免误把整个仓库的中文 plan 文稿拉进门禁。

兼容：
  `COMPAT_*` 仅允许出现在 Python 源码，不在此处扫描。

用法：
  python3 scripts/verify_repo_schema_versions.py
  python3 scripts/verify_repo_schema_versions.py --prefix quwoquan_data/
  python3 scripts/verify_repo_schema_versions.py --warn-only
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
BAD_SCHEMA_SUFFIX = re.compile(r"\.v[0-9]+$")

_SUFFIXES = (".yaml", ".yml", ".json")

_JSON_ALWAYS_SKIP_PREFIXES = (
    "tmp/",
    ".cursor/",
    "app_log/",
    "specs/",
)
_JSON_SKIP_SUBSTR = "/node_modules/"


def _git_tracked_files(repo: Path, prefixes: list[str] | None) -> list[str]:
    cmd = ["git", "-c", "core.quotePath=false", "ls-files", "-z", "--"]
    cmd.extend(prefixes if prefixes else ["."])
    proc = subprocess.run(cmd, cwd=repo, capture_output=True, check=False, text=False)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"git ls-files failed: {stderr}".strip())

    paths: list[str] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8")
        if rel.endswith(_SUFFIXES):
            paths.append(rel)
    paths.sort()
    return paths


def _explicit_prefix_hit(prefixes: list[str] | None, rel: str) -> bool:
    return True if not prefixes else any(rel.startswith(p) for p in prefixes)


def _should_scan_json(prefixes: list[str] | None, rel: str) -> bool:
    if not rel.endswith(".json"):
        return False
    if not _explicit_prefix_hit(prefixes, rel):
        return False
    if prefixes is not None:
        return True
    if rel.startswith(_JSON_ALWAYS_SKIP_PREFIXES):
        return False
    if _JSON_SKIP_SUBSTR in rel:
        return False
    return True


def _should_scan_yaml(prefixes: list[str] | None, rel: str) -> bool:
    if not rel.endswith((".yaml", ".yml")):
        return False
    if not _explicit_prefix_hit(prefixes, rel):
        return False
    if prefixes is not None:
        # 前缀模式：仍跳过明确非 payload 的根目录叙述稿（若误入）
        if rel.startswith("specs/"):
            return False
        return True
    bad_roots = ("specs/", "tmp/", ".cursor/", "app_log/")
    if rel.startswith(bad_roots):
        return False
    if "/feature-tree/" in rel or "/changelog/" in rel:
        return False

    yaml_ok_prefix = (
        "quwoquan_app/configs/",
        "artifacts/",
        "deploy/",
        "quwoquan_data/",
        ".github/workflows/",
    )
    if rel.startswith(yaml_ok_prefix):
        return True
    meta = "/quwoquan_service/contracts/metadata/"
    if meta in rel and "/test_fixtures/" in rel:
        return True
    return False


def _walk_payload(obj: object, rel_path: str, hits: list[tuple[str, str]]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "schemaVersion" and isinstance(v, str) and BAD_SCHEMA_SUFFIX.search(v):
                hits.append((rel_path, v))
            _walk_payload(v, rel_path, hits)
    elif isinstance(obj, list):
        for item in obj:
            _walk_payload(item, rel_path, hits)


def _check_file(repo: Path, rel_path: str) -> tuple[list[tuple[str, str]], list[str]]:
    path = repo / rel_path
    errors: list[str] = []
    hits: list[tuple[str, str]] = []
    if not path.is_file():
        errors.append(f"缺失文件（未被检出？）: {rel_path}")
        return hits, errors
    raw = path.read_text(encoding="utf-8")

    try:
        if rel_path.endswith(".json"):
            data = json.loads(raw)
            _walk_payload(data, rel_path, hits)
        elif rel_path.endswith((".yaml", ".yml")):
            loaded = yaml.safe_load_all(raw)
            for doc in loaded:
                if doc is None:
                    continue
                _walk_payload(doc, rel_path, hits)
    except json.JSONDecodeError as e:
        errors.append(f"{rel_path}: JSON 解析失败: {e}")
    except yaml.YAMLError as e:
        errors.append(f"{rel_path}: YAML 解析失败: {e}")

    return hits, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prefix",
        action="append",
        default=None,
        help="只检查若干路径前缀（可重复），如 quwoquan_data/",
    )
    parser.add_argument("--warn-only", action="store_true", help="仅警告仍以 0 退出")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="仓库根目录")
    args = parser.parse_args()
    repo = args.repo.resolve()
    prefixes = args.prefix

    tracked = _git_tracked_files(repo, prefixes)
    all_errors: list[str] = []
    all_hits: list[tuple[str, str]] = []

    for rel in tracked:
        if rel.endswith(".json"):
            if not _should_scan_json(prefixes, rel):
                continue
        elif rel.endswith((".yaml", ".yml")):
            if not _should_scan_yaml(prefixes, rel):
                continue
        else:
            continue

        hits, errs = _check_file(repo, rel)
        all_hits.extend(hits)
        all_errors.extend(errs)

    for err in sorted(set(all_errors)):
        print(err, file=sys.stderr)

    for rel_path, sv in sorted(all_hits):
        print(f"非法 schemaVersion 后缀（{rel_path}）: {sv!r}", file=sys.stderr)

    if all_errors:
        print("[verify_repo_schema_versions] FAIL: 数据文件解析错误", file=sys.stderr)
        return 2

    if all_hits:
        msg = "[verify_repo_schema_versions] FAIL: 发现带 .vN 后缀的 schemaVersion"
        print(msg + ("（warn-only）" if args.warn_only else ""), file=sys.stderr)
        return 0 if args.warn_only else 1

    print("[verify_repo_schema_versions] OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
