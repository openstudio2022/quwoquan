#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import datetime as dt
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
    "circle-service",
    "recommendation-service",
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
            "url": "http://127.0.0.1:8000",
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


def write_summary(path: Path, *, image_version: str, config_version: str, seed_box_repo: str, recommendation_repo: str) -> None:
    text = "\n".join(
        [
            "## Mainline Release Artifact",
            "",
            f"- `image_version`: `{image_version}`",
            f"- `config_version`: `{config_version}`",
            f"- `seed-box`: `{seed_box_repo}:{image_version}`",
            f"- `recommendation-service`: `{recommendation_repo}:{image_version}`",
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
    seed_box_repo = f"{registry}/{repository}/seed-box"
    recommendation_repo = f"{registry}/{repository}/recommendation-service"

    release_files: dict[str, str] = {}
    for service in RELEASE_SERVICES:
        relative_path = Path("releases") / "config" / service / f"{config_version}.yaml"
        snapshot_path = output_dir / relative_path
        write_release_snapshot(
            snapshot_path,
            render_release_snapshot(service, config_version),
        )
        release_files[service] = relative_path.as_posix()

    manifest = {
        "schemaVersion": 1,
        "artifactName": ARTIFACT_NAME,
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
        "images": {
            "seedBox": {
                "repository": seed_box_repo,
                "tag": image_version,
                "ref": f"{seed_box_repo}:{image_version}",
            },
            "recommendationService": {
                "repository": recommendation_repo,
                "tag": image_version,
                "ref": f"{recommendation_repo}:{image_version}",
            },
        },
        "releaseFiles": release_files,
    }
    write_json(output_dir / "manifest.json", manifest)
    write_summary(
        output_dir / "summary.md",
        image_version=image_version,
        config_version=config_version,
        seed_box_repo=seed_box_repo,
        recommendation_repo=recommendation_repo,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
