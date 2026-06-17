#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ACTIVE_SURFACES = [
    ROOT / ".github" / "workflows",
    ROOT / "agent_ops" / "deploy",
    ROOT / "quwoquan_service" / "scripts" / "deploy",
    ROOT / "quwoquan_app" / "scripts" / "gamma",
]

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


def iter_files() -> list[Path]:
    files: list[Path] = []
    for root in ACTIVE_SURFACES:
        if not root.exists():
            continue
        for pattern in SCRIPT_GLOBS:
            files.extend(root.rglob(pattern))
    return sorted({path for path in files if path.is_file()})


def line_is_retired_comment(raw_line: str) -> bool:
    lowered = raw_line.lower()
    return "退役" in raw_line or "retired" in lowered


def main() -> int:
    issues: list[str] = []
    workflow_root = ROOT / ".github" / "workflows"
    for path in iter_files():
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
    print("[verify_prod_access_guard] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
