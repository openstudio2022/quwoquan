#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import deployment_target_path
from quwoquan_ops.cli.lib.prod_management_access import prod_management_ssh_host


ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
DEFAULT_KEY_DIR = Path.home() / ".ssh" / "quwoquan-prod"
DEFAULT_STATE_DIR = deployment_target_path("prod-hosted", "ssh-bootstrap")
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
    try:
        return prod_management_ssh_host(override=override)
    except RuntimeError as error:
        raise SystemExit(f"FAIL: {error}") from error


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
        help="输出账号/host/key 路径映射 JSON（默认仓外 QWQ_DEPLOY_WORK_ROOT/prod-hosted/ssh-bootstrap）",
    )
    parser.add_argument(
        "--instructions-out",
        default=str(DEFAULT_STATE_DIR / "runner_key_setup.md"),
        help="输出 self-hosted runner / 导出说明 Markdown（默认仓外 QWQ_DEPLOY_WORK_ROOT/prod-hosted/ssh-bootstrap）",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="覆盖 prod-hosted SSH host；默认读取 prod/access-isolation.yaml management.sshHost",
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
        help="加密 bundle 输出路径（默认仓外 QWQ_DEPLOY_WORK_ROOT/prod-hosted/ssh-bootstrap/prod_ssh_keys.tar.enc）",
    )
    parser.add_argument(
        "--bundle-passphrase-env",
        default="PROD_SSH_BUNDLE_PASSPHRASE",
        help="读取 bundle 密码的环境变量名（默认 PROD_SSH_BUNDLE_PASSPHRASE）",
    )
    return parser.parse_args()


# 与现有容器存储保持同版，仅补齐原生 systemd 构建能力；禁止降级运行时。
PODMAN_SOURCE_COMMIT = "8303f2e25b675ea7f82099d615c60969aec15870"
PODMAN_SOURCE_ARCHIVE_SHA256 = "7a44bab607444fa6e98398feb9385fa5fc852c59efb01f7d9d7ce3ee0b7b402e"
PODMAN_VERSION = "6.1.1"
PODMAN_BUILD_TAGS = (
    "seccomp selinux systemd containers_image_openpgp "
    "exclude_graphdriver_btrfs exclude_graphdriver_devicemapper"
)


def register_runtime_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "prod-hosted-bootstrap", help="显式授权的同版原生 Podman 能力修复（不部署业务）"
    )
    parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    parser.add_argument("--host-id", default="")
    parser.add_argument("--bootstrap-user", default="")
    parser.add_argument("--bootstrap-key-file", default="")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare-secret-directories", action="store_true",
                         help="仅准备仓外长期秘密输入目录，不生成密钥、不上传或启用服务")
    actions.add_argument("--confirm-runtime-install", action="store_true")
    actions.add_argument("--confirm-lock-migration", action="store_true",
                         help="迁移已确认仅含 rehearsal 容器的 musl 共享锁，保留所有数据卷")
    actions.add_argument("--verify-health-scheduler", action="store_true",
                         help="在平面账号以既有镜像验证原生 timer；只清理本次探针容器")


# 长期输入仓与可重建部署 workspace 分离；不改变现有 consumer 的显式凭据引用。
SECRET_INPUT_ROOT = Path.home() / "Deployments" / "quwoquan-secrets"
SECRET_INPUT_PURPOSES = (
    "user-cohort", "providers/sms", "mtls/user-to-integration",
    "mtls/integration-server", "mtls/trust-roots",
    "signing/app-runtime", "signing/graphql-read-registry",
    "signing/assistant-skill-package", "app-signing/android", "app-signing/ios",
    "dns", "tls/public", "observability", "backup",
)


def _runtime_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if key.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}


def _runtime_ssh(account: str, host: str, key: Path) -> list[str]:
    """只接受当前用户的受限常规私钥；错误不携带私钥路径或内容。"""
    try:
        info = key.lstat()
    except OSError as error:
        raise ValueError("RUNTIME_SSH_KEY_UNAVAILABLE") from error
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) not in {0o400, 0o600} or info.st_nlink != 1):
        raise ValueError("RUNTIME_SSH_KEY_UNSAFE")
    return ["ssh", "-F", "/dev/null", "-i", str(key), "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=12",
            "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3", f"{account}@{host}"]


