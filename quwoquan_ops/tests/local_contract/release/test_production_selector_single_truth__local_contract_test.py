# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-004.t2
"""Prod 版本选择语义只有一处 canonical 声明。

`release_selection_policy.yaml#production` 是 canonical（release_tag_admission 消费）；
`branch_policy.yaml#production_selector` 是分支治理侧的投影（git_branch_policy 消费）。
两者若在 selector / acceptedTagKind / mainHeadDenied / mutablePointerDenied 上分叉，
就会出现"分支门禁放行、标签准入拒绝"的双真相。
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
CANONICAL = ROOT / "quwoquan_ops/policies/release_selection_policy.yaml"
PROJECTION = ROOT / "quwoquan_ops/policies/branch_policy.yaml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_branch_policy_production_selector_projects_release_selection_policy() -> None:
    canonical = _load(CANONICAL)["production"]
    projection = _load(PROJECTION)["production_selector"]

    assert projection["source"] == canonical["selector"] == "ReleaseTagAdmissionFact"
    assert projection["acceptedTagKind"] == canonical["acceptedTagKind"] == "stable"
    for shared in ("mainHeadDenied", "mutablePointerDenied"):
        assert projection[shared] is True and canonical[shared] is True, shared
    # 各自消费者独有的字段只允许下面两个：branch 侧要求 exact OCI digests，tag 侧显式拒绝 RC。
    assert set(projection) - set(canonical) == {"source", "exactOciDigestsRequired"}
    assert set(canonical) - set(projection) == {"selector", "rcDenied"}
    assert projection["exactOciDigestsRequired"] is True
    assert canonical["rcDenied"] is True
