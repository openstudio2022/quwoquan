#!/usr/bin/env python3
"""受版本控制文件里的 output 路径卫生，两个维度。

维度一（源文件 × 退役路径）：拒绝活跃运行入口重新写入退役 output/state 路径。

维度二（生成物 × 易失路径）：受版本控制的生成物不得嵌入 `.qwq_output` 路径。
`.qwq_output/` 按 AGENTS.md 只存可删除、可重建的运行输出，删掉后仍必须能凭受版本
控制的真相源重建；生成物一旦记下该目录下的路径，就记下了一个无法重建的事实。
真实发生过：契约视图有一条 reinstatement 分支会把 `.qwq_output` 下 materialize 出来
的已退役服务纳入视图，于是在该目录存在时跑 codegen，会把它的路径写进
`quwoquan_service/generated/contract_graph.json`。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = (
    ROOT / "quwoquan_app" / "scripts",
    ROOT / "quwoquan_app" / "lib",
    ROOT / "quwoquan_data" / "scripts",
    ROOT / "quwoquan_ops",
    ROOT / "quwoquan_service" / "scripts",
    ROOT / "quwoquan_service" / "services",
    ROOT / ".github" / "workflows",
    ROOT / ".cursor" / "commands",
    ROOT / ".agents" / "skills" / "environment-ops",
)
ROOT_CONFIG_FILES = (
    ROOT / "Makefile",
    ROOT / "pytest.ini",
)
TEXT_SUFFIXES = frozenset({".py", ".sh", ".yaml", ".yml", ".md", ".dart", ".go", ".json", ".toml"})
NEGATIVE_CONTRACT_FILES = {
    ROOT / "quwoquan_data" / "scripts" / "verify" / "verify_output_root_isolation.py",
    ROOT / "quwoquan_ops" / "gate" / "verify_dev_up_cli_surface.py",
    ROOT / "quwoquan_ops" / "gate" / "verify_root_layout.py",
}
RETIRED_PATTERNS = (
    re.compile(r"data/local/runtime"),
    re.compile(r"data/release(?:/|$|(?=[._-]))"),
    re.compile(r"data-releases"),
    re.compile(r"(?:QWQ_OUTPUT_ROOT|\.qwq_output)/(?:local|runs|release|observability|repo)(?:/|$|(?=[._-]))"),
    re.compile(r"env/(?:alpha|beta|gamma|prod|repo)/(?:packages|runtime|cache|tmp)(?:/|$|(?=[._-]))"),
    re.compile(r"env/(?:alpha|beta|gamma|prod|repo)/release(?:/|$|(?=[._-]))"),
    re.compile(
        r"env/(?:alpha|beta|gamma|prod|repo)/local/[^\s\"']+/process/"
        r"(?:config|configuration|caddy|pki|tls|certificates?)(?:/|$|(?=[._-]))"
    ),
    re.compile(
        r"env/(?:alpha|beta|gamma|prod|repo)/local/[^\s\"']+/"
        r"(?:config|configuration|caddy|pki|tls|certificates?)(?:/|$|(?=[._-]))"
    ),
    re.compile(r"(?:QWQ_OUTPUT_ROOT|\.qwq_output)/data/(?:runtime|runs|objects|cache|tmp|observability)(?:/|$|(?=[._-]))"),
    re.compile(r"env/prod/control(?:/|$|(?=[._-]))"),
    re.compile(r"env/repo/local/test-cache(?:/|$|(?=[._-]))"),
    re.compile(
        r'''(?:QWQ_OUTPUT_ROOT|\.qwq_output)/[^\n]*(?:control_plane|prompts|templates|schema|specs|policies|reference|requirements\.txt)(?:/|$|["'\s])'''
    ),
    re.compile(r"QWQ_STATE_ROOT|\.qwq_state"),
)

GENERATED_DIR_NAME = "generated"
EPHEMERAL_OUTPUT_PATTERN = re.compile(r"(?:\.qwq_output|QWQ_OUTPUT_ROOT)/")
MAX_REPORTED_LINES_PER_FILE = 5


def _sources() -> list[Path]:
    files: list[Path] = [path for path in ROOT_CONFIG_FILES if path.is_file()]
    for source_root in SOURCE_ROOTS:
        if not source_root.exists():
            continue
        for path in source_root.rglob("*"):
            relative_parts = path.relative_to(source_root).parts
            if (
                path.is_file()
                and path.suffix in TEXT_SUFFIXES
                and not {"node_modules", "vendor", ".qwq_output"}.intersection(relative_parts)
                and path != Path(__file__)
                and path not in NEGATIVE_CONTRACT_FILES
                and "/tests/" not in path.as_posix()
                and not path.name.startswith("test_")
            ):
                files.append(path)
    return sorted(set(files))


def source_path_issues() -> list[str]:
    issues: list[str] = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in RETIRED_PATTERNS):
                try:
                    rendered = path.relative_to(ROOT).as_posix()
                except ValueError:
                    rendered = path.as_posix()
                issues.append(f"{rendered}:{line_number}: retired output/state path")
    return issues


def _tracked_generated_files(root: Path) -> list[Path]:
    """受版本控制的生成物：git 跟踪，且路径含 `generated` 目录段。

    判据是「git 跟踪」而不是「磁盘上存在」，因为本维度要守的正是「被提交下来的
    事实必须可重建」；未跟踪的本地产物不在此列。
    """
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    files: list[Path] = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8", errors="replace"))
        if GENERATED_DIR_NAME not in relative.parts:
            continue
        path = root / relative
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            files.append(path)
    return sorted(set(files))


def generated_artifact_issues(root: Path = ROOT) -> list[str]:
    issues: list[str] = []
    for path in _tracked_generated_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [
            line_number
            for line_number, line in enumerate(text.splitlines(), start=1)
            if EPHEMERAL_OUTPUT_PATTERN.search(line)
        ]
        if not hits:
            continue
        rendered = path.relative_to(root).as_posix()
        for line_number in hits[:MAX_REPORTED_LINES_PER_FILE]:
            issues.append(f"{rendered}:{line_number}: generated artifact embeds ephemeral .qwq_output path")
        if len(hits) > MAX_REPORTED_LINES_PER_FILE:
            issues.append(f"{rendered}: ... {len(hits) - MAX_REPORTED_LINES_PER_FILE} more line(s) in the same file")
    return issues


def main() -> int:
    issues = source_path_issues()
    issues.extend(generated_artifact_issues())
    if issues:
        print("[verify_output_path_source_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_output_path_source_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
