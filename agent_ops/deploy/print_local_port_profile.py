#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_ops.deploy.lib.port_manifest import load_port_manifest, profile_ports


ENV_EXPORTS = {
    "alpha-local": {
        "API_EDGE_PORT": "api-edge",
        "PRODUCT_OPS_PORT": "product-ops-edge",
        "MEDIA_EDGE_PORT": "media-edge",
        "MEDIA_ORIGIN_PORT": "media-origin",
    },
    "beta-local": {
        "GATEWAY_PORT": "api-edge",
        "PRODUCT_OPS_PORT": "product-ops-edge",
        "PLATFORM_OPS_PORT": "platform-ops-edge",
        "OPS_PORTAL_PORT": "ops-portal",
        "MEDIA_PORT": "media-edge",
        "MEDIA_ORIGIN_PORT": "media-origin",
        "ASSISTANT_PORT": "assistant-service",
        "CHAT_PORT": "chat-service",
    },
    "gamma-local": {
        "LOCAL_GAMMA_HTTP_PORT": "api-edge",
        "LOCAL_GAMMA_PRODUCT_OPS_PORT": "product-ops-edge",
        "LOCAL_GAMMA_PLATFORM_OPS_PORT": "platform-ops-edge",
        "LOCAL_GAMMA_MEDIA_EDGE_PORT": "media-edge",
        "LOCAL_GAMMA_MEDIA_ORIGIN_PORT": "media-origin",
        "LOCAL_GAMMA_CONTENT_PORT": "content-service",
        "LOCAL_GAMMA_CHAT_PORT": "chat-service",
        "LOCAL_GAMMA_USER_PORT": "user-service",
        "LOCAL_GAMMA_ASSISTANT_PORT": "assistant-service",
        "LOCAL_GAMMA_REC_MODEL_PORT": "rec-model-service",
        "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT": "product-ops-service",
        "LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT": "platform-ops-service",
        "LOCAL_GAMMA_POSTGRES_PORT": "postgres",
        "LOCAL_GAMMA_MONGO_PORT": "mongodb",
        "LOCAL_GAMMA_REDIS_PORT": "redis",
    },
    "prod-sim": {
        "PROD_SIM_GATEWAY_PORT": "api-edge",
        "PROD_SIM_MEDIA_EDGE_PORT": "media-edge",
        "PROD_SIM_MEDIA_ORIGIN_PORT": "media-origin",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument(
        "--format",
        choices=["json", "shell", "shell-defaults"],
        default="json",
    )
    args = parser.parse_args()

    manifest = load_port_manifest()
    ports = profile_ports(manifest, args.profile)
    export_map = ENV_EXPORTS.get(args.profile, {})
    payload = {
        "profile": args.profile,
        "ports": ports,
        "env": {env_name: ports[role_name] for env_name, role_name in export_map.items()},
    }

    if args.format == "shell":
        for env_name, value in payload["env"].items():
            print(f"export {env_name}={value}")
    elif args.format == "shell-defaults":
        for env_name, value in payload["env"].items():
            print(f': "${{{env_name}:={value}}}"')
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