def _run_plane_script(placement: Any, script: str, *, timeout: int) -> subprocess.CompletedProcess[str]:
    ssh = _runtime_ssh(placement.account, placement.ssh_host, DEFAULT_KEY_DIR / placement.account)
    return subprocess.run([*ssh, "bash -s"], input=script, text=True, capture_output=True,
                          env=_runtime_environment(), timeout=timeout)


def _check_secret_directory(path: Path, *, private: bool) -> None:
    if path.is_symlink():
        raise ValueError(f"secret directory must not traverse symlink: {path}")
    if not path.exists():
        return
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"secret path is not a directory: {path}")
    mode = stat.S_IMODE(info.st_mode)
    if private:
        if info.st_uid != os.getuid() or mode != 0o700:
            raise ValueError(f"existing secret directory requires owner-only 0700: {path}")
    elif info.st_uid not in {0, os.getuid()} or mode & 0o022:
        # 系统受保护的 sticky 临时根不允许替换他人目录；普通可写祖先拒绝。
        if not (info.st_uid == 0 and mode & stat.S_ISVTX):
            raise ValueError(f"secret directory ancestor has unsafe owner or permissions: {path}")


def _secret_directory_tree(root: Path, scopes: tuple[str, ...]) -> set[Path]:
    directories = {root}
    for scope in scopes:
        for purpose in SECRET_INPUT_PURPOSES:
            leaf = root / scope / purpose
            directories.add(leaf)
            directories.update(parent for parent in leaf.parents if parent == root or root in parent.parents)
    return directories


def _prepare_secret_directories() -> dict[str, Any]:
    """先完整校验再创建空目录；不搬动、不覆盖任何既有秘密。"""
    from quwoquan_ops.cli.lib.output_paths import deployment_work_root, output_root

    root = SECRET_INPUT_ROOT
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("secret input root must be an absolute canonical path")
    if not root.parent.is_dir():
        raise ValueError("secret input parent directory is unavailable")
    protected = (ROOT.resolve(), output_root().resolve(), deployment_work_root("prod-hosted").parent.resolve())
    resolved = root.resolve()
    if any(resolved == other or other in resolved.parents or resolved in other.parents for other in protected):
        raise ValueError("secret input root must not overlap source, output or deployment workspace")
    scopes = ("alpha", "beta", "gamma", "prod/prevalidate", "prod/formal")
    directories = _secret_directory_tree(root, scopes)
    # 根的祖先也禁止 symlink；既有不安全路径不自动 chmod，避免影响其他用途。
    for path in directories | set(root.parents):
        _check_secret_directory(path, private=path in directories)
    for path in sorted(directories, key=lambda item: len(item.parts)):
        # 重读祖先，防止两次调用间发生的路径替换被当成合法目录复用。
        for parent in path.parents:
            _check_secret_directory(parent, private=parent in directories)
        path.mkdir(mode=0o700, exist_ok=True)
        _check_secret_directory(path, private=True)
    return {"exitCode": 0, "summary": "secret input directories prepared; no credentials generated or activated",
            "secretInputRoot": str(root), "scopes": list(scopes), "purposes": list(SECRET_INPUT_PURPOSES),
            "directoryMode": "0700", "requiredSecretFileMode": "0600", "consumerBinding": "not-configured",
            "credentialsReady": False,
            "releaseEligibility": "GATE_BLOCK"}


def _native_runtime_script(build_root: str, source_digest: str) -> str:
    root = shlex.quote(build_root)
    return f"""set -euo pipefail
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
cd {root}
printf '%s  source.tar.gz\\n' {shlex.quote(source_digest)} | sha256sum -c -
test \"$(uname -m)\" = x86_64
test \"$(/usr/local/bin/podman --version)\" = 'podman version {PODMAN_VERSION}'
# 不执行 dnf upgrade，不替换 Docker/Caddy 或修改其单元。
sudo -n dnf -y --setopt=install_weak_deps=False install golang-1.25.9 gcc make pkgconf-pkg-config systemd-devel libseccomp-devel
mkdir -p source cache
tar -xzf source.tar.gz -C source --strip-components=1
cd source
test -f vendor/modules.txt
# 单核配额与 2 GiB 上限保留共存应用余量；超时失败不替换旧二进制。
sudo -n systemd-run --wait --pipe --collect --unit=quwoquan-podman-build \\
  --uid=\"$(id -un)\" --working-directory=\"$PWD\" \\
  --property=CPUQuota=100% --property=MemoryMax=2G --property=RuntimeMaxSec=1800 \\
  --setenv=HOME=\"$HOME\" --setenv=GOCACHE={root}/cache --setenv=GOMAXPROCS=2 \\
  --setenv=CGO_ENABLED=1 --setenv=GOTOOLCHAIN=local \\
  go build -mod=vendor -p=2 -tags {shlex.quote(PODMAN_BUILD_TAGS)} \\
  -ldflags '-X go.podman.io/podman/v6/libpod/define.gitCommit={PODMAN_SOURCE_COMMIT}' \\
  -o ../podman ./cmd/podman
cd ..
./podman --version
go version -m ./podman
test \"$(./podman --version)\" = 'podman version {PODMAN_VERSION}'
case \"$(go version -m ./podman)\" in *-tags=*systemd*) ;; *) exit 2 ;; esac
sha256sum podman
{_native_install_script()}
/usr/local/bin/podman --version
printf 'runtime_install=completed; health_scheduler=requires-live-readback\\n'
"""


