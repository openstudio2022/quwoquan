#!/usr/bin/env python3
"""Canonical pure impact classification shared by local and hosted planners."""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import unicodedata
from typing import Iterable, Mapping

SCOPE_NAMES = ("service", "app", "portal", "topology", "data")
LOCAL_SCOPE_NAMES = (*SCOPE_NAMES, "spec_contract")
INTEGRATION_DEPTHS = ("no_live", "alpha_integration", "abg_release_sensitive")
SOURCE_IDENTITY = "quwoquan-impact-planner"
SOURCE_VERSION = "impact-planner-v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:/")

_ALL_SCOPE_PREFIXES = (
    ".github/workflows/",
    "quwoquan_app/scripts/",
    "quwoquan_service/scripts/",
    "quwoquan_data/scripts/",
)
_DATA_PREFIXES = ("quwoquan_data/", ".agents/skills/content-production/")
_DATA_DOCUMENT_PREFIXES = ("specs/feature-tree/discovery-content/",)
_DOC_ONLY_PREFIXES = ("specs/", "docs/")
_DOC_ONLY_SUFFIXES = {".md", ".mdc", ".png", ".jpg", ".jpeg", ".gif", ".svg"}
_ROOT_LEVEL_ALL_SCOPE_FILES = {"Makefile"}
_METADATA_PREFIX = "quwoquan_service/contracts/metadata/"
_SERVICE_CONTRACT_PREFIX = "quwoquan_service/services/"
_SERVICE_CONTRACT_SEGMENT = "/contracts/"
_FEATURE_SPEC_SCOPE_RULES: tuple[tuple[str, Mapping[str, bool]], ...] = (
    (
        "specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/",
        {"service": False, "app": True, "portal": False, "topology": False},
    ),
    (
        "specs/feature-tree/runtime/runtime-client-foundation/",
        {"service": False, "app": True, "portal": False, "topology": False},
    ),
    (
        "specs/feature-tree/product-ops-growth/",
        {"service": True, "app": True, "portal": True, "topology": False},
    ),
    (
        "specs/feature-tree/platform-ops-governance/",
        {"service": True, "app": False, "portal": True, "topology": False},
    ),
)


class ImpactPlannerError(ValueError):
    """Fail-closed malformed planner input."""


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalize_changed_path(raw_path: str) -> str:
    """Return one lexical repository-relative NFC path or fail closed."""

    if not isinstance(raw_path, str):
        raise ImpactPlannerError("changed path 必须为字符串")
    path = unicodedata.normalize("NFC", raw_path.replace("\\", "/"))
    if not path or path != path.strip() or any(char in path for char in ("\x00", "\n", "\r")):
        raise ImpactPlannerError(f"changed path 含空白或为空：{raw_path!r}")
    if path.startswith("/") or _WINDOWS_DRIVE_RE.match(path):
        raise ImpactPlannerError(f"changed path 必须为仓库相对路径：{raw_path!r}")
    parts = path.split("/")
    if any(part in {"", ".."} for part in parts):
        raise ImpactPlannerError(f"changed path 含非法 segment：{raw_path!r}")
    normalized = unicodedata.normalize("NFC", posixpath.normpath(path))
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise ImpactPlannerError(f"changed path 不在仓库内：{raw_path!r}")
    return normalized


def normalize_changed_paths(paths: Iterable[str]) -> list[str]:
    normalized = {normalize_changed_path(path) for path in paths}
    return sorted(normalized, key=lambda value: value.encode("utf-8"))


