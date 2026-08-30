#!/usr/bin/env python3
"""构建运维运营 Portal 的不可变生产静态包。

产物落 `QWQ_DEPLOY_WORK_ROOT/prod-hosted/packages/ops-portal/<digest>/dist`，并把
`current` 符号链接指向该包的内容摘要；`render_prod_plane_stack.py` 渲染 service plane
时会将 `current/dist` 复制进 `runtime/portal` 随发布同步到远端。

生产 VITE 变量为同源部署口径（Portal 与控制面 API 同在 ops 域名下），
OIDC issuer/client 必须显式传入，禁止把 dev 值悄悄带上生产。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
PORTAL_DIR = ROOT / "quwoquan_ops" / "portal"
sys.path.insert(0, str(ROOT / "quwoquan_ops" / "cli"))

from lib.output_paths import (  # noqa: E402
    deployment_target_for_env,
    deployment_target_path,
    deployment_work_root,
    portal_deployment_package_dir,
    remove_deployment_tree,
)
from lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ops-base-url", default="", help="必须等于 topology 的 productOps role")
    parser.add_argument("--content-base-url", default="", help="必须等于 topology 的 api role")
    parser.add_argument("--entity-base-url", default="", help="必须等于 topology 的 api role")
    parser.add_argument("--oidc-issuer", required=True, help="生产 OIDC issuer")
    parser.add_argument("--oidc-client-id", required=True, help="生产 OIDC client id")
    parser.add_argument("--oidc-audience", required=True, help="生产控制面 API audience")
    parser.add_argument("--oidc-scope", required=True, help="IdP 登记的 Portal 最小 scope 集")
    parser.add_argument("--skip-install", action="store_true", help="跳过 npm install（CI 已缓存依赖时使用）")
    parser.add_argument("--target", default="", help="prod deployment target（默认 prod-hosted）")
    args = parser.parse_args()

    issuer = args.oidc_issuer.strip().rstrip("/")
    parsed_issuer = urlparse(issuer)
    if parsed_issuer.scheme != "https" or not parsed_issuer.netloc:
        raise SystemExit("FAIL: --oidc-issuer must be an absolute HTTPS issuer")
    client_id = args.oidc_client_id.strip()
    audience = args.oidc_audience.strip()
    scopes = args.oidc_scope.split()
    if not client_id or not audience:
        raise SystemExit("FAIL: --oidc-client-id and --oidc-audience are required")
    if "openid" not in scopes or len(scopes) < 2:
        raise SystemExit("FAIL: --oidc-scope must include openid and operator scopes")
    try:
        target_name = deployment_target_for_env("prod", target=args.target)
    except ValueError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    public_bases = get_target(
        load_environment_topology(),
        target_name,
    )["publicBases"]
    role_values = {
        "ops_base_url": str(public_bases["productOps"]),
        "content_base_url": str(public_bases["api"]),
        "entity_base_url": str(public_bases["api"]),
    }
    for attribute, canonical in role_values.items():
        supplied = str(getattr(args, attribute) or "").rstrip("/")
        if supplied and supplied != canonical.rstrip("/"):
            raise SystemExit(
                f"FAIL: --{attribute.replace('_', '-')} must equal topology projection"
            )
        setattr(args, attribute, canonical)

    if not args.skip_install:
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=PORTAL_DIR, check=True)

    env = dict(os.environ)
    env.update(
        {
            "QWQ_DEPLOY_WORK_ROOT": str(
                deployment_work_root(target_name).parent
            ),
            "QWQ_DEPLOY_TARGET": target_name,
            "VITE_PRODUCT_OPS_BASE_URL": args.ops_base_url,
            "VITE_PLATFORM_OPS_BASE_URL": args.ops_base_url,
            "VITE_CONTENT_SERVICE_BASE_URL": args.content_base_url,
            "VITE_ENTITY_SERVICE_BASE_URL": args.entity_base_url,
            "VITE_OIDC_ISSUER": issuer,
            "VITE_OIDC_CLIENT_ID": client_id,
            "VITE_OIDC_AUDIENCE": audience,
            "VITE_OIDC_SCOPE": " ".join(scopes),
            "VITE_OIDC_REDIRECT_URI": args.ops_base_url.rstrip("/") + "/",
        }
    )
    subprocess.run(["npm", "run", "build"], cwd=PORTAL_DIR, check=True, env=env)

    build_dist = deployment_target_path(target_name, "build", "ops-portal")
    if not build_dist.is_dir():
        raise SystemExit(f"FAIL: vite build output missing: {build_dist}")

    package_digest = _sha256_tree(build_dist)
    package_directory = package_digest.removeprefix("sha256:")
    source_git_sha = _git_output("rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", source_git_sha) is None:
        raise SystemExit("FAIL: source Git SHA is not canonical")
    source_tree = _git_output("rev-parse", "HEAD^{tree}")
    if re.fullmatch(r"[0-9a-f]{40}", source_tree) is None:
        raise SystemExit("FAIL: source tree digest is not canonical")

    release_root = portal_deployment_package_dir("prod", target=target_name)
    package_dir = deployment_target_path(
        target_name,
        "packages",
        "ops-portal",
        package_directory,
    )
    if package_dir.exists():
        existing_dist = package_dir / "dist"
        if not existing_dist.is_dir() or _sha256_tree(existing_dist) != package_digest:
            raise SystemExit(
                f"FAIL: immutable package digest collision: {package_dir}"
            )
    else:
        package_dir.mkdir(parents=True)
        shutil.copytree(build_dist, package_dir / "dist")

    manifest = {
        "schema": "qwq.ops_portal_application",
        "packageDigest": package_digest,
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": "sha1:" + source_tree,
        "opsBaseUrl": args.ops_base_url,
        "contentBaseUrl": args.content_base_url,
        "entityBaseUrl": args.entity_base_url,
        "oidcIssuer": args.oidc_issuer,
        # client id 非机密（公开 SPA client），记录用于发布追溯。
        "oidcClientId": args.oidc_client_id,
    }
    manifest_path = package_dir / "manifest.json"
    encoded_manifest = json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if (
        manifest_path.exists()
        and manifest_path.read_text(encoding="utf-8") != encoded_manifest
    ):
        raise SystemExit(f"FAIL: immutable package manifest differs: {manifest_path}")
    manifest_path.write_text(encoded_manifest, encoding="utf-8")

    current = release_root / "current"
    if current.is_symlink() or current.exists():
        if current.is_dir() and not current.is_symlink():
            remove_deployment_tree(
                target_name,
                "packages",
                "ops-portal",
                "current",
            )
        else:
            current.unlink()
    current.symlink_to(package_dir.name)

    print(
        json.dumps(
            {
                "releaseDir": str(package_dir),
                "current": str(current),
                "packageDigest": package_digest,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_tree(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "FAIL: cannot resolve immutable source identity: "
            + (result.stderr.strip() or result.stdout.strip())
        )
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