def _native_install_script() -> str:
    """封存不可变文件后仅原子切换链接，不截断任何运行中的 inode。"""
    return f"""sudo -n python3 - "$PWD/podman" <<'PY'
import fcntl, os, pathlib, shutil, stat, sys, tempfile
runtime = pathlib.Path('/usr/local/lib/quwoquan-runtime/{PODMAN_VERSION}-systemd')
current = pathlib.Path('/usr/local/bin/podman')

def trusted(path, directory=False):
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or info.st_uid != 0 or info.st_mode & 0o022:
        raise SystemExit('RUNTIME_INSTALL_UNSAFE_PATH')
    if not directory and (info.st_nlink != 1 or not info.st_mode & 0o100):
        raise SystemExit('RUNTIME_INSTALL_UNSAFE_BINARY')

for parent in reversed(runtime.parents):
    if not parent.exists():
        parent.mkdir(mode=0o755)
    trusted(parent, directory=True)
for parent in current.parents:
    trusted(parent, directory=True)
if not runtime.exists():
    runtime.mkdir(mode=0o755)
trusted(runtime, directory=True)
lockfd = os.open(runtime / '.install.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
lockinfo = os.fstat(lockfd)
if not stat.S_ISREG(lockinfo.st_mode) or lockinfo.st_uid != 0 or lockinfo.st_nlink != 1 or lockinfo.st_mode & 0o077:
    raise SystemExit('RUNTIME_INSTALL_UNSAFE_LOCK')
fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
candidate = pathlib.Path(sys.argv[1])
if not stat.S_ISREG(candidate.lstat().st_mode):
    raise SystemExit('RUNTIME_INSTALL_UNSAFE_SOURCE')

def seal(source, target):
    if target.exists() or target.is_symlink():
        trusted(target)
        if source.read_bytes() != target.read_bytes():
            raise SystemExit('RUNTIME_BINARY_DRIFT')
        return
    fd, temporary = tempfile.mkstemp(prefix='.install-', dir=runtime)
    try:
        with os.fdopen(fd, 'wb') as output, source.open('rb') as input_file:
            shutil.copyfileobj(input_file, output)
            os.fchmod(output.fileno(), 0o755)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, target, follow_symlinks=False)
    finally:
        os.unlink(temporary)

binary = runtime / 'podman'
previous = runtime / 'previous-podman'
if current.is_symlink():
    if current.lstat().st_uid != 0 or current.readlink() != binary:
        raise SystemExit('RUNTIME_INSTALL_UNEXPECTED_LINK')
    trusted(binary)
    trusted(previous)
    seal(candidate, binary)
else:
    trusted(current)
    seal(current, previous)
    seal(candidate, binary)
    # 临时目录独占，避免复用失败重试留下的公共链接名。
    with tempfile.TemporaryDirectory(prefix='.qwq-runtime-', dir=current.parent) as temporary:
        link = pathlib.Path(temporary) / 'podman'
        link.symlink_to(binary)
        os.replace(link, current)
PY"""


