"""垂类脚本目录治理检查。"""
from __future__ import annotations

from pathlib import Path

from _common.paths import DATA_ROOT

SCRIPTS_ROOT = DATA_ROOT / "scripts"
VERTICALS_ROOT = DATA_ROOT / "verticals"

# 历史兼容薄壳：允许存在，但必须只委托 verticals 下实现。
LEGACY_VERTICAL_WRAPPERS = {
    "bootstrap_school_entities.py": "verticals/campus/scripts/bootstrap_school_entities.py",
    "bootstrap_school_posts.py": "verticals/campus/scripts/bootstrap_school_posts.py",
}

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
    for rel_name, target in LEGACY_VERTICAL_WRAPPERS.items():
        wrapper = SCRIPTS_ROOT / rel_name
        if not wrapper.exists():
            continue
        target_path = DATA_ROOT / target
        if not target_path.exists():
            issues.append(f"{rel_name}: legacy wrapper target missing: {target}")
            continue
        text = wrapper.read_text(encoding="utf-8", errors="ignore")
        if target.replace("/", ".").replace(".py", "") not in text and "verticals" not in text:
            issues.append(f"{rel_name}: legacy wrapper must delegate to {target}")
    for path in sorted(SCRIPTS_ROOT.glob("*.py")):
        name = path.name
        if name in LEGACY_VERTICAL_WRAPPERS:
            continue
        lowered = name.lower()
        is_vertical_entry = lowered.startswith("bootstrap_") and any(token in lowered for token in VERTICAL_TOKENS)
        is_vertical_maintenance = any(token in lowered for token in VERTICAL_TOKENS) and (
            "_backfill" in lowered or "_seed" in lowered
        )
        if is_vertical_entry or is_vertical_maintenance:
            issues.append(f"{name}: vertical/task-specific script must live under quwoquan_data/verticals/** or tasks/**/scripts")
    return issues
