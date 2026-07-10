#!/usr/bin/env python3
"""T4 four-environment prefab user readiness report."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.creator_pool.io import artifacts_readiness_path

ARTIFACT = artifacts_readiness_path("creator_prefab_user_four_env_readiness.json")
CUTOVER = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "prefab_cutover.yaml"
T2_REPORT = artifacts_readiness_path("creator_prefab_user_t2_stability_report.json")


def main() -> int:
    blockers: list[str] = []
    checks: dict[str, object] = {}

    if yaml is None or not CUTOVER.is_file():
        blockers.append("missing prefab_cutover.yaml")
    else:
        cutover = yaml.safe_load(CUTOVER.read_text(encoding="utf-8")) or {}
        domains = cutover.get("domains") or {}
        domain_states = {
            name: (cfg or {}).get("cutover")
            for name, cfg in domains.items()
            if isinstance(cfg, dict)
        }
        checks["domainCutover"] = domain_states
        if not all(state == "done" for state in domain_states.values()):
            blockers.append("not all domains cutover=done")

    if T2_REPORT.is_file():
        t2 = json.loads(T2_REPORT.read_text(encoding="utf-8"))
        checks["t2Stability"] = t2.get("decision")
        if t2.get("decision") != "go":
            blockers.append("t2 stability report not go")
    else:
        blockers.append("missing t2 stability report")

    for manifest_name in (
        "app_alpha_seed_manifest.json",
        "app_beta_seed_manifest.json",
        "app_gamma_seed_manifest.json",
    ):
        path = REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures" / manifest_name
        if not path.is_file():
            blockers.append(f"missing {manifest_name}")
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        domains = {item.get("domain") for item in manifest.get("seedRefs") or [] if isinstance(item, dict)}
        has_creator = "creator_pool" in domains
        checks[f"{manifest_name}.creatorPool"] = has_creator
        if not has_creator and manifest.get("environment") != "prod":
            blockers.append(f"{manifest_name} missing creator_pool domain")

    code = subprocess.run(
        ["python3", "quwoquan_data/scripts/verify/verify_prefab_user_provenance.py"],
        cwd=REPO_ROOT,
        check=False,
    ).returncode
    checks["prefabProvenanceGate"] = code == 0
    if code != 0:
        blockers.append("prefab provenance gate failed")

    decision = "go" if not blockers else "gate_block"
    report = {
        "schemaVersion": "creator_prefab_user_four_env_readiness/1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "checks": checks,
        "blockers": blockers,
        "note": "T4 legacy user_pool.json entries retained read-only until explicit retire apply; dual-read resolver aliases remain for rollback.",
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[four-env-readiness] decision={decision} artifact={ARTIFACT}")
    return 0 if decision == "go" else 1


if __name__ == "__main__":
    raise SystemExit(main())
