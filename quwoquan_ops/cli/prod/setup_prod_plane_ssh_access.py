#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology


ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod_plane_access_isolation.yaml"
DEFAULT_KEY_DIR = Path.home() / ".ssh" / "quwoquan-prod"
DEFAULT_STATE_DIR = ROOT / ".qwq_output" / "env" / "repo" / "local" / "prod-ssh"
RETIRED_GITHUB_ACTION_SECRETS = (
    "PROD_KUBECONFIG",
    "PROD_SSH_HOST",
    "PROD_EDGE_SSH_KEY",
    "PROD_MEDIA_SSH_KEY",
    "PROD_SERVICE_SSH_KEY",
    "PROD_DATA_SSH_KEY",
    "PROD_OPS_SSH_KEY",
    "GAMMA_BASE_URL",
    "GAMMA_PRODUCT_OPS_BASE_URL",
    "GAMMA_ECS_HOST",
    "GAMMA_ECS_USER",
    "GAMMA_ECS_PASSWORD",
    "GAMMA_ECS_SSH_KEY",
)


@dataclass(frozen=True)
class ProdAccountSpec:
    spec_id: str
    role: str
    plane: str | None
    account: str
    home: str
    compose_project_root: str | None
    credentials_path: str | None
    ssh_key_secret: str
    access: str
    applies_to_stages: list[str]
    runtime_container: str | None
    private_key_path: Path
    public_key_path: Path


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: {path} 解析后不是 object")
    return data


def _resolve_prod_host(override: str | None) -> str:
    if override:
        return override
    topology = load_environment_topology()
    target = get_target(topology, "prod-hosted")
    api_base = str((target.get("publicBases") or {}).get("api", "")).strip()
    host = urlparse(api_base).hostname
    if not host:
        raise SystemExit(f"FAIL: 无法从 prod-hosted api 地址解析 hostname: {api_base}")
    return host


def _load_account_specs(key_dir: Path) -> list[ProdAccountSpec]:
    access = _load_yaml(ACCESS_MANIFEST)
    relay = access.get("relayAccount") or {}
    specs: list[ProdAccountSpec] = [
        ProdAccountSpec(
            spec_id="relay",
            role="relay",
            plane=None,
            account=str(relay["name"]),
            home=str(relay["home"]),
            compose_project_root=relay.get("bootstrapPath"),
            credentials_path=None,
            ssh_key_secret=str(relay["sshKeySecret"]),
            access="bootstrap",
            applies_to_stages=[],
            runtime_container=None,
            private_key_path=key_dir / str(relay["name"]),
            public_key_path=(key_dir / str(relay["name"])).with_suffix(".pub"),
        )
    ]
    for plane in access.get("planes", []):
        account = str(plane["account"])
        private_key_path = key_dir / account
        access_mode = str(plane.get("access", "")).strip()
        role = "deploy" if access_mode == "read-write" else "readonly"
        specs.append(
            ProdAccountSpec(
                spec_id=f"plane:{plane['plane']}",
                role=role,
                plane=str(plane["plane"]),
                account=account,
                home=str(plane["home"]),
                compose_project_root=plane.get("composeProjectRoot"),
                credentials_path=plane.get("credentialsPath"),
                ssh_key_secret=str(plane["sshKeySecret"]),
                access=access_mode,
                applies_to_stages=list(plane.get("appliesToStages", [])),
                runtime_container=plane.get("runtimeContainer"),
                private_key_path=private_key_path,
                public_key_path=private_key_path.with_suffix(".pub"),
            )
        )
    return specs


def _select_specs(
    all_specs: list[ProdAccountSpec],
    *,
    include_relay: bool,
    include_readonly: bool,
) -> list[ProdAccountSpec]:
    role_rank = {"deploy": 0, "relay": 1, "readonly": 2}
    selected: list[ProdAccountSpec] = []
    for spec in sorted(all_specs, key=lambda item: (role_rank.get(item.role, 99), item.account)):
        if spec.role == "deploy":
            selected.append(spec)
        elif spec.role == "relay" and include_relay:
            selected.append(spec)
        elif spec.role == "readonly" and include_readonly:
            selected.append(spec)
    if not selected:
        raise SystemExit("FAIL: 当前参数未选择任何 prod SSH 账号")
    return selected


def _backup_existing_keypair(private_key_path: Path) -> Path | None:
    public_key_path = private_key_path.with_suffix(".pub")
    existing_paths = [path for path in (private_key_path, public_key_path) if path.exists()]
    if not existing_paths:
        return None
    backup_dir = private_key_path.parent / "_rotated" / _utc_stamp() / private_key_path.name
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.parent.chmod(0o700)
    for path in existing_paths:
        shutil.move(str(path), str(backup_dir / path.name))
    return backup_dir


