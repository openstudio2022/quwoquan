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
DELIVERY_SCOPE_NAMES = (*SCOPE_NAMES, "device", "coverage_service", "coverage_app")
LOCAL_SCOPE_NAMES = (*SCOPE_NAMES, "spec_contract")
INTEGRATION_DEPTHS = ("no_live", "alpha_integration", "abg_release_sensitive")
SOURCE_IDENTITY = "quwoquan-impact-planner"
SOURCE_VERSION = "impact-planner-v2"
IMPACT_PLAN_SCHEMA = "delivery-impact-plan"
IMPACT_PLAN_SCHEMA_VERSION = 1
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:/")

_DEVICE_IMPACT_PREFIXES = (
    "quwoquan_app/android/",
    "quwoquan_app/ios/",
    "quwoquan_app/lib/main.dart",
    "quwoquan_app/lib/main_prod.dart",
    "quwoquan_app/lib/runtime/config/",
    "quwoquan_app/lib/runtime/platform/",
    "quwoquan_app/lib/runtime/shell/startup/",
    "quwoquan_app/pubspec.yaml",
    "quwoquan_app/pubspec.lock",
    "quwoquan_app/scripts/device/",
    "quwoquan_app/scripts/gamma/",
    "quwoquan_app/scripts/ios/",
    "quwoquan_app/scripts/runtime/platform/",
    "quwoquan_app/test_host/patrol/android/",
    "quwoquan_app/test_host/patrol/ios/",
    "quwoquan_app/test_host/patrol/lib/main.dart",
    "quwoquan_app/test_host/patrol/pubspec.yaml",
    "quwoquan_app/test_host/patrol/pubspec.lock",
    "quwoquan_app/vendor/plugins/",
    "quwoquan_service/runtime/",
    "quwoquan_ops/ci/device_",
    "quwoquan_ops/ci/device_matrix/",
    "quwoquan_ops/ci/run_mobile_platform_matrix.sh",
    "quwoquan_ops/ci/render_beta_device_evidence.py",
    "quwoquan_ops/ci/render_environment_stability_attested_receipt.py",
    "quwoquan_ops/cli/lib/environment_topology.py",
    "quwoquan_ops/cli/lib/runtime_topology_package.py",
    "quwoquan_ops/environments/",
    "quwoquan_ops/ci/environment_scheduler.py",
    "quwoquan_ops/ci/run_mobile_platform_matrix.sh",
)
_COVERAGE_GOVERNANCE_PREFIXES = (
    "quwoquan_ops/gate/verify_canonical_coverage.py",
    "quwoquan_ops/policies/gates/canonical_coverage",
    "quwoquan_ops/tests/local_contract/gate/test_canonical_coverage",
)
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
        "schema": IMPACT_PLAN_SCHEMA,
        "schema_version": IMPACT_PLAN_SCHEMA_VERSION,
        "scopes": list(SCOPE_NAMES),
        "delivery_scopes": list(DELIVERY_SCOPE_NAMES),
        "device_impact_prefixes": list(_DEVICE_IMPACT_PREFIXES),
        "coverage_governance_prefixes": list(_COVERAGE_GOVERNANCE_PREFIXES),
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