def _native_scheduler_script(image: str, name: str) -> str:
    """自动探针至少执行两次才成功；不手工执行任何 healthcheck run。"""
    return f"""set -euo pipefail
name={shlex.quote(name)}
image={shlex.quote(image)}
timeout -k 2 10 podman image exists \"$image\"
# 不删除同名既有对象；只清理由本次创建并记录 ID 的容器。
container_id=''
probe_dir=$(mktemp -d)
cleanup() {{
  local first=$? cleanup_code=0
  trap - EXIT
  if ! [[ "$container_id" =~ ^[0-9a-f]{{64}}$ ]] && test -f "$probe_dir/cid"; then container_id=$(<"$probe_dir/cid"); fi
  if [[ "$container_id" =~ ^[0-9a-f]{{64}}$ ]]; then
    timeout -k 2 15 podman rm -f "$container_id" >/dev/null || cleanup_code=$?
  elif test -n "$container_id"; then cleanup_code=2
  fi
  rm -rf -- "$probe_dir" || cleanup_code=$?
  if test "$cleanup_code" -ne 0; then printf 'RUNTIME_PROBE_CLEANUP_FAILED\\n' >&2; fi
  if test "$first" -ne 0; then exit "$first"; fi
  exit "$cleanup_code"
}}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
container_id=$(timeout -k 5 20 podman create --pull=never --name "$name" --cidfile "$probe_dir/cid" \\
 --label quwoquan.runtime-probe=true --network none --log-driver=k8s-file \\
 --memory=32m --pids-limit=64 --health-cmd='test -r /etc/os-release' \\
 --health-interval=2s --health-retries=3 --health-timeout=1s --stop-signal=SIGKILL "$image" sleep 120)
[[ "$container_id" =~ ^[0-9a-f]{{64}}$ ]] || {{ printf 'RUNTIME_PROBE_ID_INVALID\\n' >&2; exit 2; }}
timeout -k 5 20 podman start "$container_id" >/dev/null
export PROBE_CONTAINER_ID="$container_id"
timeout -k 2 85 python3 - <<'PY'
import json, os, re, subprocess, time
cid = os.environ['PROBE_CONTAINER_ID']
for _ in range(35):
    raw = subprocess.check_output(['podman', 'inspect', cid], timeout=5)
    container = json.loads(raw)[0]
    if container.get('Id') != cid:
        raise SystemExit('RUNTIME_PROBE_IDENTITY_MISMATCH')
    state = container['State']
    health = state.get('Health') or state.get('Healthcheck') or {{}}
    logs = health.get('Log') or []
    successful = {{entry.get('Start') for entry in logs if entry.get('ExitCode') == 0 and entry.get('Start')}}
    timers = subprocess.check_output(['systemctl', '--user', 'list-timers', '--all', '--no-pager'], timeout=5).decode()
    if state.get('OOMKilled') is not False or state.get('Status') != 'running':
        raise SystemExit('RUNTIME_PROBE_EXITED')
    native_timer = any(re.fullmatch(re.escape(cid) + r'(?:-[0-9a-f]+)?\\.timer', unit) for unit in timers.split())
    if health.get('Status') == 'healthy' and len(successful) >= 2 and native_timer:
        print(json.dumps({{'status': 'passed', 'automaticProbeCount': len(successful), 'nativeTimer': True, 'oomKilled': False}}))
        break
    time.sleep(2)
else:
    raise SystemExit('RUNTIME_HEALTH_SCHEDULER_UNAVAILABLE')
PY
"""


def _verify_native_scheduler(host_id: str) -> dict[str, Any]:
    from quwoquan_ops.cli.prod.prod_hosted_topology import resolve_plan

    access = _load_yaml(ACCESS_MANIFEST)
    placement = resolve_plan(access, instance="prevalidate", planes=["service"], host_ids=[host_id])[0]
    image = access["prevalidation"]["isolatedData"]["images"]["redis"]
    script = _native_scheduler_script(image, "quwoquan-runtime-probe-" + _utc_stamp().lower())
    result = _run_plane_script(placement, script, timeout=200)
    try:
        probe = json.loads(result.stdout.strip())
        passed = (result.returncode == 0 and probe.get("status") == "passed"
                  and type(probe.get("automaticProbeCount")) is int and probe["automaticProbeCount"] >= 2
                  and probe.get("nativeTimer") is True and probe.get("oomKilled") is False)
    except (ValueError, AttributeError):
        passed = False
    return {"exitCode": 0 if passed else 2,
            "summary": "native health scheduler verified" if passed else "GATE_BLOCK native health scheduler failed",
            "details": [result.stdout.strip(), result.stderr.strip()],
            "releaseEligibility": "GATE_BLOCK"}