def _ensure_keypair(
    private_key_path: Path,
    *,
    force: bool,
    comment: str,
    rotation_backups: dict[str, str],
) -> str:
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key_path.parent.chmod(0o700)
    public_key_path = private_key_path.with_suffix(".pub")
    if private_key_path.exists() and public_key_path.exists() and not force:
        return "reused"
    if force:
        backup_dir = _backup_existing_keypair(private_key_path)
        if backup_dir is not None:
            rotation_backups[private_key_path.name] = str(backup_dir)
    subprocess.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            comment,
            "-f",
            str(private_key_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    private_key_path.chmod(0o600)
    public_key_path.chmod(0o644)
    return "rotated" if force else "created"


def _write_mapping_outputs(
    *,
    mapping_out: Path,
    instructions_out: Path,
    host: str,
    specs: list[ProdAccountSpec],
    key_statuses: dict[str, str],
    rotation_backups: dict[str, str],
) -> None:
    mapping_out.parent.mkdir(parents=True, exist_ok=True)
    instructions_out.parent.mkdir(parents=True, exist_ok=True)

    mapping = {
        "target": "prod-hosted",
        "host": host,
        "keyDirectory": str(specs[0].private_key_path.parent),
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "accounts": [
            {
                "specId": spec.spec_id,
                "role": spec.role,
                "plane": spec.plane,
                "account": spec.account,
                "access": spec.access,
                "sshKeySecret": spec.ssh_key_secret,
                "appliesToStages": spec.applies_to_stages,
                "privateKeyPath": str(spec.private_key_path),
                "publicKeyPath": str(spec.public_key_path),
                "status": key_statuses[spec.account],
                "rotationBackup": rotation_backups.get(spec.account, ""),
            }
            for spec in specs
        ],
    }
    mapping_out.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Prod SSH Bootstrap",
        "",
        f"- target: `prod-hosted`",
        f"- host: `{host}`",
        f"- key dir: `{specs[0].private_key_path.parent}`",
        f"- local state dir: `{mapping_out.parent}`",
        "",
        "## Selected Accounts",
        "",
        "| Role | Plane | Account | Logical Key Id | Private Key | Public Key | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for spec in specs:
        lines.append(
            f"| `{spec.role}` | `{spec.plane or '-'}` | `{spec.account}` | `{spec.ssh_key_secret}` | "
            f"`{spec.private_key_path}` | `{spec.public_key_path}` | `{key_statuses[spec.account]}` |"
        )
    lines.extend(
        [
            "",
            "## Self-hosted Runner / Local Key Store",
            "",
            "prod 私钥不再进入 GitHub Actions secrets。workflow 只在 self-hosted runner 上运行，并从本机 key dir 或 ssh-agent 取钥。",
            "",
            "以下逻辑 key id 仍保留在访问隔离映射中，用于把账号、发布脚本和说明文档绑定到同一套命名：",
            "",
        ]
    )
    for spec in specs:
        lines.append(
            f"- `{spec.ssh_key_secret}` -> `{spec.account}` (`{spec.private_key_path}` / `{spec.public_key_path}`)"
        )
    lines.extend(
        [
            "",
            "self-hosted runner 推荐做法：",
            "",
            f"- 固定 key dir：`{specs[0].private_key_path.parent}`",
            "- 或预先 `ssh-add` 对应私钥，再让 workflow 走 ssh-agent。",
            "- 如需显式指定路径，可设置 `PROD_<PLANE>_SSH_KEY_FILE` / `PROD_<PLANE>_SSH_KEY_PATH`。",
            "",
            "`.pub` 文件只用于远端服务器的 `authorized_keys` 安装；本工具的 remote/bootstrap 步骤会自动读取并写入。",
            "",
            "推荐一键命令：",
            "",
            "`bash quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.sh --mode all --include-relay --include-readonly --github-prune-obsolete-secrets`",
            "",
            "如需导出可传播的密钥包，请先设置 `PROD_SSH_BUNDLE_PASSPHRASE`，再追加：",
            "",
            "`--export-encrypted-bundle`",
            "",
        ]
    )
    instructions_out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_admin_ssh_prefix(
    *,
    bootstrap_user: str,
    host: str,
    bootstrap_key_file: str | None,
) -> tuple[list[str], dict[str, str]]:
    env = os.environ.copy()
    if bootstrap_key_file:
        return (
            [
                "ssh",
                "-i",
                bootstrap_key_file,
                "-o",
                "StrictHostKeyChecking=accept-new",
                f"{bootstrap_user}@{host}",
            ],
            env,
        )
    raise SystemExit("FAIL: remote/all 模式需要 bootstrap key file（已退役 sshpass / 口令模式）")


def _resolve_github_repo(override: str | None) -> str:
    if override:
        return override
    if not shutil.which("gh"):
        raise SystemExit("FAIL: 未安装 gh，无法清理 GitHub Actions 旧 secrets")
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "FAIL: 无法通过 gh 解析当前仓库，请先 `gh auth login`，"
            f"或显式传入 --github-repo。stderr={result.stderr.strip()}"
        )
    repo = result.stdout.strip()
    if not repo:
        raise SystemExit("FAIL: gh repo view 未返回有效仓库标识")
    return repo

