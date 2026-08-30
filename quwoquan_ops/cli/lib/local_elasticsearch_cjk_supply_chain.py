"""Fail-closed verification for the local Elasticsearch CJK image."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

SCHEMA = "quwoquan.elasticsearch_cjk_supply_chain.v1"
PLUGIN_NAMES = frozenset({"analysis-ik", "analysis-pinyin"})
MULTI_ARCH_IMAGE_MEDIA_TYPE = (
    "application/vnd.docker.distribution.manifest.list.v2+json"
)
SHA256 = re.compile(r"[0-9a-f]{64}")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def load_supply_chain(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError("Elasticsearch CJK supply-chain schema is invalid")
    elasticsearch = payload.get("elasticsearch")
    plugins = payload.get("plugins")
    architectures = payload.get("supportedArchitectures")
    if (
        not isinstance(elasticsearch, Mapping)
        or elasticsearch.get("version") != "8.13.4"
        or "@sha256:" not in str(elasticsearch.get("image") or "")
        or elasticsearch.get("mediaType") != MULTI_ARCH_IMAGE_MEDIA_TYPE
        or not elasticsearch.get("license")
        or not isinstance(plugins, list)
        or {item.get("name") for item in plugins if isinstance(item, Mapping)}
        != PLUGIN_NAMES
        or set(architectures or ()) != {"amd64", "arm64"}
    ):
        raise ValueError("Elasticsearch CJK supply-chain identity is incomplete")
    for plugin in plugins:
        if (
            plugin.get("version") != elasticsearch["version"]
            or not str(plugin.get("sourceUrl") or "").startswith("https://")
            or SHA256.fullmatch(str(plugin.get("sha256") or "")) is None
            or not plugin.get("sourceRevision")
            or not plugin.get("sourceRepository")
            or not plugin.get("license")
            or not plugin.get("licenseUrl")
        ):
            raise ValueError(
                f"Elasticsearch CJK plugin identity is invalid: {plugin.get('name')}"
            )
    return payload


def verify_plugin_archives(
    manifest: Mapping[str, Any],
    archives: Mapping[str, Path],
) -> dict[str, str]:
    verified: dict[str, str] = {}
    for plugin in manifest["plugins"]:
        name = str(plugin["name"])
        path = archives.get(name)
        if path is None or not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Elasticsearch CJK plugin archive is missing: {name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != plugin["sha256"]:
            raise RuntimeError(f"Elasticsearch CJK plugin checksum mismatch: {name}")
        verified[name] = digest
    return verified


def verify_runtime_image(
    image: str,
    manifest: Mapping[str, Any],
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    inspected = runner(
        ["docker", "image", "inspect", image],
        text=True,
        capture_output=True,
        check=False,
    )
    if inspected.returncode != 0:
        raise RuntimeError("Elasticsearch CJK image inspect failed")
    rows = json.loads(inspected.stdout)
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError("Elasticsearch CJK image identity is ambiguous")
    architecture = str(rows[0].get("Architecture") or "")
    if architecture not in set(manifest["supportedArchitectures"]):
        raise RuntimeError(
            f"Elasticsearch CJK image architecture is unsupported: {architecture}"
        )
    plugins = runner(
        [
            "docker",
            "run",
            "--rm",
            "-e",
            "CLI_JAVA_OPTS=-XX:UseSVE=0",
            "--entrypoint",
            "/usr/share/elasticsearch/bin/elasticsearch-plugin",
            image,
            "list",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    actual = {line.strip() for line in plugins.stdout.splitlines() if line.strip()}
    if plugins.returncode != 0 or actual != PLUGIN_NAMES:
        raise RuntimeError(
            "Elasticsearch CJK image plugin closure is incomplete: "
            + ",".join(sorted(actual))
        )
    return {
        "imageId": rows[0].get("Id"),
        "architecture": architecture,
        "plugins": sorted(actual),
    }
