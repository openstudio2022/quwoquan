#!/usr/bin/env python3
"""阻断推荐策略变体、手工版本身份及 gamma release 漂移。"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("BLOCK: pyyaml required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parents[2]
POLICY_RELATIVE_PATH = Path(
    "quwoquan_service/services/content-service/resources/policies/content/post/"
    "recommendation_policy.yaml"
)
GAMMA_RELEASE_RELATIVE_PATH = Path(
    "quwoquan_service/services/content-service/environments/gamma/resources/"
    "releases/content/post/recommendation_policy.yaml"
)
CANONICAL_RELEASE_REF = (
    "service-resource://policies/content/post/recommendation_policy.yaml"
)
PROD_RENDERER_RELATIVE_PATH = Path(
    "quwoquan_ops/cli/prod/render_prod_plane_stack.py"
)


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validation_issues(root: Path = ROOT) -> list[str]:
    policy_path = root / POLICY_RELATIVE_PATH
    release_path = root / GAMMA_RELEASE_RELATIVE_PATH
    prod_renderer_path = root / PROD_RENDERER_RELATIVE_PATH
    issues: list[str] = []

    if not policy_path.is_file():
        return [f"canonical recommendation policy missing: {policy_path}"]

    variants = sorted(
        path.name
        for path in policy_path.parent.glob("recommendation_policy*.yaml")
        if path != policy_path
    )
    if variants:
        issues.append(
            "recommendation policy variants are forbidden: " + ", ".join(variants)
        )

    if not prod_renderer_path.is_file():
        issues.append(f"prod renderer missing: {prod_renderer_path}")
    else:
        renderer = prod_renderer_path.read_text(encoding="utf-8")
        if '"recommendation_policy.yaml"' not in renderer:
            issues.append("prod renderer must consume the canonical recommendation policy")
        renderer_variants = sorted(
            set(
                re.findall(
                    r"recommendation_policy_[a-zA-Z0-9_-]+\.yaml",
                    renderer,
                )
            )
        )
        if renderer_variants:
            issues.append(
                "prod renderer recommendation policy variants are forbidden: "
                + ", ".join(renderer_variants)
            )

    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        issues.append("canonical recommendation policy must be a YAML object")
    else:
        for forbidden in ("version", "policyVersion"):
            if forbidden in policy:
                issues.append(
                    f"canonical recommendation policy must not declare {forbidden}"
                )
        if (policy.get("objectCards") or {}).get("enabled") is not True:
            issues.append(
                "canonical recommendation policy must own the enabled objectCards decision"
            )

    if not release_path.is_file():
        issues.append(f"gamma recommendation policy release missing: {release_path}")
        return issues
    release = yaml.safe_load(release_path.read_text(encoding="utf-8"))
    if not isinstance(release, dict):
        issues.append("gamma recommendation policy release must be a YAML object")
        return issues
    if release.get("releaseRef") != CANONICAL_RELEASE_REF:
        issues.append("gamma releaseRef must point to the canonical recommendation policy")
    expected_digest = sha256_file(policy_path)
    if release.get("digest") != expected_digest:
        issues.append(
            "gamma recommendation policy digest mismatch: "
            f"declared={release.get('digest')!r} expected={expected_digest!r}"
        )
    if release.get("target") != "runtime/recommendation_policy.yaml":
        issues.append("gamma recommendation policy target is not canonical")
    if release.get("environmentVariable") != "QWQ_REC_POLICY_PATH":
        issues.append("gamma recommendation policy environment binding is not canonical")
    return issues


def main() -> int:
    issues = validation_issues()
    if issues:
        print("BLOCK: recommendation policy is not single-track:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print(
        "OK: one canonical recommendation policy with digest-bound gamma release "
        "and prod renderer"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
