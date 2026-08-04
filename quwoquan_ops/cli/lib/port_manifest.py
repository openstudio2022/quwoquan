from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import ROOT


DEFAULT_PATH = ROOT / "quwoquan_ops" / "environments" / "local_env_port_manifest.yaml"
REQUIRED_PROFILES = ("alpha-local", "beta-local", "gamma-local", "prod-sim")
REQUIRED_PLANES = ("edge", "media", "service", "dataDebug")


def load_port_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DEFAULT_PATH

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        loaded_object: dict[str, Any] = {}
        for key, value in pairs:
            if key in loaded_object:
                raise RuntimeError(
                    f"local env port manifest contains duplicate key: {key}"
                )
            loaded_object[key] = value
        return loaded_object

    try:
        loaded = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"local env port manifest must use strict JSON syntax: {manifest_path}"
        ) from exc
    if not isinstance(loaded, dict):
        raise RuntimeError("local env port manifest must be a mapping")
    return loaded


def validate_port_manifest(manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if manifest.get("schema") != "local-env-port-manifest":
        issues.append("schema must be local-env-port-manifest")

    planes = manifest.get("planes")
    roles = manifest.get("roles")
    profiles = manifest.get("profiles")
    if not isinstance(planes, dict):
        issues.append("planes must be a mapping")
        return issues
    if not isinstance(roles, dict):
        issues.append("roles must be a mapping")
        return issues
    if not isinstance(profiles, dict):
        issues.append("profiles must be a mapping")
        return issues

    for plane_name in REQUIRED_PLANES:
        plane = planes.get(plane_name)
        if not isinstance(plane, dict):
            issues.append(f"missing plane definition: {plane_name}")
            continue
        if not isinstance(plane.get("offsetStart"), int):
            issues.append(f"{plane_name}: offsetStart must be int")
        if not isinstance(plane.get("offsetEnd"), int):
            issues.append(f"{plane_name}: offsetEnd must be int")

    for role_name, role in roles.items():
        if not isinstance(role, dict):
            issues.append(f"{role_name}: role definition must be a mapping")
            continue
        plane = str(role.get("plane", "")).strip()
        slot = role.get("slotOffset")
        if plane not in planes:
            issues.append(f"{role_name}: plane must be one of {', '.join(planes)}")
            continue
        if not isinstance(slot, int):
            issues.append(f"{role_name}: slotOffset must be int")
            continue
        plane_range = planes[plane]
        start = int(plane_range["offsetStart"])
        end = int(plane_range["offsetEnd"])
        if slot < start or slot > end:
            issues.append(
                f"{role_name}: slotOffset {slot} must stay within plane {plane} range {start}-{end}"
            )
        if slot % 10 != 0:
            issues.append(f"{role_name}: slotOffset must end with 0")
        endpoint_values = {
            "serviceHost": role.get("serviceHost"),
            "containerPort": role.get("containerPort"),
            "scheme": role.get("scheme"),
        }
        if any(value is not None for value in endpoint_values.values()):
            missing = [
                key
                for key, value in endpoint_values.items()
                if value is None or (isinstance(value, str) and not value.strip())
            ]
            if missing:
                issues.append(
                    f"{role_name}: internal endpoint metadata is incomplete: {missing}"
                )
            if (
                not isinstance(endpoint_values["containerPort"], int)
                or not 0 < endpoint_values["containerPort"] < 65536
            ):
                issues.append(
                    f"{role_name}: containerPort must be an integer in 1..65535"
                )
            if endpoint_values["scheme"] not in {"http", "https"}:
                issues.append(f"{role_name}: scheme must be http or https")

    for profile_name in REQUIRED_PROFILES:
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            issues.append(f"missing profile definition: {profile_name}")
            continue
        start = profile.get("blockStart")
        end = profile.get("blockEnd")
        if not isinstance(start, int) or not isinstance(end, int):
            issues.append(f"{profile_name}: blockStart/blockEnd must be int")
            continue
        if start % 1000 != 0:
            issues.append(f"{profile_name}: blockStart must align to 1000-port block")
        if end - start != 999:
            issues.append(f"{profile_name}: blockEnd must close a 1000-port block")

    seen_ports: dict[int, str] = {}
    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        start = profile.get("blockStart")
        end = profile.get("blockEnd")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        for role_name, role in roles.items():
            if not isinstance(role, dict):
                continue
            slot = role.get("slotOffset")
            if not isinstance(slot, int):
                continue
            canonical = start + slot
            if canonical % 10 != 0:
                issues.append(f"{profile_name}/{role_name}: canonical port must end with 0")
            if canonical < start or canonical > end:
                issues.append(
                    f"{profile_name}/{role_name}: canonical port {canonical} escapes block {start}-{end}"
                )
            owner = seen_ports.setdefault(canonical, f"{profile_name}/{role_name}")
            if owner != f"{profile_name}/{role_name}":
                issues.append(
                    f"duplicate canonical port {canonical}: {owner} and {profile_name}/{role_name}"
                )

    return issues


def canonical_port(manifest: dict[str, Any], profile_name: str, role_name: str) -> int:
    profile = manifest["profiles"][profile_name]
    role = manifest["roles"][role_name]
    return int(profile["blockStart"]) + int(role["slotOffset"])


def profile_ports(manifest: dict[str, Any], profile_name: str) -> dict[str, int]:
    return {
        role_name: canonical_port(manifest, profile_name, role_name)
        for role_name in manifest.get("roles", {})
    }


def internal_role_base_url(manifest: dict[str, Any], role_name: str) -> str:
    role = manifest.get("roles", {}).get(role_name)
    if not isinstance(role, dict):
        raise ValueError(f"local topology role is unavailable: {role_name}")
    host = str(role.get("serviceHost") or "").strip()
    scheme = str(role.get("scheme") or "").strip()
    port = role.get("containerPort")
    if not host or scheme not in {"http", "https"} or not isinstance(port, int):
        raise ValueError(
            f"local topology role has no complete internal endpoint: {role_name}"
        )
    return f"{scheme}://{host}:{port}"
