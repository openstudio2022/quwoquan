#!/usr/bin/env python3
"""按平面硬校验 prod-hosted 的 SSH 发布凭据（self-hosted / 本机持钥模型）。

访问隔离映射唯一真相源：quwoquan_ops/environments/prod/access-isolation.yaml。
对给定 rollout stage（gray-initial/carry-on/full）下适用的平面账号，校验以下任一路径：

1. 显式 key 文件：`<SSH_KEY_SECRET>_FILE` / `<SSH_KEY_SECRET>_PATH`
2. 指定 key dir：`--key-dir` 或 `PROD_SSH_KEY_DIR`，按 `<key_dir>/<account>` 查找私钥
3. ssh-agent：当 `<key_dir>/<account>.pub` 存在且 agent 已加载同一公钥时视为有效

任一缺失/非法即硬失败（exit 2），禁止失败放通。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FAIL: PyYAML required", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
ACCESS = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
DEFAULT_KEY_DIR = Path.home() / ".ssh" / "quwoquan-prod"

PRIVATE_KEY_MARKERS = (
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----",
)


@dataclass(frozen=True)
class RequiredCredential:
    plane: str
    account: str
    secret_name: str


@dataclass(frozen=True)
class ResolvedCredential:
    plane: str
    account: str
    secret_name: str
    source: str
    key_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=["gray-initial", "carry-on", "full"],
        required=True,
    )
    parser.add_argument(
        "--key-dir",
        default=os.environ.get("PROD_SSH_KEY_DIR", "").strip(),
        help="平面私钥目录；默认读 PROD_SSH_KEY_DIR，再回退 ~/.ssh/quwoquan-prod。",
    )
    parser.add_argument(
        "--require-relay",
        action="store_true",
        help="同时要求 relayAccount(PROD_OPS_SSH_KEY) 可用（bootstrap/凭据分发场景）。",
    )
    parser.add_argument(
        "--require-readonly",
        action="store_true",
        help="同时要求 readonly audit 账号(PROD_DATA_SSH_KEY) 可用（审计/巡检场景）。",
    )
    parser.add_argument(
        "--no-ssh-agent",
        action="store_true",
        help="仅允许 key file / key dir，不接受 ssh-agent 中已加载的同名公钥。",
    )
    return parser.parse_args()


def _looks_like_private_key_file(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    text = text.strip()
    return any(marker in text for marker in PRIVATE_KEY_MARKERS)


def _load_agent_keys() -> list[str]:
    if not os.environ.get("SSH_AUTH_SOCK", "").strip():
        return []
    result = subprocess.run(
        ["ssh-add", "-L"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _matches_agent(pub_path: Path, loaded_keys: list[str]) -> bool:
    if not pub_path.is_file():
        return False
    expected = pub_path.read_text(encoding="utf-8").strip()
    if not expected:
        return False
    expected_parts = expected.split()
    if len(expected_parts) < 2:
        return False
    expected_key = f"{expected_parts[0]} {expected_parts[1]}"
    for item in loaded_keys:
        parts = item.split()
        if len(parts) < 2:
            continue
        if f"{parts[0]} {parts[1]}" == expected_key:
            return True
    return False


def _env_key_path(secret_name: str) -> Path | None:
    for suffix in ("_FILE", "_PATH"):
        raw = os.environ.get(f"{secret_name}{suffix}", "").strip()
        if raw:
            return Path(raw).expanduser()
    return None


def _key_dir_from_args(args: argparse.Namespace) -> Path:
    if args.key_dir:
        return Path(args.key_dir).expanduser()
    return DEFAULT_KEY_DIR


def _required_credentials(access: dict, args: argparse.Namespace) -> list[RequiredCredential]:
    service_filter = os.environ.get("SERVICE", "").strip()
    required: list[RequiredCredential] = []
    for plane in access.get("planes") or []:
        access_mode = str(plane.get("access", "")).strip()
        if access_mode != "read-write":
            continue
        if args.stage not in (plane.get("appliesToStages") or []):
            continue
        governed = [str(item).strip() for item in (plane.get("rootlessGovernedComposeServices") or []) if str(item).strip()]
        support = [str(item).strip() for item in (plane.get("rootlessSupportComposeServices") or []) if str(item).strip()]
        if ("rootlessGovernedComposeServices" in plane or "rootlessSupportComposeServices" in plane) and not (governed or support):
            continue
        if service_filter and str(plane.get("plane")) == "service" and governed:
            target = {
                "recommendation-service": "recommendation-service",
                "service-plane": "__all__",
            }.get(service_filter, service_filter)
            if target != "__all__" and target not in governed:
                continue
        required.append(
            RequiredCredential(
                plane=str(plane.get("plane")),
                account=str(plane.get("account")),
                secret_name=str(plane.get("sshKeySecret")),
            )
        )
    if args.require_relay:
        relay = access.get("relayAccount") or {}
        required.append(
            RequiredCredential(
                plane="relay",
                account=str(relay.get("name")),
                secret_name=str(relay.get("sshKeySecret")),
            )
        )
    if args.require_readonly:
        for plane in access.get("planes") or []:
            access_mode = str(plane.get("access", "")).strip()
            if access_mode != "read-only-audit":
                continue
            required.append(
                RequiredCredential(
                    plane=str(plane.get("plane")),
                    account=str(plane.get("account")),
                    secret_name=str(plane.get("sshKeySecret")),
                )
            )
    return required


def _resolve_credential(
    required: RequiredCredential,
    *,
    key_dir: Path,
    allow_ssh_agent: bool,
    loaded_agent_keys: list[str],
) -> tuple[ResolvedCredential | None, str | None]:
    explicit_path = _env_key_path(required.secret_name)
    candidate_path = explicit_path or (key_dir / required.account)
    public_key_path = candidate_path.with_suffix(".pub")

    if explicit_path is not None:
        if _looks_like_private_key_file(explicit_path):
            return (
                ResolvedCredential(
                    plane=required.plane,
                    account=required.account,
                    secret_name=required.secret_name,
                    source="explicit-file",
                    key_path=str(explicit_path),
                ),
                None,
            )
        return None, (
            f"{required.plane}: {required.secret_name}_FILE 指向的私钥无效或不存在: {explicit_path}"
        )

    if _looks_like_private_key_file(candidate_path):
        return (
            ResolvedCredential(
                plane=required.plane,
                account=required.account,
                secret_name=required.secret_name,
                source="key-dir-file",
                key_path=str(candidate_path),
            ),
            None,
        )

    if allow_ssh_agent and _matches_agent(public_key_path, loaded_agent_keys):
        return (
            ResolvedCredential(
                plane=required.plane,
                account=required.account,
                secret_name=required.secret_name,
                source="ssh-agent",
                key_path=str(public_key_path),
            ),
            None,
        )

    hint = f"缺少私钥文件 {candidate_path}"
    if allow_ssh_agent:
        hint += f"，且 ssh-agent 未加载匹配公钥 {public_key_path}"
    return None, f"{required.plane}: {required.secret_name} 未就绪（{hint}）"


def main() -> int:
    if not ACCESS.exists():
        print(f"FAIL: 缺少访问隔离映射 {ACCESS}", file=sys.stderr)
        return 2
    access = yaml.safe_load(ACCESS.read_text(encoding="utf-8"))
    args = parse_args()
    key_dir = _key_dir_from_args(args)

    if os.environ.get("PROD_KUBECONFIG", "").strip():
        print(
            "::error::PROD_KUBECONFIG 已退役，禁止再注入；请改用 key file / ssh-agent / PROD_SSH_KEY_DIR 模型",
            file=sys.stderr,
        )
        return 2

    required = _required_credentials(access, args)
    if not required:
        print(f"FAIL: stage={args.stage} 未解析出任何需要校验的平面凭据", file=sys.stderr)
        return 2

    loaded_agent_keys = [] if args.no_ssh_agent else _load_agent_keys()
    resolved: list[ResolvedCredential] = []
    issues: list[str] = []
    for item in required:
        hit, issue = _resolve_credential(
            item,
            key_dir=key_dir,
            allow_ssh_agent=not args.no_ssh_agent,
            loaded_agent_keys=loaded_agent_keys,
        )
        if hit is not None:
            resolved.append(hit)
            continue
        if issue:
            issues.append(issue)

    if issues:
        print(
            f"::error::prod 平面 SSH 凭据硬校验失败（stage={args.stage}, key_dir={key_dir}）",
            file=sys.stderr,
        )
        for item in issues:
            print(f"  - {item}", file=sys.stderr)
        return 2

    summary = ", ".join(
        f"{item.plane}:{item.secret_name} via {item.source} ({item.key_path})"
        for item in resolved
    )
    print(f"OK: prod 平面 SSH 凭据齐备（stage={args.stage}, key_dir={key_dir}）: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
