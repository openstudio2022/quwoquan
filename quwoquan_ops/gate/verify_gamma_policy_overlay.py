#!/usr/bin/env python3
"""N2-2 门禁：gamma 选择的推荐 policy 资源不得成为第二真相源。

gamma releaseRef 所选 policy 允许与公共 service policy 的差异只有：
  1. objectCards.enabled（环境灰度开关）
  2. policyVersion（环境后缀）
  3. 文件头注释

其余任何键（权重/实验/曝光治理/召回融合/运营干预）漂移一律 BLOCK：
业务演进必须先改公共 service resource，再生成明确版本的候选资源。
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("BLOCK: pyyaml required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[2]
METADATA_POLICY = (
    ROOT
    / "quwoquan_service/services/content-service/resources/policies/content/post"
    / "recommendation_policy.yaml"
)
GAMMA_OVERLAY = (
    ROOT
    / "quwoquan_service/services/content-service/resources/policies/content/post"
    / "recommendation_policy_object_cards_v1.yaml"
)

ALLOWED_DIFF_PATHS = {
    ("objectCards", "enabled"),
    ("policyVersion",),
}


def flatten(node, prefix=()):  # noqa: ANN001 - 递归 yaml 节点
    if isinstance(node, dict):
        for key, value in node.items():
            yield from flatten(value, prefix + (str(key),))
    elif isinstance(node, list):
        # 列表按序列整体比较（实验 buckets 等顺序敏感）。
        yield prefix, tuple(repr(item) for item in node)
    else:
        yield prefix, node


def main() -> int:
    if not GAMMA_OVERLAY.exists():
        print(f"BLOCK: gamma overlay missing: {GAMMA_OVERLAY}", file=sys.stderr)
        return 1
    base = yaml.safe_load(METADATA_POLICY.read_text(encoding="utf-8"))
    overlay = yaml.safe_load(GAMMA_OVERLAY.read_text(encoding="utf-8"))

    base_flat = dict(flatten(base))
    overlay_flat = dict(flatten(overlay))

    violations: list[str] = []
    for path in sorted(set(base_flat) | set(overlay_flat)):
        if base_flat.get(path) == overlay_flat.get(path):
            continue
        if path in ALLOWED_DIFF_PATHS:
            continue
        violations.append(
            f"  {'.'.join(path)}: metadata={base_flat.get(path)!r} overlay={overlay_flat.get(path)!r}"
        )

    if violations:
        print("BLOCK: gamma-local policy overlay drifted beyond allowed diff paths:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        print("修复：先改 metadata policy.yaml，再重新派生 overlay（只保留 objectCards.enabled/policyVersion 差异）。", file=sys.stderr)
        return 1

    if overlay.get("objectCards", {}).get("enabled") is not True:
        print("BLOCK: gamma overlay must enable objectCards (N2-2 验收开关)", file=sys.stderr)
        return 1
    print("OK: gamma-local policy overlay in sync (allowed diff: objectCards.enabled, policyVersion)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
