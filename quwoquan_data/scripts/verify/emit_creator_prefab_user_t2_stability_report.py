#!/usr/bin/env python3
"""Emit T2 stability report for creator prefab user dual-track migration."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = REPO_ROOT / "artifacts" / "creator_prefab_user_t2_stability_report.json"


def _run(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, result.stdout


def main() -> int:
    checks: dict[str, object] = {}
    blockers: list[str] = []

    code, out = _run(["python3", "quwoquan_data/scripts/verify/verify_prefab_user_provenance.py"])
    checks["prefabUserProvenanceGate"] = {"exitCode": code, "passed": code == 0}
    if code != 0:
        blockers.append("verify_prefab_user_provenance failed")

    code, out = _run(["python3", "quwoquan_data/scripts/verify/verify_creator_pool_seed_consistency.py"])
    checks["creatorPoolSeedConsistency"] = {"exitCode": code, "passed": code == 0}
    if code != 0:
        blockers.append("verify_creator_pool_seed_consistency failed")

    code, out = _run(
        ["go", "test", "./tests", "-run", "^TestContractFixtureSeed_CreatorPoolBetaReadsViaHandler$", "-count=1"],
        cwd=REPO_ROOT / "quwoquan_service/services/user-service",
    )
    checks["creatorPoolApiIntegration"] = {"exitCode": code, "passed": code == 0, "note": out[-500:]}
    if code != 0:
        blockers.append("CreatorPool beta handler seed test failed")

    manifest_path = REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/user_pool.manifest.json"
    creator_path = REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/user_pool.creator_pool.json"
    if manifest_path.is_file() and creator_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        creator = json.loads(creator_path.read_text(encoding="utf-8"))
        checks["dualTrackConsistency"] = {
            "creatorPoolUserCount": len(creator.get("users") or []),
            "legacyUserCount": manifest.get("statistics", {}).get("legacyUserCount"),
            "passed": len(creator.get("users") or []) >= 101,
        }
        if len(creator.get("users") or []) < 101:
            blockers.append("creator slice < 101 users")
    else:
        blockers.append("missing creator slice or manifest")

    decision = "go" if not blockers else "gate_block"
    report = {
        "schemaVersion": "creator_prefab_user_t2_stability/1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "checks": checks,
        "blockers": blockers,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[t2-stability] decision={decision} artifact={ARTIFACT}")
    if blockers:
        for item in blockers:
            print(f"  blocker: {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
