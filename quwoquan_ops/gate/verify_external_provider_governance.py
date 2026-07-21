#!/usr/bin/env python3
"""Block drift between external Capability, Adapter, Binding and conformance truth."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.external_provider_governance import (
    composition_issues,
    load_and_compile,
    load_registry,
)


def main() -> int:
    try:
        compiled, issues = load_and_compile()
        issues = [
            *issues,
            *composition_issues(load_registry(), compiled),
        ]
    except (OSError, ValueError) as exc:
        print(f"[verify_external_provider_governance] FAIL\n  - cannot compile registry: {exc}")
        return 1
    if issues:
        print("[verify_external_provider_governance] FAIL")
        for issue in issues:
            print(f"  - {issue.render()}")
        return 1
    print(
        "[verify_external_provider_governance] OK "
        f"({compiled['capabilityCount']} capabilities, {compiled['adapterCount']} adapters)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