def _native_lock_migration_script(project: str) -> str:
    """生成可独立校验的受限迁移，不依赖本机可变环境。"""
    return f"""set -euo pipefail
export EXPECTED_PROJECT={shlex.quote(project)}
python3 - <<'PY'
import fcntl, json, os, pathlib, re, shutil, stat, subprocess
uid = os.getuid()
root = pathlib.Path.home() / '.cache/quwoquan-runtime-migration'
config = pathlib.Path.home() / '.config/containers/containers.conf.d/90-quwoquan-native.conf'
completed = root / 'native-locks-completed'
content = '[containers]\\nlog_driver = "k8s-file"\\n'
marker = 'native locks verified; persistent volumes preserved\\n'

def safe_path(path, *, directory=False, optional=False, private=True):
    for ancestor in reversed(path.parents):
        if ancestor.is_symlink():
            raise SystemExit('RUNTIME_MIGRATION_UNSAFE_PATH')
        if ancestor.exists():
            info = ancestor.lstat()
            writable = info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, uid) or writable:
                raise SystemExit('RUNTIME_MIGRATION_UNSAFE_ANCESTOR')
    if optional and not path.exists() and not path.is_symlink():
        return
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    unsafe_mode = info.st_mode & (0o077 if private else 0o022)
    if not valid or info.st_uid != uid or unsafe_mode or (not directory and info.st_nlink != 1):
        raise SystemExit('RUNTIME_MIGRATION_UNSAFE_PATH')

def inventory(binary, stopped=False):
    rows = json.loads(subprocess.check_output([str(binary), 'ps', '-a', '--format', 'json'], timeout=20))
    if not isinstance(rows, list):
        raise SystemExit('RUNTIME_MIGRATION_INVALID_INVENTORY')
    project = os.environ['EXPECTED_PROJECT']
    for row in rows:
        names = row.get('Names') or []
        if isinstance(names, str):
            names = [names]
        labels = row.get('Labels') or {{}}
        owned = (labels.get('io.podman.compose.project') == project or labels.get('com.docker.compose.project') == project)
        probe = labels.get('quwoquan.runtime-probe') == 'true'
        if not names or not all(isinstance(n, str) and ((owned and n.startswith(project + '-')) or
                (probe and n.startswith('quwoquan-runtime-probe-'))) for n in names):
            raise SystemExit('RUNTIME_MIGRATION_FOREIGN_CONTAINER')
        if not re.fullmatch('[0-9a-f]{{64}}', row.get('Id', '')) or row.get('State') not in ('running', 'created', 'exited', 'stopped'):
            raise SystemExit('RUNTIME_MIGRATION_INVALID_INVENTORY')
        if stopped and row['State'] == 'running':
            raise SystemExit('RUNTIME_MIGRATION_CONTAINERS_STILL_RUNNING')
    return rows

def create_once(path, value):
    safe_path(path, optional=True)
    if path.exists():
        if path.read_text() != value:
            raise SystemExit('RUNTIME_CONFIGURATION_DRIFT')
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    safe_path(path.parent, directory=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(value)
        output.flush()
        os.fsync(output.fileno())

def native_info():
    return subprocess.run(['timeout', '-k', '2', '5', 'podman', 'info', '--format',
        '{{{{.Host.CgroupManager}}}} {{{{.Host.CgroupsVersion}}}}'], capture_output=True, timeout=10)

safe_path(root, directory=True, optional=True)
for path, expected in ((config, content), (completed, marker)):
    safe_path(path, optional=True)
    if path.exists() and path.read_text() != expected:
        raise SystemExit('RUNTIME_CONFIGURATION_DRIFT')
# 标记不赋予 authority；两个分支都先验证完整 inventory，再写配置与完成事实。
native = native_info()
if native.returncode == 0:
    if native.stdout.strip() != b'systemd v2':
        raise SystemExit('RUNTIME_MIGRATION_NATIVE_READBACK_FAILED')
    inventory('podman', stopped=True)
else:
    if native.returncode not in (124, 137):
        raise SystemExit('RUNTIME_MIGRATION_UNEXPECTED_FAILURE: exit=' + str(native.returncode))
    if completed.exists():
        raise SystemExit('RUNTIME_MIGRATION_STALE_COMPLETION')
    pausefile = pathlib.Path('/run/user') / str(uid) / 'libpod/tmp/pause.pid'
    safe_path(pausefile, private=False)
    pid = int(pausefile.read_text().strip())
    process = pathlib.Path('/proc') / str(pid)
    if pid <= 1 or process.stat().st_uid != uid:
        raise SystemExit('RUNTIME_MIGRATION_NAMESPACE_OWNER_MISMATCH')
    old = process / 'exe'
    executable = old.readlink()
    if not executable.name.startswith('podman') or old.stat().st_uid not in (0, uid) or old.stat().st_mode & 0o022:
        raise SystemExit('RUNTIME_MIGRATION_EXECUTABLE_MISMATCH')
    if subprocess.check_output([str(old), '--version'], timeout=10).strip() != b'podman version 6.1.1':
        raise SystemExit('RUNTIME_MIGRATION_VERSION_MISMATCH')
    rows = inventory(old)
    lock = pathlib.Path('/dev/shm') / ('libpod_rootless_lock_' + str(uid))
    safe_path(lock)
    lock_backup = lock.with_name(lock.name + '.musl-backup')
    if lock_backup.exists() or lock_backup.is_symlink():
        raise SystemExit('RUNTIME_MIGRATION_BACKUP_ALREADY_EXISTS')
    for process in pathlib.Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != uid:
                continue
            executable = (process / 'exe').readlink().name
        except FileNotFoundError:
            continue
        if executable.startswith('podman') and int(process.name) != pid:
            raise SystemExit('RUNTIME_MIGRATION_ACTIVE_WRITER')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = root / 'podman-static-6.1.1'
    safe_path(backup, optional=True)
    if not backup.exists():
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700)
        with os.fdopen(fd, 'wb') as output, old.open('rb') as source:
            shutil.copyfileobj(source, output)
    if backup.read_bytes() != old.read_bytes():
        raise SystemExit('RUNTIME_MIGRATION_BINARY_BACKUP_DRIFT')
    # 不使用覆盖式 rename；link 仅在备份不存在时成功，之后才移走原锁名。
    fd = os.open(root / 'migration.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    safe_path(root / 'migration.lock')
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    subprocess.run(['systemctl', '--user', 'stop', 'podman.socket', 'podman.service'], check=True, timeout=30)
    running = [row['Id'] for row in rows if row['State'] == 'running']
    if running:
        subprocess.run([str(backup), 'stop', '--time', '20', *running], check=True, timeout=120)
    inventory(backup, stopped=True)
    safe_path(lock)
    os.link(lock, lock_backup, follow_symlinks=False)
    lock.unlink()
    subprocess.run(['podman', 'system', 'renumber'], check=True, timeout=30)
    native = native_info()
    if native.returncode != 0 or native.stdout.strip() != b'systemd v2':
        raise SystemExit('RUNTIME_MIGRATION_NATIVE_READBACK_FAILED')
    inventory('podman', stopped=True)
create_once(config, content)
subprocess.run(['systemctl', '--user', 'start', 'podman.socket'], check=True, timeout=15)
subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'podman.socket'], check=True, timeout=10)
create_once(completed, marker)
print('native_lock_migration=completed; persistent_volumes=preserved')
PY
"""


