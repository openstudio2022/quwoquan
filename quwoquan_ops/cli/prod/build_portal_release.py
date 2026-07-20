#!/usr/bin/env python3
"""构建运维运营 Portal 的不可变生产静态包。

产物落 `QWQ_OUTPUT_ROOT/env/prod/release/ops-portal/<version>/dist`，并把
`current` 符号链接指向该版本；`render_prod_plane_stack.py` 渲染 service plane
时会将 `current/dist` 复制进 `runtime/portal` 随发布同步到远端。

生产 VITE 变量为同源部署口径（Portal 与控制面 API 同在 ops 域名下），
OIDC issuer/client 必须显式传入，禁止把 dev 值悄悄带上生产。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
PORTAL_DIR = ROOT / "quwoquan_ops" / "portal"
sys.path.insert(0, str(ROOT / "quwoquan_ops" / "cli"))

from lib.output_paths import output_root as resolve_output_root  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="release 版本号（与 service release 对齐，例如 1.20260719.123）")
    parser.add_argument("--ops-base-url", default="https://ops.quwoquan.com", help="Portal 同源控制面基地址")
    parser.add_argument("--content-base-url", default="https://api.quwoquan.com", help="content-service 公网基地址")
    parser.add_argument("--entity-base-url", default="https://api.quwoquan.com", help="entity-service 公网基地址")
    parser.add_argument("--oidc-issuer", required=True, help="生产 OIDC issuer")
    parser.add_argument("--oidc-client-id", required=True, help="生产 OIDC client id")
    parser.add_argument("--oidc-audience", required=True, help="生产控制面 API audience")
    parser.add_argument("--oidc-scope", required=True, help="IdP 登记的 Portal 最小 scope 集")
    parser.add_argument("--skip-install", action="store_true", help="跳过 npm install（CI 已缓存依赖时使用）")
    args = parser.parse_args()

    version = args.version.strip()
    if not version:
        raise SystemExit("FAIL: --version is required")
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

    if not args.skip_install:
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=PORTAL_DIR, check=True)

    env = dict(os.environ)
    env.update(
        {
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

    build_dist = (
        resolve_output_root() / "env" / "repo" / "local" / "ops-portal" / "process" / "dist"
    )
    if not build_dist.is_dir():
        raise SystemExit(f"FAIL: vite build output missing: {build_dist}")

    release_root = resolve_output_root() / "env" / "prod" / "release" / "ops-portal"
    version_dir = release_root / version
    if version_dir.exists():
        raise SystemExit(f"FAIL: release version already exists (immutable): {version_dir}")
    version_dir.mkdir(parents=True)
    shutil.copytree(build_dist, version_dir / "dist")

    manifest = {
        "version": version,
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "opsBaseUrl": args.ops_base_url,
        "contentBaseUrl": args.content_base_url,
        "entityBaseUrl": args.entity_base_url,
        "oidcIssuer": args.oidc_issuer,
        # client id 非机密（公开 SPA client），记录用于发布追溯。
        "oidcClientId": args.oidc_client_id,
    }
    (version_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    current = release_root / "current"
    if current.is_symlink() or current.exists():
        if current.is_dir() and not current.is_symlink():
            shutil.rmtree(current)
        else:
            current.unlink()
    current.symlink_to(version_dir.name)

    print(json.dumps({"releaseDir": str(version_dir), "current": str(current)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
