"""生产公网域名解析与灰度路由块（从 render_prod_plane_stack.py 逐字搬移）。"""
from __future__ import annotations

import re

from quwoquan_ops.cli.lib.environment_topology import load_environment_topology

def _prod_public_hosts() -> dict[str, str]:
    """从环境拓扑真相源解析生产域名，禁止生产 Caddy 回退本地域名或 IP。"""
    from urllib.parse import urlparse

    topology = load_environment_topology()
    public_bases = (
        ((topology.get("targets") or {}).get("prod-hosted") or {}).get("publicBases")
        or {}
    )
    hosts: dict[str, str] = {}
    for key in (
        "api",
        "realtime",
        "rtc",
        "productOps",
        "publicWeb",
        "legal",
        "appDownload",
        "mediaAvatar",
        "mediaImage",
        "mediaUpload",
    ):
        host = urlparse(str(public_bases.get(key) or "")).hostname or ""
        if (
            not host
            or host.endswith((".test", ".example"))
            or re.fullmatch(r"\d+(?:\.\d+){3}", host)
        ):
            raise SystemExit(f"FAIL: prod-hosted publicBases.{key} must use a public DNS name")
        hosts[key] = host
    return hosts


def _render_gray_routing_block(rollout_stage: str) -> str:
    """Caddy is transport-only; API Edge owns stable/candidate allocation.

    Keep the function as a compatibility-free renderer seam while callers are
    migrated to the five-stage release transaction.  Returning an empty block
    is deliberate: client headers must never become a Caddy business router.
    """
    if rollout_stage not in {"canary", "5", "20", "50", "100"}:
        raise SystemExit(
            "FAIL: rollout policy received an unsupported stage "
            f"{rollout_stage!r}"
        )
    return ""
