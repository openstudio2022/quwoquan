"""垂类 coverage registry 加载与缺口评估。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from _common.paths import DATA_ROOT, PUBLISH_ROOT

VERTICALS_ROOT = DATA_ROOT / "verticals"
REGISTRY_REL = Path("coverage") / "registry.yaml"


def load_registry(vertical: str) -> dict[str, Any]:
    path = VERTICALS_ROOT / vertical / REGISTRY_REL
    if not path.is_file():
        raise FileNotFoundError(f"missing coverage registry: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("schemaVersion") != "quwoquan.vertical_coverage.v1":
        raise ValueError(f"{path}: invalid schemaVersion")
    if data.get("vertical") != vertical:
        raise ValueError(f"{path}: vertical mismatch")
    return data


def list_verticals() -> list[str]:
    if not VERTICALS_ROOT.is_dir():
        return []
    return sorted(
        p.name for p in VERTICALS_ROOT.iterdir()
        if p.is_dir() and (p / REGISTRY_REL).is_file()
    )


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    data = path.read_bytes()
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def _publish_entity_count(entity_type: str) -> int:
    if "/" not in entity_type:
        return 0
    root = PUBLISH_ROOT / "entities" / entity_type
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("_entity.json"))


def _publish_post_count_for_angles(angles: list[str]) -> int:
    total = 0
    for angle in angles:
        root = PUBLISH_ROOT / "posts" / "article" / angle
        if root.is_dir():
            total += sum(1 for _ in root.rglob("manifest.json"))
    return total


def evaluate_registry(vertical: str) -> dict[str, Any]:
    registry = load_registry(vertical)
    units = []
    totals = {"expectedCount": 0, "actualCount": 0, "gapCount": 0, "units": 0, "gapUnits": 0}
    for unit in registry.get("units") or []:
        expected = int(unit.get("expectedCount") or 0)
        source = str(unit.get("source") or "")
        actual = 0
        source_path = DATA_ROOT / source
        if source.endswith(".ndjson"):
            actual = _line_count(source_path)
        elif str(unit.get("entityType") or "").count("/") >= 1:
            actual = _publish_entity_count(str(unit.get("entityType")))
        angles = [str(a) for a in unit.get("requiredAngles") or []]
        post_count = _publish_post_count_for_angles(angles)
        gap = max(expected - actual, 0) if expected > 0 else (1 if str(unit.get("maturity")) == "gap" else 0)
        status = "passed" if gap == 0 and str(unit.get("maturity")) != "gap" else "gap"
        units.append({
            "id": unit.get("id"),
            "label": unit.get("label"),
            "maturity": unit.get("maturity"),
            "expectedCount": expected,
            "actualCount": actual,
            "gapCount": gap,
            "postCountForRequiredAngles": post_count,
            "status": status,
        })
        totals["expectedCount"] += expected
        totals["actualCount"] += actual
        totals["gapCount"] += gap
        totals["units"] += 1
        if status != "passed":
            totals["gapUnits"] += 1
    return {
        "schemaVersion": "quwoquan.vertical_coverage_report.v1",
        "vertical": vertical,
        "status": "passed" if totals["gapUnits"] == 0 else "gap",
        "totals": totals,
        "units": units,
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        f"[coverage] vertical={report['vertical']} status={report['status']}",
        f"  units={report['totals']['units']} gapUnits={report['totals']['gapUnits']} actual={report['totals']['actualCount']} expected={report['totals']['expectedCount']}",
    ]
    for unit in report["units"]:
        marker = "OK" if unit["status"] == "passed" else "GAP"
        lines.append(
            f"  {marker} {unit['id']}: actual={unit['actualCount']} expected={unit['expectedCount']} maturity={unit['maturity']} posts={unit['postCountForRequiredAngles']}"
        )
    return "\n".join(lines)
