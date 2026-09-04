"""扫描范围、目录闭集与命名正则的唯一定义处。"""
from __future__ import annotations

import re
from pathlib import Path

SCOPES = ("app", "service", "ops", "data")
SCRIPT_SUFFIXES = {".py", ".sh"}
PYTHON_SCOPE_ROOTS = {
    "app": Path("quwoquan_app"),
    "service": Path("quwoquan_service"),
    "ops": Path("quwoquan_ops"),
    "data": Path("quwoquan_data"),
}
FORBIDDEN_CACHE_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        ".nox",
        ".ipynb_checkpoints",
    }
)
FORBIDDEN_TEMP_FILE_SUFFIXES = (
    ".bak",
    ".orig",
    ".rej",
    ".swp",
    ".swo",
    "~",
)
TRAVERSAL_IGNORED_DIR_NAMES = frozenset(
    {
        ".dart_tool",
        ".git",
        ".gradle",
        ".idea",
        ".qwq_output",
        ".venv",
        "Pods",
        "build",
        "dist",
        "node_modules",
    }
)
RIPGREP_EXCLUDED_GLOBS = tuple(
    f"!**/{name}/**" for name in sorted(TRAVERSAL_IGNORED_DIR_NAMES)
)
TEMP_SCRIPT_NAME_RE = re.compile(
    r"^(?:tmp|temp|scratch|copy_of)[_-].*\.(?:py|sh)$",
    re.IGNORECASE,
)
_MILESTONE_TOKENS = (
    "t" + "[1-4]",
    "m" + "6",
    "m" + "7",
    "b" + "10",
    "phase" + "[0-9]+",
    "part" + "[0-9]+",
)
MILESTONE_NAME_RE = re.compile(
    r"(^|[_-])(?:" + "|".join(_MILESTONE_TOKENS) + r")(?=[_.-]|$)",
    re.IGNORECASE,
)
REPO_SCRIPT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:quwoquan_(?:app|service|data|ops)/)[A-Za-z0-9_./-]+\.(?:py|sh))"
    r"(?![A-Za-z0-9_.-])"
)
RELATIVE_SCRIPTS_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(scripts/[A-Za-z0-9_./-]+\.(?:py|sh))"
    r"(?![A-Za-z0-9_.-])"
)
PACKAGE_SCRIPT_ROOTS = {
    "quwoquan_app": "quwoquan_app",
    "quwoquan_service": "quwoquan_service",
    "quwoquan_data": "quwoquan_data",
}

APP_CONCERN_ROOTS = {
    "_common",
    "device",
    "env",
    "fonts",
    "gamma",
    "ios",
    "runtime",
    "tools",
    "web",
}
APP_CLOUD_LAYOUT_SEGMENTS = {
    "config",
    "deploy",
    "environments",
}
APP_RUNTIME_CONCERNS = {
    "architecture",
    "auth",
    "cloud",
    "codegen",
    "error",
    "media",
    "observability",
    "page",
    "platform",
}
SERVICE_CONCERN_ROOTS = {
    "codegen",
    "contracts",
    "runtime",
    "tools",
    "verify",
}
SERVICE_RUNTIME_CONCERNS = {
    "experiments",
    "packaging",
    "reliabletask",
}
#: ``tools`` 与其它 managed root 一样参与角色派生：手工工具落在这里是 AGENTS.md
#: 允许的裁决之一，但它必须由 ``_tool_owner_issues`` 证明 owner 与用途，否则就是
#: 无人认领的 orphan。不收录只会让它落进笼统的 BOUNDARY_UNKNOWN，反而逃过治理。
OPS_MANAGED_ROOTS = (
    "ci",
    "cli",
    "environments/verify",
    "gate",
    "hooks",
    "migrations",
    "tools",
)
OPS_ALLOWED_TOP_LEVEL = {
    "ci",
    "cli",
    "environments",
    "gate",
    "hooks",
    "migrations",
    "observability",
    "tests",
    "tools",
}
ACCEPTANCE_ROOT = Path(
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops"
)

#: Python 文件行数硬顶。业界通行的模块规模上限（pylint ``max-module-lines``
#: 默认值）。``quwoquan_data/scripts/**`` 不在本预算内：它由
#: ``verify_script_architecture.py`` 的 600/500/400 更严硬顶单轨负责。
PYTHON_LINE_BUDGET_MAX_LINES = 1000
#: sequence-017 基线冻结仍携带超预算模块；在按责任拆分清零前保持 warn。
PYTHON_LINE_BUDGET_ENFORCEMENT = "warn"