def validate_exact_sha(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ImpactPlannerError(f"{label} 必须为 40 位 lowercase exact SHA")
    return value


def planner_identity() -> dict[str, str]:
    ruleset = {
        "source": SOURCE_IDENTITY,
        "version": SOURCE_VERSION,
        "scopes": list(SCOPE_NAMES),
        "all_scope_prefixes": list(_ALL_SCOPE_PREFIXES),
        "data_prefixes": list(_DATA_PREFIXES),
        "data_document_prefixes": list(_DATA_DOCUMENT_PREFIXES),
        "root_all_scope_files": sorted(_ROOT_LEVEL_ALL_SCOPE_FILES),
        "metadata_prefix": _METADATA_PREFIX,
        "service_contract": {
            "prefix": _SERVICE_CONTRACT_PREFIX,
            "segment": _SERVICE_CONTRACT_SEGMENT,
            "closure": ["service", "app", "portal"],
        },
        "portal_closure": ["portal", "data"],
        "ops_non_portal_closure": list(SCOPE_NAMES),
        "feature_spec_rules": [
            [prefix, dict(flags)] for prefix, flags in _FEATURE_SPEC_SCOPE_RULES
        ],
    }
    return {
        "source": SOURCE_IDENTITY,
        "version": SOURCE_VERSION,
        "digest": canonical_digest(ruleset),
    }


def _is_doc_only(path: str) -> bool:
    if path.startswith("specs/feature-tree/") and path.rsplit("/", 1)[-1] in {"spec.md", "design.md"}:
        return False
    suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return suffix in _DOC_ONLY_SUFFIXES and path.startswith(_DOC_ONLY_PREFIXES)


def _feature_spec_scopes(path: str) -> Mapping[str, bool] | None:
    if not path.startswith("specs/feature-tree/") or path.rsplit("/", 1)[-1] not in {"spec.md", "design.md"}:
        return None
    for prefix, flags in _FEATURE_SPEC_SCOPE_RULES:
        if path.startswith(prefix):
            return flags
    return {"service": True, "app": True, "portal": True, "topology": False}


def _apply_all(scopes: dict[str, bool]) -> None:
    for scope in SCOPE_NAMES:
        scopes[scope] = True


def _classify_one(path: str, scopes: dict[str, bool]) -> None:
    if _is_doc_only(path):
        if path.startswith(_DATA_DOCUMENT_PREFIXES):
            scopes["data"] = True
        return

    feature_scopes = _feature_spec_scopes(path)
    if feature_scopes is not None:
        for scope, required in feature_scopes.items():
            scopes[scope] = scopes[scope] or required
        if path.startswith(_DATA_DOCUMENT_PREFIXES):
            scopes["data"] = True
        return

    if path in _ROOT_LEVEL_ALL_SCOPE_FILES or path.startswith(_ALL_SCOPE_PREFIXES):
        _apply_all(scopes)
        return

    if path.startswith("quwoquan_ops/portal/"):
        scopes["portal"] = True
        scopes["data"] = True
        return

    if path.startswith("quwoquan_ops/"):
        _apply_all(scopes)
        return

    if path.startswith(_METADATA_PREFIX) or (
        path.startswith(_SERVICE_CONTRACT_PREFIX)
        and _SERVICE_CONTRACT_SEGMENT in path
    ):
        scopes["service"] = True
        scopes["app"] = True
        scopes["portal"] = True
        return

    if path.startswith(_DATA_PREFIXES):
        scopes["data"] = True
        return
    if path.startswith("quwoquan_ops/environments/"):
        scopes["topology"] = True
    if path.startswith("quwoquan_service/"):
        scopes["service"] = True
    if path.startswith("quwoquan_app/"):
        scopes["app"] = True


def derive_integration_depth(classification: Mapping[str, object]) -> str:
    """由 typed impact scopes 派生 G2 集成深度档位；档位只能派生，不得人工降档。

    - data/topology 影响属 release-sensitive 面，要求 Alpha→Beta→Gamma 全链验证；
    - app/service/portal 任一 runtime 影响默认要求 Alpha 真实集成；
    - 五个 runtime scope 全空才允许 runtime-neutral 免真启档。
    """

    if not isinstance(classification, Mapping):
        raise ImpactPlannerError("integration depth 输入必须为 classify_impacts 结果")
    scopes = classification.get("scopes")
    if not isinstance(scopes, Mapping) or set(scopes) != set(SCOPE_NAMES):
        raise ImpactPlannerError("integration depth 需要完整 typed runtime scopes")
    for name in SCOPE_NAMES:
        if not isinstance(scopes[name], bool):
            raise ImpactPlannerError(f"runtime scope {name} 必须为 bool")
    if scopes["data"] or scopes["topology"]:
        return "abg_release_sensitive"
    if scopes["app"] or scopes["service"] or scopes["portal"]:
        return "alpha_integration"
    return "no_live"


def classify_impacts(paths: Iterable[str], *, fail_closed_empty: bool = False) -> dict[str, object]:
    normalized = normalize_changed_paths(paths)
    scopes = {scope: False for scope in SCOPE_NAMES}
    if not normalized and fail_closed_empty:
        _apply_all(scopes)
    else:
        for path in normalized:
            _classify_one(path, scopes)

    spec_contract = any(
        path.startswith(("specs/", "quwoquan_ops/policies/"))
        or "/contracts/" in path
        for path in normalized
    )
    return {
        "source": planner_identity(),
        "paths": normalized,
        "path_digest": canonical_digest(normalized),
        "scopes": scopes,
        "local_scopes": {
            **scopes,
            "spec_contract": spec_contract,
        },
    }
