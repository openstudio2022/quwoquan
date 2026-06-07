"""垂类脚本目录治理检查。"""
from __future__ import annotations

from _common.paths import DATA_ROOT

SCRIPTS_ROOT = DATA_ROOT / "scripts"
VERTICALS_ROOT = DATA_ROOT / "verticals"
VERTICAL_TOKENS = (
    "school",
    "campus",
    "travel",
    "photo",
    "photography",
)


def verify_vertical_script_governance() -> list[str]:
    issues: list[str] = []
    if not VERTICALS_ROOT.is_dir():
        issues.append("verticals/ 目录不存在")
        return issues
    for path in sorted(SCRIPTS_ROOT.glob("*.py")):
        lowered = path.name.lower()
        if any(token in lowered for token in VERTICAL_TOKENS):
            issues.append(f"{path.name}: vertical/task-specific script must live under quwoquan_data/verticals/** or tasks/**/scripts")
    return issues
