"""Gate: scale is a parameter, not a constant restated in code.

The milestone targets used to be written out in the campaign workload, the pool
report and the environment release selector. Raising a milestone then meant
editing code in several places, and a missed edit was a silent divergence that
only surfaced as a wrong target mid-run.

This gate scans the engine for a per-carrier milestone target table restated
outside the content distribution policy, and asserts that every live consumer
still equals the policy table, so a divergence cannot survive even if it is
written in a shape the scan misses.

It deliberately does not flag code that merely names the milestones. An ordering
helper or a CLI choice list naming ``M100``/``M1000`` holds no target quantity
and is not a second source of truth for the numbers.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"

# The one module allowed to hold the numbers, and the one allowed to name the
# governed milestones as data.
POLICY_MODULE = SCRIPTS_ROOT / "governance/coverage/distribution.py"
POLICY_YAML_DIR = DATA_ROOT / "control_plane"

_MILESTONE_NAMES = ("M100", "M1000", "M10000")
# Targets that only mean something as a milestone quantity. A bare 100 is
# ordinary; a dict mapping carriers to 100/1000/10000 is a milestone table.
_CARRIER_KEYS = frozenset({"homepage", "article", "image", "video"})
_MILESTONE_QUANTITIES = frozenset({100, 1_000, 10_000})

_SCAN_ROOTS = (
    SCRIPTS_ROOT / "content",
    SCRIPTS_ROOT / "governance",
    SCRIPTS_ROOT / "core",
)


def _iter_sources() -> list[Path]:
    paths: list[Path] = []
    for root in _SCAN_ROOTS:
        if not root.is_dir():
            continue
        paths.extend(
            path
            for path in sorted(root.rglob("*.py"))
            if path.resolve() != POLICY_MODULE.resolve()
        )
    return paths


def _is_milestone_table(node: ast.Dict) -> bool:
    """Whether this dict literal is a per-carrier milestone target table."""

    keys = {key.value for key in node.keys if isinstance(key, ast.Constant)}
    if _CARRIER_KEYS <= keys:
        values = {
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, int)
        }
        if values & _MILESTONE_QUANTITIES:
            return True
    if not keys & set(_MILESTONE_NAMES):
        return False
    return any(isinstance(value, ast.Dict) for value in node.values)


def scan_restated_milestones() -> list[str]:
    findings: list[str] = []
    for path in _iter_sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            findings.append(f"{path.relative_to(DATA_ROOT)}: unparseable ({exc})")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict) and _is_milestone_table(node):
                findings.append(
                    f"{path.relative_to(DATA_ROOT)}:{node.lineno}: milestone target "
                    "table restated in code; read "
                    "load_content_distribution_policy().milestone_targets()"
                )
    return findings


def verify_consumers_agree() -> list[str]:
    """Every live milestone consumer must equal the policy table."""

    if str(SCRIPTS_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_ROOT))
    from content.execution.campaign.scale import campaign_workload_targets
    from content.release.canonical import environment_release_selection, pool_inspection
    from governance.coverage.distribution import load_content_distribution_policy

    policy = load_content_distribution_policy()
    table = policy.milestone_targets()
    findings: list[str] = []
    if environment_release_selection.MILESTONE_TARGETS != table:
        findings.append(
            "environment_release_selection.MILESTONE_TARGETS diverged from the "
            "content distribution policy"
        )
    if pool_inspection.M100_TARGETS != table["M100"]:
        findings.append(
            "pool_inspection.M100_TARGETS diverged from the content distribution "
            "policy"
        )
    for milestone, targets in table.items():
        resolved = campaign_workload_targets(milestone)
        if resolved != targets:
            findings.append(
                f"campaign_workload_targets({milestone}) = {resolved} diverged "
                f"from the policy target {targets}"
            )
    if tuple(table) != policy.governed_scales():
        findings.append(
            "governed_scales() diverged from the declared milestone table"
        )
    return findings


def verify_policy_is_control_plane_data() -> list[str]:
    """The numbers must live in a control-plane document, not only in Python."""

    if not any(POLICY_YAML_DIR.rglob("content_distribution.policy.yaml")):
        return [
            "content_distribution.policy.yaml is absent from control_plane; the "
            "milestone numbers would have no parameter surface"
        ]
    return []


def main() -> int:
    findings = (
        verify_policy_is_control_plane_data()
        + scan_restated_milestones()
        + verify_consumers_agree()
    )
    if findings:
        print("[verify scale-parameterization] GATE_BLOCK", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(
        "[verify scale-parameterization] OK: milestone targets have a single "
        "control-plane source and every consumer agrees"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
