#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


ARTIFACT_NAME = "mainline-release-artifact"
DEFAULT_MIN_IMAGE_VERSION = "1.0.0"
DEFAULT_MAX_IMAGE_VERSION = "2.0.0"
RELEASE_SERVICES = (
    "seed-box",
    "content-service",
    "chat-service",
    "user-service",
    "integration-service",
    "notification-service",
    "circle-service",
    "recommendation-service",
    "product-ops-service",
    "platform-ops-service",
    "assistant-service",
    "tag-service",
    "entity-service",
)
DEPLOYED_SERVICES = (
    "rec-model-service",
    "content-service",
    "chat-service",
    "user-service",
    "assistant-service",
    "product-ops-service",
    "platform-ops-service",
    "tag-service",
    "entity-service",
    "integration-service",
    "notification-service",
    "realtime-gateway",
    "rtc-service",
)


SERVICE_TEMPLATES: dict[str, dict[str, Any]] = {
    "seed-box": {
        "service": {
            "name": "seed-box",
            "http": {
                "addr": ":8080",
            },
        },
    },
    "content-service": {
        "service": {
            "name": "content-service",
            "http": {
                "addr": ":18080",
            },
        },
        "mongo": {
            "uri": "",
            "database": "quwoquan_content",
            "collection": "posts",
        },
        "redis": {
            "rec": {
                "mode": "memory",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
            "general": {
                "mode": "memory",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
        },
        "rec_model_service": {
            "enabled": False,
            "url": "http://recommendation-service:8000",
            "timeout_ms": 80,
        },
        "experiments": {
            "rec_model_vs_rule": {
                "enabled": False,
            },
            "rec_scoring_weights": {
                "enabled": False,
            },
        },
    },
    "chat-service": {
        "service": {
            "name": "chat-service",
            "http": {
                "addr": ":18081",
            },
        },
        "mongodb": {
            "uri": "",
            "database": "quwoquan_chat",
        },
        "redis": {
            "realtime": {
                "mode": "standalone",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
            "general": {
                "mode": "standalone",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
            "reliable_task": {
                "mode": "standalone",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
        },
        "runtime": {
            "media": {
                "group_avatar_cdn_base_url": "",
                "group_avatar_local_media_root": "/tmp/chat-media",
            },
            "reliable_task": {
                "ready_index": {
                    "enabled": False,
                },
            },
        },
    },
    "user-service": {
        "service": {
            "name": "user-service",
                "http": {
                    "addr": ":18082",
                },
            },
            "postgres": {
                "dsn": "",
                "max_open_conns": 25,
                "max_idle_conns": 5,
                "conn_max_lifetime_minutes": 30,
        },
        "mongodb": {
                "uri": "",
            "database": "quwoquan_user",
        },
        "redis": {
            "general": {
                "mode": "standalone",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
            "realtime": {
                "mode": "standalone",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
        },
    },
    "integration-service": {
        "service": {
            "name": "integration-service",
            "http": {
                "addr": ":18086",
            },
        },
        "integration": {
            "location": {
                "provider": "baidu",
                "primary_provider": "baidu",
                "backup_provider": "amap",
                "timeout_ms": 1200,
                "nearby_default_radius_meters": 3000,
                "nearby_default_limit": 20,
                "search_default_limit": 20,
                "default_latitude": 30.6586,
                "default_longitude": 104.0648,
                "baidu_base_url": "https://api.map.baidu.com",
                "amap_base_url": "https://restapi.amap.com",
                "baidu_ak": "",
                "amap_key": "",
            },
        },
    },
    "circle-service": {
        "service": {
            "name": "circle-service",
            "http": {
                "addr": ":18084",
            },
        },
        "mongo": {
            "uri": "",
            "database": "quwoquan_circle",
        },
        "redis": {
            "general": {
                "mode": "standalone",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
        },
    },
    "recommendation-service": {
        "service": {
            "name": "recommendation-service",
            "http": {
                "addr": ":8000",
            },
        },
    },
    "product-ops-service": {
        "service": {
            "name": "product-ops-service",
            "http": {
                "addr": ":18086",
            },
        },
        "mongodb": {
            "uri": "",
            "database": "quwoquan_product_ops",
        },
        "redis": {
            "rec": {
                "mode": "standalone",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
            "general": {
                "mode": "standalone",
                "addr": "",
                "addrs": [],
                "tls": False,
            },
        },
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate mainline release manifest and versioned config snapshots.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--run-number", required=True, type=int)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--registry", default="ghcr.io")
    parser.add_argument("--image-version", default="")
    parser.add_argument("--config-version", default="")
    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def compute_versions(run_number: int) -> tuple[str, str]:
    stamp = dt.datetime.now(dt.timezone.utc)
    image_version = f"1.{stamp.strftime('%Y%m%d')}.{run_number}"
    config_version = f"v{stamp.strftime('%Y.%m.%d')}.{run_number}"
    return image_version, config_version


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def render_release_snapshot(service: str, config_version: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "config": {
            "version": config_version,
            "min_image_version": DEFAULT_MIN_IMAGE_VERSION,
            "max_image_version": DEFAULT_MAX_IMAGE_VERSION,
        },
    }
    template = SERVICE_TEMPLATES.get(service)
    if template:
        payload = deep_merge(payload, template)
    return payload


def dump_yaml_like(payload: dict[str, Any]) -> str:
    if yaml is not None:
        text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    else:  # pragma: no cover
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    return text if text.endswith("\n") else text + "\n"


def write_release_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml_like(payload), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def write_summary(
    path: Path,
    *,
    image_version: str,
    config_version: str,
    image_repositories: dict[str, str],
) -> None:
    text = "\n".join(
        [
            "## Mainline Release Artifact",
            "",
            f"- `image_version`: `{image_version}`",
            f"- `config_version`: `{config_version}`",
            "- `status`: `build-input`（全部 OCI digest 与 attestations 收齐后才可部署）",
            "",
            "### Required images",
            *[
                f"- `{service}`: `{repository}:{image_version}`"
                for service, repository in image_repositories.items()
            ],
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    image_version = args.image_version.strip()
    config_version = args.config_version.strip()
    if not image_version or not config_version:
        image_version, config_version = compute_versions(args.run_number)
    registry = args.registry.rstrip("/")
    repository = args.repository.strip("/")
    release_files: dict[str, str] = {}
    release_file_digests: dict[str, str] = {}
    for service in RELEASE_SERVICES:
        relative_path = Path("releases") / "config" / service / f"{config_version}.yaml"
        snapshot_path = output_dir / relative_path
        write_release_snapshot(
            snapshot_path,
            render_release_snapshot(service, config_version),
        )
        release_files[service] = relative_path.as_posix()
        release_file_digests[service] = sha256_file(snapshot_path)

    image_repositories = {
        service: (
            f"{registry}/{repository}/recommendation-service"
            if service == "rec-model-service"
            else f"{registry}/{repository}/{service}"
        )
        for service in DEPLOYED_SERVICES
    }

    manifest = {
        "schema": "mainline-release-artifact",
        "artifactName": ARTIFACT_NAME,
        "status": "build-input",
        "generatedAt": utc_now(),
        "source": {
            "gitSha": args.git_sha,
            "runNumber": args.run_number,
            "repository": args.repository,
        },
        "versions": {
            "imageVersion": image_version,
            "configVersion": config_version,
        },
        "requiredImages": list(DEPLOYED_SERVICES),
        "imageRepositories": image_repositories,
        "images": {},
        "releaseFiles": release_files,
        "releaseFileDigests": release_file_digests,
    }
    write_json(output_dir / "manifest.json", manifest)
    write_summary(
        output_dir / "summary.md",
        image_version=image_version,
        config_version=config_version,
        image_repositories=image_repositories,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