def _migrate_native_locks(host_id: str) -> dict[str, Any]:
    """仅平面账号内的 rehearsal 停机锁迁移，不触碰磁盘数据。"""
    from quwoquan_ops.cli.prod.prod_hosted_topology import resolve_plan

    placements = resolve_plan(_load_yaml(ACCESS_MANIFEST), instance="prevalidate", host_ids=[host_id])
    evidence = []
    for placement in placements:
        script = _native_lock_migration_script(placement.project)
        result = _run_plane_script(placement, script, timeout=420)
        evidence.append({"plane": placement.plane, "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode != 0:
            return {"exitCode": 2, "summary": "GATE_BLOCK native lock migration failed", "details": evidence}
    return {"exitCode": 0, "summary": "native locks migrated; containers remain stopped", "details": evidence,
            "releaseEligibility": "GATE_BLOCK"}


def _runtime_failure(error: Exception) -> dict[str, Any]:
    """subprocess 异常默认含完整 argv；只返回类型和状态，不泄漏 SSH 私钥位置。"""
    if isinstance(error, subprocess.TimeoutExpired):
        reason = "RUNTIME_COMMAND_TIMEOUT"
    elif isinstance(error, subprocess.CalledProcessError):
        reason = f"RUNTIME_COMMAND_FAILED: exit={error.returncode}"
    elif isinstance(error, OSError):
        reason = f"RUNTIME_OS_ERROR: errno={error.errno}"
    else:
        reason = str(error)
    return {"exitCode": 2, "summary": f"GATE_BLOCK native runtime bootstrap: {reason}",
            "releaseEligibility": "GATE_BLOCK"}


def command_runtime_bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    """明确动作独立执行；安装/目录存在均不授予发布或 credentials-ready 资格。"""
    actions = [name for name in ("prepare_secret_directories", "confirm_lock_migration",
               "verify_health_scheduler", "confirm_runtime_install") if getattr(args, name, False)]
    if len(actions) != 1:
        return {"exitCode": 2, "summary": "GATE_BLOCK requires one action and explicit confirmation"}
    action = actions[0]
    if action != "prepare_secret_directories" and not getattr(args, "host_id", ""):
        return {"exitCode": 2, "summary": "GATE_BLOCK remote bootstrap requires a declared host-id"}
    try:
        if action == "prepare_secret_directories":
            return _prepare_secret_directories()
        if action == "confirm_lock_migration":
            return _migrate_native_locks(args.host_id)
        if action == "verify_health_scheduler":
            return _verify_native_scheduler(args.host_id)
        return _install_native_runtime(args)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        return _runtime_failure(error)


def _install_native_runtime(args: argparse.Namespace) -> dict[str, Any]:
    from quwoquan_ops.cli.prod.prod_hosted_topology import resolve_plan

    try:
        plan = resolve_plan(_load_yaml(ACCESS_MANIFEST), instance="prevalidate", host_ids=[args.host_id])
    except (ValueError, RuntimeError) as error:
        return {"exitCode": 2, "summary": f"GATE_BLOCK invalid bootstrap placement: {error}"}
    hosts = {replica.ssh_host for replica in plan}
    if len(hosts) != 1:
        return {"exitCode": 2, "summary": "GATE_BLOCK bootstrap requires one declared host"}
    host = hosts.pop()
    key = Path(args.bootstrap_key_file).expanduser()
    ssh = _runtime_ssh(args.bootstrap_user, host, key)
    if not shutil.which("gh"):
        return {"exitCode": 2, "summary": "GATE_BLOCK GitHub source client missing"}
    env = _runtime_environment()
    local_root = deployment_target_path("prod-hosted", "runtime-bootstrap")
    local_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    archive = local_root / f"podman-{PODMAN_SOURCE_COMMIT}.tar.gz"
    try:
        if not archive.exists():
            partial = archive.with_suffix(".partial")
            with partial.open("wb") as output:
                subprocess.run(["gh", "api", f"repos/podman-container-tools/podman/tarball/{PODMAN_SOURCE_COMMIT}"],
                               stdout=output, check=True, timeout=180, env=env)
            partial.replace(archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != PODMAN_SOURCE_ARCHIVE_SHA256:
            raise ValueError("Podman source archive differs from the pinned verified bytes")
        # 由管理员 HOME 决定受限工作目录，不把路径变为任意远端命令。
        home = subprocess.run([*ssh, "printf '%s' \"$HOME\""], env=env,
                              capture_output=True, text=True, check=True, timeout=30).stdout
        if not home.startswith("/home/") or "\n" in home:
            raise ValueError("bootstrap requires a non-root administrator home")
        remote_root = f"{home}/.cache/quwoquan-runtime/{PODMAN_SOURCE_COMMIT}"
        with archive.open("rb") as source:
            subprocess.run([*ssh, f"umask 077; mkdir -p {shlex.quote(remote_root)} && cat > {shlex.quote(remote_root + '/source.tar.gz')}"],
                           stdin=source, check=True, timeout=180, env=env)
        subprocess.run([*ssh, "bash -s"], input=_native_runtime_script(remote_root, digest),
                       text=True, check=True, timeout=2100, env=env)
    except (subprocess.SubprocessError, ValueError, OSError) as error:
        return _runtime_failure(error)
    return {"exitCode": 0, "summary": "native Podman installed; live health scheduling not yet verified",
            "sourceCommit": PODMAN_SOURCE_COMMIT, "sourceArchiveDigest": "sha256:" + digest,
            "runtimeHealth": "requires-live-readback", "releaseEligibility": "GATE_BLOCK"}


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
