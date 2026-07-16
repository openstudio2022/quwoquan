#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "quwoquan_data" / "scripts" / "verify" / "data_role_gate_inventory.json"
DATA_AGENTS = ROOT / "quwoquan_data" / "AGENTS.md"
CONTEXT_CONTRACT = ROOT / "docs" / "agent_context_contract.md"
VERIFY_HANDLER = ROOT / "quwoquan_data" / "scripts" / "verify" / "handler.py"

REQUIRED_ROLE_IDS = {
    "senior_software_engineer",
    "senior_data_engineer",
    "data_quality_qa",
    "legal_compliance_expert",
    "consumer_perspective",
    "content_ops_expert",
    "unattended_automation",
}


def main() -> int:
    issues: list[str] = []

    try:
        payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[verify_data_role_gate_inventory] FAIL: cannot read inventory: {exc}", file=sys.stderr)
        return 1

    roles = payload.get("roles")
    if not isinstance(roles, list):
        issues.append("inventory must contain a roles list")
        roles = []

    seen_ids: set[str] = set()
    data_agents_text = DATA_AGENTS.read_text(encoding="utf-8")
    context_text = CONTEXT_CONTRACT.read_text(encoding="utf-8")
    verify_text = VERIFY_HANDLER.read_text(encoding="utf-8")

    for role in roles:
        if not isinstance(role, dict):
            issues.append("each role must be an object")
            continue
        role_id = role.get("id")
        label = role.get("label")
        keywords = role.get("required_keywords")
        if not isinstance(role_id, str) or not role_id:
            issues.append("role missing string id")
            continue
        if role_id in seen_ids:
            issues.append(f"duplicate role id: {role_id}")
        seen_ids.add(role_id)
        if not isinstance(label, str) or not label:
            issues.append(f"{role_id} missing label")
            continue
        if label not in data_agents_text:
            issues.append(f"quwoquan_data/AGENTS.md missing role label: {label}")
        if not isinstance(keywords, list) or not all(isinstance(item, str) and item for item in keywords):
            issues.append(f"{role_id} required_keywords must be a non-empty string list")
            continue
        for keyword in keywords:
            if keyword not in data_agents_text:
                issues.append(f"quwoquan_data/AGENTS.md missing keyword for {role_id}: {keyword}")

    missing = REQUIRED_ROLE_IDS - seen_ids
    extra = seen_ids - REQUIRED_ROLE_IDS
    if missing:
        issues.append(f"inventory missing required roles: {', '.join(sorted(missing))}")
    if extra:
        issues.append(f"inventory contains unrecognized roles: {', '.join(sorted(extra))}")

    if "数据工程七角色" not in data_agents_text:
        issues.append("quwoquan_data/AGENTS.md must keep the 数据工程七角色 section")
    if "数据工程七角色" not in context_text:
        issues.append("docs/agent_context_contract.md must reference 数据工程七角色")
    if '"data-role-gate"' not in verify_text or '"all"' not in verify_text:
        issues.append("verify handler must register data-role-gate and the canonical all gate")

    if issues:
        print("[verify_data_role_gate_inventory] FAIL", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    print("[verify_data_role_gate_inventory] OK")
    return 0
