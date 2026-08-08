#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 固定执行面：路径由本仓库布局直接决定，必须存在。
STATIC_SURFACES = (
    ".github/workflows",
    "quwoquan_app/scripts/gamma",
    "quwoquan_app/deploy",
)
#: 部署执行面按对象树发现：第一方部署基线归服务 `deploy/`，四环境入口归
#: `environments/<env>/deploy`，控制面与外部 workload 各自持有 `deploy/`。
#: 每条声明都必须至少发现一个根，否则说明目录轴又变了而门禁在空扫。
DISCOVERED_SURFACE_GLOBS = (
    "quwoquan_service/services/*/deploy",
    "quwoquan_service/services/*/environments/*/deploy",
    "quwoquan_service/control-plane/*/deploy",
    "quwoquan_ops/external/*/deploy",
)

SCRIPT_GLOBS = ("*.py", "*.sh", "*.yml", "*.yaml")

ACTIVE_AUTH_PATTERNS = {
    r"\bsshpass\b": "禁止在执行面重新引入口令 SSH（sshpass）",
    r"PreferredAuthentications=password": "禁止在执行面强制 password SSH 认证",
    r"PubkeyAuthentication=no": "禁止在执行面关闭 pubkey 认证以回退口令模式",
    r"root@118\.31\.239\.122": "禁止在执行面硬编码 root prod SSH 入口",
}

WORKFLOW_PROHIBITED_ENV_PATTERNS = {
    r"\bGAMMA_ECS_[A-Z0-9_]+\b": "workflow 不得重新注入已退役的 GAMMA_ECS_* 变量",
    r"\bPROD_KUBECONFIG\b": "workflow 不得重新注入已退役的 PROD_KUBECONFIG",
}


def resolve_surfaces() -> tuple[list[Path], list[str]]:
    """解析执行面。目标缺失时返回阻断项，绝不静默跳过成空扫。"""
    surfaces: list[Path] = []
    problems: list[str] = []
    for relative in STATIC_SURFACES:
        root = ROOT / relative
        if not root.is_dir():
            problems.append(
                f"声明的执行面不存在: {relative}；目录轴变更后必须把门禁指向新的 canonical 路径"
            )
            continue
        surfaces.append(root)
    for pattern in DISCOVERED_SURFACE_GLOBS:
        discovered = sorted(path for path in ROOT.glob(pattern) if path.is_dir())
        if not discovered:
            problems.append(
                f"执行面发现模式没有命中任何目录: {pattern}；"
                "部署目录轴变更后必须同步该模式，不得让门禁空扫通过"
            )
            continue
        surfaces.extend(discovered)
    return surfaces, problems


def iter_files(surfaces: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in surfaces:
        for pattern in SCRIPT_GLOBS:
            files.extend(root.rglob(pattern))
    return sorted({path for path in files if path.is_file()})


def line_is_retired_comment(raw_line: str) -> bool:
    lowered = raw_line.lower()
    return "退役" in raw_line or "retired" in lowered


def main() -> int:
    surfaces, issues = resolve_surfaces()
    workflow_root = ROOT / ".github" / "workflows"
    scanned = iter_files(surfaces)
    if not scanned:
        issues.append("执行面扫描结果为空；门禁不得在没有被测文件的情况下通过")
    for path in scanned:
        rel = path.relative_to(ROOT)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = text.splitlines()
        for line_no, raw_line in enumerate(lines, start=1):
            for pattern, message in ACTIVE_AUTH_PATTERNS.items():
                if re.search(pattern, raw_line) and not line_is_retired_comment(raw_line):
                    issues.append(f"{rel}:{line_no}: {message}")
            if path.is_relative_to(workflow_root):
                for pattern, message in WORKFLOW_PROHIBITED_ENV_PATTERNS.items():
                    if re.search(pattern, raw_line) and not line_is_retired_comment(raw_line):
                        issues.append(f"{rel}:{line_no}: {message}")
    if issues:
        print("[verify_prod_access_guard] FAIL", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print(
        f"[verify_prod_access_guard] OK: surfaces={len(surfaces)} files={len(scanned)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
