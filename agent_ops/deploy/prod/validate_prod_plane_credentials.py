#!/usr/bin/env python3
"""按平面硬校验 prod-hosted 的 SSH 发布凭据（退役 PROD_KUBECONFIG 单一全权凭据）。

访问隔离映射唯一真相源：deploy/shared/prod_plane_access_isolation.yaml。
对给定 rollout stage（gray-initial/carry-on/full）下「适用」的每个读写平面：
  - 从环境变量读取该平面的 sshKeySecret（如 PROD_EDGE_SSH_KEY）。
  - 硬校验：非空、且形如 OpenSSH/PEM 私钥（含 BEGIN ... PRIVATE KEY）。
任一缺失/非法即硬失败（exit 2），禁止「失败当成功放通」。

用法：
  python3 agent_ops/deploy/prod/validate_prod_plane_credentials.py --stage gray-initial
  python3 agent_ops/deploy/prod/validate_prod_plane_credentials.py --stage full --require-relay
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FAIL: PyYAML required", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
ACCESS = ROOT / "deploy/shared/prod_plane_access_isolation.yaml"

PRIVATE_KEY_MARKERS = (
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----",
)


def looks_like_private_key(value: str) -> bool:
    text = value.strip()
    return any(marker in text for marker in PRIVATE_KEY_MARKERS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=["gray-initial", "carry-on", "full"],
        required=True,
    )
    parser.add_argument(
        "--require-relay",
        action="store_true",
        help="同时要求 relayAccount(PROD_OPS_SSH_KEY) 存在（bootstrap/凭据分发场景）。",
    )
    return parser.parse_args()


def main() -> int:
    if not ACCESS.exists():
        print(f"FAIL: 缺少访问隔离映射 {ACCESS}", file=sys.stderr)
        return 2
    access = yaml.safe_load(ACCESS.read_text(encoding="utf-8"))
    args = parse_args()

    # 反向保险：彻底退役 PROD_KUBECONFIG，不允许任何 prod 路径继续依赖它。
    if os.environ.get("PROD_KUBECONFIG", "").strip():
        print(
            "::error::PROD_KUBECONFIG 已退役，禁止再注入；请改用按平面 SSH 凭据 PROD_<PLANE>_SSH_KEY",
            file=sys.stderr,
        )
        return 2

    issues: list[str] = []
    checked: list[str] = []

    required_secrets: list[tuple[str, str]] = []
    for plane in access.get("planes") or []:
        if str(plane.get("access")) != "read-write":
            continue
        if args.stage not in (plane.get("appliesToStages") or []):
            continue
        required_secrets.append((str(plane.get("plane")), str(plane.get("sshKeySecret"))))

    if args.require_relay:
        relay = access.get("relayAccount") or {}
        required_secrets.append(("relay", str(relay.get("sshKeySecret"))))

    if not required_secrets:
        print(f"FAIL: stage={args.stage} 未解析出任何需要校验的平面凭据", file=sys.stderr)
        return 2

    for plane, secret_name in required_secrets:
        value = os.environ.get(secret_name, "")
        if not value.strip():
            issues.append(f"{plane}: 缺少/空的 SSH 凭据 secret {secret_name}")
            continue
        if not looks_like_private_key(value):
            issues.append(
                f"{plane}: {secret_name} 不像 OpenSSH/PEM 私钥（缺少 BEGIN ... PRIVATE KEY）"
            )
            continue
        checked.append(f"{plane}:{secret_name}")

    if issues:
        print(f"::error::prod 平面 SSH 凭据硬校验失败（stage={args.stage}）", file=sys.stderr)
        for item in issues:
            print(f"  - {item}", file=sys.stderr)
        return 2

    print(f"OK: prod 平面 SSH 凭据齐备（stage={args.stage}）: {', '.join(checked)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
