"""仓外输出根隔离门（数据输出规范）。

裁定（目录规范计划验收标准）：
1. 【repo allowlist 门】仓内唯一允许长期保留并参与打包的生成输出是 `publish/**`；
   `quwoquan_data/runtime/**`、`quwoquan_data/release/**`、`.qwq_output/**`、
   `.qwq_sandbox/**` 一律不得进入版本控制。
2. 【仓内阶段树门】canonical 阶段树 `runtime/{e2e,operations}/...` 只能落在
   QWQ_OUTPUT_ROOT；仓内 `quwoquan_data/runtime/` 不再保留任何 legacy 运行残留。
3. 【批次轴门】canonical 批次必须携带 batch_manifest.json，且 phase/contentType/
   supplyMode 与所在目录层级一致；manifest.taskId 必须能回指仓内 committed task.yaml
   （committed 模板存在性/路径合法性）。
4. 【摘要索引门】.qwq_output/runs/content_runs 批次摘要目录必须 index-first：
   有报告即有 index.json，回指字段齐全（复用 _common.artifacts_index）。
5. 【artifacts 根隔离门】repo `.qwq_output/runs/` 只服务非 data 运行证据；data-owned
   临时报表、旧目录和 legacy marker/index/manifest 一律 FAIL。

CLI 入口（cli-first）：`qwq-data verify output-root-isolation`。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.artifacts_index import (  # noqa: E402
    ARTIFACTS_INDEX_FILENAME,
    artifacts_index_issues,
)
from _common.io import read_json  # noqa: E402
from _common.paths import (  # noqa: E402
    BATCH_CONTENT_TYPES,
    BATCH_PHASES,
    BATCH_SUPPLY_MODES,
    OUTPUT_ARTIFACTS_ROOT,
    REPO_ROOT,
    RUNTIME_ROOT,
    committed_task_spec,
)

# 仓内禁止进入版本控制的生成输出面（publish 是唯一例外，不在此列）。
TRACKED_FORBIDDEN_PATHS = (
    "quwoquan_data/runtime",
    "quwoquan_data/release",
    ".qwq_output",
    ".qwq_sandbox",
)

DATA_ARTIFACT_ROOT_DIRS = frozenset(
    {
        "legacy",
        "quwoquan_data_runs",
        "quwoquan_data_cleanup",
        "sichuan-e2e-assessment",
        "tmp",
    }
)
DATA_ARTIFACT_ROOT_PREFIXES = (
    "creator_",
    "scale_",
    "scale10_",
    "site_supply_",
    "s10verify_",
    "cs100verify_",
    "cursor_probe_",
    "p0_probe_",
    "quwoquan_data_",
)
LEGACY_MARKER_FILENAMES = frozenset(
    {
        "LEGACY_READONLY.md",
        "_".join(("legacy", "index")) + ".json",
        "_".join(("migration", "manifest")) + ".json",
    }
)


def tracked_output_issues(repo_root: Path = REPO_ROOT) -> list[str]:
    """repo allowlist 门：生成输出面不得被 git 追踪（唯一入库生成输出是 publish/**）。"""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--", *TRACKED_FORBIDDEN_PATHS],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"git ls-files failed: {exc}"]
    tracked = [line for line in proc.stdout.splitlines() if line.strip()]
    return [
        f"{path}: 生成输出被版本控制追踪（仓内唯一入库生成输出是 publish/**）"
        for path in tracked[:50]
    ]


def repo_phase_tree_issues(repo_root: Path = REPO_ROOT) -> list[str]:
    """仓内阶段树门：quwoquan_data/runtime 不得保留运行残留。"""
    issues: list[str] = []
    runtime = repo_root / "quwoquan_data" / "runtime"
    if not runtime.is_dir():
        return issues
    for entry in sorted(runtime.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name in BATCH_PHASES:
            issues.append(
                f"quwoquan_data/runtime/{entry.name}: canonical 阶段树只能落在 QWQ_OUTPUT_ROOT"
            )
            continue
        if entry.name == "batches":
            issues.append("quwoquan_data/runtime/batches: legacy 平铺批次根已退役，需删除重跑")
            continue
        issues.append(f"quwoquan_data/runtime/{entry.name}: 仓内 runtime 已退役，需删除重跑")
    return issues


def _is_data_artifact_root_entry(name: str) -> bool:
    return name in DATA_ARTIFACT_ROOT_DIRS or name in LEGACY_MARKER_FILENAMES or any(
        name.startswith(prefix) for prefix in DATA_ARTIFACT_ROOT_PREFIXES
    )


def data_root_artifact_issues(repo_root: Path = REPO_ROOT) -> list[str]:
    """artifacts 根隔离门：阻断 data-owned 根文件、旧目录与 legacy marker。"""
    issues: list[str] = []
    artifacts_root = repo_root / "artifacts"
    if not artifacts_root.is_dir():
        return issues
    for entry in sorted(artifacts_root.iterdir()):
        if not _is_data_artifact_root_entry(entry.name):
            continue
        rel = entry.relative_to(repo_root)
        issues.append(
            f"{rel}: data 运行残留不得落 repo .qwq_output/runs/ 根；请删除并改写到 .qwq_output/runs/**"
        )
    return issues


def legacy_marker_issues(
    repo_artifacts_root: Path | None = None,
    output_artifacts_root: Path = OUTPUT_ARTIFACTS_ROOT,
) -> list[str]:
    """legacy marker/index/manifest 不允许存在于 repo artifacts 或输出 artifacts。"""
    issues: list[str] = []
    roots = [
        repo_artifacts_root if repo_artifacts_root is not None else REPO_ROOT / "artifacts",
        output_artifacts_root,
    ]
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for marker in LEGACY_MARKER_FILENAMES:
            for path in sorted(root.rglob(marker)):
                try:
                    rel = path.relative_to(REPO_ROOT)
                except ValueError:
                    rel = path
                if path in seen:
                    continue
                seen.add(path)
                issues.append(f"{rel}: legacy marker/index/manifest 已退役，需删除")
    return issues


def canonical_batch_axis_issues(runtime_root: Path = RUNTIME_ROOT) -> list[str]:
    """批次轴门：canonical 批次 manifest 轴与目录层级一致，且回指 committed task。"""
    issues: list[str] = []
    for phase in BATCH_PHASES:
        for content_type in BATCH_CONTENT_TYPES:
            for supply_mode in BATCH_SUPPLY_MODES:
                root = runtime_root / phase / content_type / supply_mode
                if not root.is_dir():
                    continue
                for batch_dir in sorted(p for p in root.iterdir() if p.is_dir()):
                    rel = batch_dir.relative_to(runtime_root)
                    manifest_path = batch_dir / "batch_manifest.json"
                    if not manifest_path.is_file():
                        issues.append(f"{rel}: canonical 批次缺 batch_manifest.json")
                        continue
                    try:
                        manifest = read_json(manifest_path)
                    except Exception as exc:  # noqa: BLE001
                        issues.append(f"{rel}: batch_manifest.json unreadable ({exc})")
                        continue
                    for field, expected in (
                        ("phase", phase),
                        ("contentType", content_type),
                        ("supplyMode", supply_mode),
                    ):
                        actual = str(manifest.get(field) or "")
                        if actual != expected:
                            issues.append(
                                f"{rel}: manifest.{field}={actual!r} 与目录层级 {expected!r} 漂移"
                            )
                    task_id = str(manifest.get("taskId") or "")
                    if not task_id:
                        issues.append(f"{rel}: manifest.taskId 为空（批次必须回指 committed task）")
                        continue
                    spec_path = committed_task_spec(task_id)
                    if not spec_path.is_file():
                        issues.append(
                            f"{rel}: committed task 模板缺失（taskId={task_id} → {spec_path}）"
                        )
    return issues


def artifacts_index_gate_issues(artifacts_root: Path = OUTPUT_ARTIFACTS_ROOT) -> list[str]:
    """摘要索引门：content_runs 批次摘要目录有报告即必须有 index.json 且回指齐全。"""
    issues: list[str] = []
    content_runs = artifacts_root / "content_runs"
    if not content_runs.is_dir():
        return issues
    for phase_dir in sorted(p for p in content_runs.iterdir() if p.is_dir()):
        for type_dir in sorted(p for p in phase_dir.iterdir() if p.is_dir()):
            for batch_dir in sorted(p for p in type_dir.iterdir() if p.is_dir()):
                has_reports = any(
                    p.suffix == ".json" and p.name != ARTIFACTS_INDEX_FILENAME
                    for p in batch_dir.iterdir()
                    if p.is_file()
                )
                if not has_reports:
                    continue
                issues.extend(
                    str(issue)
                    for issue in artifacts_index_issues(batch_dir / ARTIFACTS_INDEX_FILENAME)
                )
    return issues


def scan_all() -> list[str]:
    issues: list[str] = []
    issues.extend(tracked_output_issues())
    issues.extend(repo_phase_tree_issues())
    issues.extend(data_root_artifact_issues())
    issues.extend(legacy_marker_issues())
    issues.extend(canonical_batch_axis_issues())
    issues.extend(artifacts_index_gate_issues())
    return issues


def main() -> int:
    issues = scan_all()
    if issues:
        print("FAIL verify_output_root_isolation:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("PASS verify_output_root_isolation")
    return 0
