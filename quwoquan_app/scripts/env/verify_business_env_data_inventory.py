#!/usr/bin/env python3
"""直接校验 alpha/beta/gamma seed manifests；不读取手工环境 inventory。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
MANIFESTS = {
    environment: METADATA / "_shared" / "test_fixtures" / f"app_{environment}_seed_manifest.json"
    for environment in ("alpha", "beta", "gamma")
}


def main() -> int:
    failures: list[str] = []
    totals: dict[str, int] = {}
    for environment, path in MANIFESTS.items():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{environment}: cannot read seed manifest: {exc}")
            continue
        if payload.get("environment") != environment:
            failures.append(f"{environment}: manifest environment mismatch")
        rows = payload.get("seedRefs")
        if not isinstance(rows, list) or not rows:
            failures.append(f"{environment}: seedRefs must be a non-empty list")
            continue
        domains: set[str] = set()
        refs: set[str] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                failures.append(f"{environment}: seedRefs[{index}] must be an object")
                continue
            domain = row.get("domain")
            fixture = row.get("fixturePath")
            row_refs = row.get("refs")
            if not isinstance(domain, str) or not domain:
                failures.append(f"{environment}: seedRefs[{index}] missing domain")
            elif domain in domains:
                failures.append(f"{environment}: duplicate domain {domain}")
            else:
                domains.add(domain)
            if not isinstance(fixture, str) or not (ROOT / fixture).is_file():
                failures.append(f"{environment}: fixturePath does not exist: {fixture!r}")
            if not isinstance(row_refs, list) or not row_refs or not all(isinstance(item, str) and item for item in row_refs):
                failures.append(f"{environment}: {domain} refs must be non-empty strings")
                continue
            duplicate_refs = refs.intersection(row_refs)
            if duplicate_refs:
                failures.append(f"{environment}: duplicate seed refs {sorted(duplicate_refs)}")
            refs.update(row_refs)
        totals[environment] = len(refs)
    if failures:
        print("[verify_business_env_data] FAIL", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    summary = ", ".join(f"{name}={count}" for name, count in totals.items())
    print(f"[verify_business_env_data] OK ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
