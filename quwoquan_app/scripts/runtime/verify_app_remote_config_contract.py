#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "specs/gates/app_remote_config_catalog.yaml"
SPEC = (
    ROOT
    / "specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md"
)
ACCEPTANCE = (
    ROOT
    / "specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/acceptance.yaml"
)

RISK_LEVELS = {"low", "medium", "high", "critical"}
RELOAD_POLICIES = {
    "hot",
    "restart_only",
    "app_release",
    "request",
    "test_only",
}
ACTIVATION_POLICIES = {
    "immediate",
    "next_navigation",
    "next_session",
    "restart_only",
    "request",
    "test_only",
}
REQUIRED_ITEM_FIELDS = {
    "key",
    "owner",
    "risk_level",
    "reload_policy",
    "activation_policy",
    "fallback",
    "expiry",
}
REMOTE_FORBIDDEN_TOKENS = {
    "gateway",
    "cdn_base",
    "auth",
    "secret",
    "payment",
    "permission",
    "token",
    "keychain",
}
DIRECT_APP_CONFIG_CALL = re.compile(r"\.\s*getAppConfig\s*\(")


def main() -> int:
    errors: list[str] = []
    for path in (CATALOG, SPEC, ACCEPTANCE):
        if not path.is_file():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")
    if errors:
        return report(errors)

    try:
        data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return report([f"cannot parse catalog yaml: {exc}"])

    if not isinstance(data, dict):
        return report(["catalog root must be a mapping"])
    if data.get("schema_id") != "app_remote_config_catalog":
        errors.append("schema_id must be app_remote_config_catalog")
    categories = data.get("categories")
    if not isinstance(categories, list) or not categories:
        errors.append("categories must be a non-empty list")
        return report(errors)

    seen_keys: set[str] = set()
    category_ids: set[str] = set()
    has_remote = False
    for category in categories:
        if not isinstance(category, dict):
            errors.append("category entry must be a mapping")
            continue
        category_id = str(category.get("id", "")).strip()
        if not category_id:
            errors.append("category.id is required")
            continue
        if category_id in category_ids:
            errors.append(f"duplicate category id: {category_id}")
        category_ids.add(category_id)
        remote_editable = category.get("remote_editable") is True
        if category_id == "app_remote_config":
            has_remote = True
            if not remote_editable:
                errors.append("app_remote_config category must be remote_editable=true")
        items = category.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{category_id}: items must be a non-empty list")
            continue
        for item in items:
            if not isinstance(item, dict):
                errors.append(f"{category_id}: item must be a mapping")
                continue
            missing = sorted(REQUIRED_ITEM_FIELDS - set(item))
            key = str(item.get("key", "")).strip()
            if missing:
                errors.append(f"{category_id}.{key or '<missing-key>'}: missing {missing}")
            if not key:
                errors.append(f"{category_id}: item key is required")
                continue
            if key in seen_keys:
                errors.append(f"duplicate config key across catalog: {key}")
            seen_keys.add(key)
            risk = str(item.get("risk_level", "")).strip()
            if risk not in RISK_LEVELS:
                errors.append(f"{key}: invalid risk_level {risk!r}")
            reload_policy = str(item.get("reload_policy", "")).strip()
            if reload_policy not in RELOAD_POLICIES:
                errors.append(f"{key}: invalid reload_policy {reload_policy!r}")
            activation_policy = str(item.get("activation_policy", "")).strip()
            if activation_policy not in ACTIVATION_POLICIES:
                errors.append(f"{key}: invalid activation_policy {activation_policy!r}")
            expiry = str(item.get("expiry", "")).strip()
            if not expiry:
                errors.append(f"{key}: expiry must be set to a date or never")
            if remote_editable:
                lower_key = key.lower()
                for token in REMOTE_FORBIDDEN_TOKENS:
                    if token in lower_key:
                        errors.append(
                            f"{key}: forbidden token {token!r} in remote editable config",
                        )
                if risk == "critical":
                    errors.append(f"{key}: critical configs cannot be remote editable")
                if activation_policy == "restart_only":
                    errors.append(f"{key}: remote editable config cannot be restart_only")

    if not has_remote:
        errors.append("missing app_remote_config category")
    errors.extend(check_app_config_call_sites())
    return report(errors)


def check_app_config_call_sites() -> list[str]:
    allowed = {
        "quwoquan_app/lib/core/providers/app_providers.dart",
        "quwoquan_app/lib/cloud/services/content/content_repository_remote.dart",
        "quwoquan_app/lib/cloud/services/content/content_repository_mock.dart",
        "quwoquan_app/lib/core/services/cache/cached_content_repository.dart",
    }
    errors: list[str] = []
    lib = ROOT / "quwoquan_app/lib"
    for path in lib.rglob("*.dart"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if DIRECT_APP_CONFIG_CALL.search(text):
            errors.append(
                f"{rel}: direct getAppConfig call is not allowed; use appRemoteConfigProvider/contentRuntimeConfigProvider",
            )
    return errors


def report(errors: list[str]) -> int:
    if errors:
        print("app-remote-config contract check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("app-remote-config contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