def _prune_github_secrets(*, github_repo: str) -> list[str]:
    result = subprocess.run(
        ["gh", "secret", "list", "--repo", github_repo, "--app", "actions"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    existing = {
        line.split("\t", 1)[0].strip()
        for line in result.stdout.splitlines()
        if line.strip()
    }
    deleted: list[str] = []
    for secret_name in RETIRED_GITHUB_ACTION_SECRETS:
        if secret_name not in existing:
            continue
        subprocess.run(
            ["gh", "secret", "delete", secret_name, "--repo", github_repo, "--app", "actions"],
            cwd=ROOT,
            text=True,
            check=True,
        )
        deleted.append(secret_name)
    return deleted


def _bootstrap_accounts(
    *,
    host: str,
    bootstrap_user: str,
    bootstrap_key_file: str | None,
) -> None:
    env = os.environ.copy()
    env.update(
        {
            "DRY_RUN": "false",
            "PROD_BOOTSTRAP_SSH_HOST": host,
            "PROD_BOOTSTRAP_SSH_USER": bootstrap_user,
        }
    )
    if bootstrap_key_file:
        env["PROD_BOOTSTRAP_SSH_KEY_FILE"] = bootstrap_key_file
    subprocess.run(
        ["bash", "quwoquan_ops/cli/prod/bootstrap_prod_plane_accounts.sh"],
        cwd=ROOT,
        env=env,
        check=True,
    )


def _install_public_keys(
    *,
    specs: list[ProdAccountSpec],
    host: str,
    bootstrap_user: str,
    bootstrap_key_file: str | None,
) -> None:
    ssh_prefix, env = _build_admin_ssh_prefix(
        bootstrap_user=bootstrap_user,
        host=host,
        bootstrap_key_file=bootstrap_key_file,
    )
    remote_shell = "bash -s" if bootstrap_user == "root" else "sudo bash -s"
    lines = [
        "set -euo pipefail",
        "install_pubkey() {",
        "  local account=\"$1\"",
        "  local pubkey=\"$2\"",
        "  local home shell",
        "  home=\"$(getent passwd \"$account\" | cut -d: -f6)\"",
        "  shell=\"$(getent passwd \"$account\" | cut -d: -f7)\"",
        "  if [[ -z \"$home\" ]]; then",
        "    echo \"FAIL: user missing: $account\" >&2",
        "    exit 2",
        "  fi",
        "  if [[ \"$shell\" != \"/bin/bash\" ]]; then",
        "    chsh -s /bin/bash \"$account\" >/dev/null 2>&1 || usermod -s /bin/bash \"$account\"",
        "  fi",
        "  install -d -m 0700 -o \"$account\" -g \"$account\" \"$home/.ssh\"",
        "  touch \"$home/.ssh/authorized_keys\"",
        "  chown \"$account:$account\" \"$home/.ssh/authorized_keys\"",
        "  chmod 0600 \"$home/.ssh/authorized_keys\"",
        "  if ! grep -Fqx \"$pubkey\" \"$home/.ssh/authorized_keys\"; then",
        "    printf '%s\\n' \"$pubkey\" >> \"$home/.ssh/authorized_keys\"",
        "    echo \"[done] installed $account pubkey\"",
        "  else",
        "    echo \"[skip] $account pubkey already present\"",
        "  fi",
        "}",
    ]
    for spec in specs:
        pubkey = spec.public_key_path.read_text(encoding="utf-8").strip()
        lines.append(f"install_pubkey {shlex.quote(spec.account)} {shlex.quote(pubkey)}")
    remote_script = "\n".join(lines) + "\n"
    subprocess.run(
        [*ssh_prefix, remote_shell],
        env=env,
        input=remote_script,
        text=True,
        check=True,
    )


def _verify_account_logins(specs: list[ProdAccountSpec], host: str) -> None:
    for spec in specs:
        checks = [
            "printf 'ACCOUNT=%s\\n' \"$(whoami)\"",
            f"test -d {shlex.quote(spec.home)}",
        ]
        if spec.credentials_path:
            checks.append(f"test -d {shlex.quote(spec.credentials_path)}")
        if spec.compose_project_root:
            checks.append(f"test -d {shlex.quote(spec.compose_project_root)}")
        remote_cmd = " && ".join(checks)
        subprocess.run(
            [
                "ssh",
                "-i",
                str(spec.private_key_path),
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=12",
                f"{spec.account}@{host}",
                remote_cmd,
            ],
            check=True,
        )


def _export_encrypted_bundle(
    *,
    specs: list[ProdAccountSpec],
    bundle_out: Path,
    passphrase_env_name: str,
    host: str,
) -> Path:
    if not shutil.which("openssl"):
        raise SystemExit("FAIL: 导出加密 bundle 需要本机安装 openssl")
    passphrase = os.environ.get(passphrase_env_name, "")
    if not passphrase:
        raise SystemExit(
            f"FAIL: 导出加密 bundle 需要设置环境变量 {passphrase_env_name}"
        )
    bundle_out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage_root = Path(tmp) / "prod-ssh-bundle"
        stage_root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "target": "prod-hosted",
            "host": host,
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "accounts": [],
        }
        for spec in specs:
            shutil.copy2(spec.private_key_path, stage_root / spec.private_key_path.name)
            shutil.copy2(spec.public_key_path, stage_root / spec.public_key_path.name)
            manifest["accounts"].append(
                {
                    "role": spec.role,
                    "plane": spec.plane,
                    "account": spec.account,
                    "sshKeySecret": spec.ssh_key_secret,
                    "privateKeyFile": spec.private_key_path.name,
                    "publicKeyFile": spec.public_key_path.name,
                }
            )
        (stage_root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tar_path = Path(tmp) / "prod-ssh-bundle.tar"
        with tarfile.open(tar_path, "w") as tar:
            tar.add(stage_root, arcname="prod-ssh-bundle")
        env = os.environ.copy()
        env["PROD_SSH_BUNDLE_PASSPHRASE_VALUE"] = passphrase
        subprocess.run(
            [
                "openssl",
                "enc",
                "-aes-256-cbc",
                "-salt",
                "-pbkdf2",
                "-in",
                str(tar_path),
                "-out",
                str(bundle_out),
                "-pass",
                "env:PROD_SSH_BUNDLE_PASSPHRASE_VALUE",
            ],
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    return bundle_out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成 prod SSH key，并可自动 bootstrap 远端账号、安装公钥、加密导出、清理 GitHub 旧 secret。"
    )
    parser.add_argument(
        "--mode",
        choices=("generate", "remote", "all"),
        default="all",
        help="generate=只生成本地 key；remote=只做远端安装；all=两者都做",
    )
    parser.add_argument(
        "--key-dir",
        default=str(DEFAULT_KEY_DIR),
        help="本地私钥目录（默认 ~/.ssh/quwoquan-prod）",
    )
    parser.add_argument(
        "--mapping-out",
        default=str(DEFAULT_STATE_DIR / "plane_key_map.json"),
        help="输出账号/host/key 路径映射 JSON（默认 .qwq_output/env/repo/local/prod-ssh）",
    )
    parser.add_argument(
        "--instructions-out",
        default=str(DEFAULT_STATE_DIR / "runner_key_setup.md"),
        help="输出 self-hosted runner / 导出说明 Markdown（默认 .qwq_output/env/repo/local/prod-ssh）",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="覆盖 prod-hosted 目标 host；默认从 environment_topology_manifest.yaml 解析",
    )
    parser.add_argument(
        "--include-relay",
        action="store_true",
        help="把 prod-ops 也纳入生成/安装/校验范围",
    )
    parser.add_argument(
        "--include-readonly",
        action="store_true",
        help="把只读 data 平面账号也纳入生成/安装/校验范围",
    )
    parser.add_argument(
        "--all-accounts",
        action="store_true",
        help="等价于同时开启 --include-relay 与 --include-readonly",
    )
    parser.add_argument(
        "--bootstrap-user",
        default=os.environ.get("PROD_BOOTSTRAP_SSH_USER", "root"),
        help="一次性 bootstrap 管理员账号（默认 root）",
    )
    parser.add_argument(
        "--bootstrap-key-file",
        default=os.environ.get("PROD_BOOTSTRAP_SSH_KEY_FILE"),
        help="一次性 bootstrap 管理员私钥文件",
    )
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="保留旧 key 备份并生成新 key（staged rotation 起点）",
    )
    parser.add_argument(
        "--skip-verify-login",
        action="store_true",
        help="完成远端安装后跳过逐账号 SSH 登录验收",
    )
    parser.add_argument(
        "--github-repo",
        default=os.environ.get("GH_REPO"),
        help="GitHub 仓库，格式 owner/repo；默认用 gh repo view 自动解析",
    )
    parser.add_argument(
        "--github-prune-obsolete-secrets",
        action="store_true",
        help="删除已退役或不再允许存在的 GitHub Actions secrets（含 PROD_*_SSH_KEY）",
    )
    parser.add_argument(
        "--export-encrypted-bundle",
        action="store_true",
        help="把当前选择的账号私钥导出为受密码保护的 bundle，便于受控传播",
    )
    parser.add_argument(
        "--bundle-out",
        default=str(DEFAULT_STATE_DIR / "prod_ssh_keys.tar.enc"),
        help="加密 bundle 输出路径（默认 .qwq_output/env/repo/local/prod-ssh/prod_ssh_keys.tar.enc）",
    )
    parser.add_argument(
        "--bundle-passphrase-env",
        default="PROD_SSH_BUNDLE_PASSPHRASE",
        help="读取 bundle 密码的环境变量名（默认 PROD_SSH_BUNDLE_PASSPHRASE）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    include_relay = args.include_relay or args.all_accounts
    include_readonly = args.include_readonly or args.all_accounts
    host = _resolve_prod_host(args.host)
    key_dir = Path(args.key_dir).expanduser()
    mapping_out = Path(args.mapping_out)
    instructions_out = Path(args.instructions_out)
    bundle_out = Path(args.bundle_out)
    specs = _select_specs(
        _load_account_specs(key_dir),
        include_relay=include_relay,
        include_readonly=include_readonly,
    )

    rotation_backups: dict[str, str] = {}
    key_statuses: dict[str, str] = {}
    if args.mode in {"generate", "all"}:
        for spec in specs:
            key_statuses[spec.account] = _ensure_keypair(
                spec.private_key_path,
                force=args.force_regenerate,
                comment=f"{spec.account}@{host}",
                rotation_backups=rotation_backups,
            )
    else:
        for spec in specs:
            if not spec.private_key_path.exists() or not spec.public_key_path.exists():
                raise SystemExit(
                    f"FAIL: remote 模式要求本地 key 已存在: {spec.private_key_path} / {spec.public_key_path}"
                )
            key_statuses[spec.account] = "existing"

    _write_mapping_outputs(
        mapping_out=mapping_out,
        instructions_out=instructions_out,
        host=host,
        specs=specs,
        key_statuses=key_statuses,
        rotation_backups=rotation_backups,
    )

    if args.mode in {"remote", "all"}:
        _bootstrap_accounts(
            host=host,
            bootstrap_user=args.bootstrap_user,
            bootstrap_key_file=args.bootstrap_key_file,
        )
        _install_public_keys(
            specs=specs,
            host=host,
            bootstrap_user=args.bootstrap_user,
            bootstrap_key_file=args.bootstrap_key_file,
        )
        if not args.skip_verify_login:
            _verify_account_logins(specs, host)

    github_repo: str | None = None
    deleted_github_secrets: list[str] = []
    if args.github_prune_obsolete_secrets:
        github_repo = _resolve_github_repo(args.github_repo)
    if args.github_prune_obsolete_secrets:
        deleted_github_secrets = _prune_github_secrets(github_repo=github_repo or "")

    bundle_path: Path | None = None
    if args.export_encrypted_bundle:
        bundle_path = _export_encrypted_bundle(
            specs=specs,
            bundle_out=bundle_out,
            passphrase_env_name=args.bundle_passphrase_env,
            host=host,
        )

    print(f"[done] host={host}")
    print(f"[done] mapping={mapping_out}")
    print(f"[done] instructions={instructions_out}")
    if bundle_path is not None:
        print(f"[done] encrypted_bundle={bundle_path}")
    if github_repo is not None:
        print(f"[done] github_repo={github_repo}")
    if deleted_github_secrets:
        print("[done] github_deleted=" + ",".join(deleted_github_secrets))
    for spec in specs:
        print(
            f"[done] role={spec.role} plane={spec.plane or '-'} account={spec.account} "
            f"secret={spec.ssh_key_secret} private={spec.private_key_path} "
            f"public={spec.public_key_path} status={key_statuses[spec.account]}"
        )
        if spec.account in rotation_backups:
            print(f"[done] rotation_backup[{spec.account}]={rotation_backups[spec.account]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