def _matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def build_delivery_impact_plan(
    paths: Iterable[str],
    *,
    source_sha: str,
    base_sha: str,
    force_device: bool = False,
    fail_closed_empty: bool = False,
) -> dict[str, object]:
    """Build the versioned, artifact-safe Delivery impact contract once per DAG."""

    source = validate_exact_sha(source_sha, label="source_sha")
    base = validate_exact_sha(base_sha, label="base_sha")
    classified = classify_impacts(paths, fail_closed_empty=fail_closed_empty)
    changed_paths = list(classified["paths"])
    runtime_scopes = dict(classified["scopes"])
    governance_closure = any(
        _matches_prefix(path, _COVERAGE_GOVERNANCE_PREFIXES)
        or path == "quwoquan_ops/ci/impact_planner_core.py"
        or path == "quwoquan_ops/ci/detect_ci_impacted_scopes.py"
        for path in changed_paths
    )
    device_required = force_device or any(
        _matches_prefix(path, _DEVICE_IMPACT_PREFIXES) for path in changed_paths
    )
    coverage_service = bool(runtime_scopes["service"] or governance_closure)
    coverage_app = bool(runtime_scopes["app"] or governance_closure)
    scopes = {
        **runtime_scopes,
        "device": device_required,
        "coverage_service": coverage_service,
        "coverage_app": coverage_app,
    }
    states = {
        name: "required" if required else "not_required"
        for name, required in scopes.items()
    }
    plan = {
        "schema": IMPACT_PLAN_SCHEMA,
        "schema_version": IMPACT_PLAN_SCHEMA_VERSION,
        "source_sha": source,
        "base_sha": base,
        "impact_planner": planner_identity(),
        "changed_paths": changed_paths,
        "changed_paths_digest": classified["path_digest"],
        "scopes": scopes,
        "states": states,
        "policy": {
            "device_forced": bool(force_device),
            "coverage_contract_closure": governance_closure,
        },
    }
    return {**plan, "plan_digest": canonical_digest(plan)}


def validate_delivery_impact_plan(
    payload: Mapping[str, object],
    *,
    expected_source_sha: str = "",
) -> dict[str, object]:
    """Validate schema/version/source/path digest and the complete plan digest."""

    if not isinstance(payload, Mapping):
        raise ImpactPlannerError("Delivery impact plan 必须为 object")
    if payload.get("schema") != IMPACT_PLAN_SCHEMA:
        raise ImpactPlannerError("Delivery impact plan schema 不受支持")
    if payload.get("schema_version") != IMPACT_PLAN_SCHEMA_VERSION:
        raise ImpactPlannerError("Delivery impact plan schema_version 不受支持")
    source_sha = validate_exact_sha(str(payload.get("source_sha") or ""), label="source_sha")
    validate_exact_sha(str(payload.get("base_sha") or ""), label="base_sha")
    if expected_source_sha and source_sha != validate_exact_sha(
        expected_source_sha, label="expected_source_sha"
    ):
        raise ImpactPlannerError("Delivery impact plan source_sha 漂移")
    paths = payload.get("changed_paths")
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ImpactPlannerError("Delivery impact plan changed_paths 非 canonical list")
    normalized = normalize_changed_paths(paths)
    if normalized != paths:
        raise ImpactPlannerError("Delivery impact plan changed_paths 未 canonicalize")
    if payload.get("changed_paths_digest") != canonical_digest(normalized):
        raise ImpactPlannerError("Delivery impact plan changed_paths digest 漂移")
    identity = payload.get("impact_planner")
    if identity != planner_identity():
        raise ImpactPlannerError("Delivery impact planner identity 漂移")
    scopes = payload.get("scopes")
    states = payload.get("states")
    if not isinstance(scopes, Mapping) or set(scopes) != set(DELIVERY_SCOPE_NAMES):
        raise ImpactPlannerError("Delivery impact plan scopes 不闭合")
    if not isinstance(states, Mapping) or set(states) != set(DELIVERY_SCOPE_NAMES):
        raise ImpactPlannerError("Delivery impact plan states 不闭合")
    for name in DELIVERY_SCOPE_NAMES:
        required = scopes[name]
        if not isinstance(required, bool):
            raise ImpactPlannerError(f"Delivery impact scope {name} 必须为 bool")
        expected_state = "required" if required else "not_required"
        if states[name] != expected_state:
            raise ImpactPlannerError(f"Delivery impact scope {name} state 漂移")
    unsigned = dict(payload)
    plan_digest = unsigned.pop("plan_digest", None)
    if plan_digest != canonical_digest(unsigned):
        raise ImpactPlannerError("Delivery impact plan digest 漂移")
    return dict(payload)
