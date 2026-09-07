#!/usr/bin/env python3
"""Canonical pure impact classification shared by local and hosted planners."""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Mapping

SCOPE_NAMES = ("service", "app", "portal", "topology", "data")
DELIVERY_SCOPE_NAMES = (*SCOPE_NAMES, "device", "coverage_service", "coverage_app")
LOCAL_SCOPE_NAMES = (*SCOPE_NAMES, "spec_contract")
INTEGRATION_DEPTHS = ("no_live", "alpha_integration", "abg_release_sensitive")
SOURCE_IDENTITY = "quwoquan-impact-planner"
SOURCE_VERSION = "impact-planner-v3"
IMPACT_PLAN_SCHEMA = "delivery-impact-plan"
IMPACT_PLAN_SCHEMA_VERSION = 2
RISK_LEVELS = ("R0", "R1", "R2", "R3", "R4")
EXECUTION_PROFILES = ("pr", "promotion", "nightly", "manual")
ROOT = Path(__file__).resolve().parents[2]
TEST_OWNERSHIP_POLICY = ROOT / "quwoquan_ops/policies/ci_test_ownership.json"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TREE_DIGEST_RE = re.compile(r"^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
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

_R4_GOVERNANCE_PREFIXES = (
    ".github/workflows/",
    "quwoquan_ops/ci/impact_planner_core.py",
    "quwoquan_ops/ci/detect_ci_impacted_scopes.py",
    "quwoquan_ops/ci/verify_ci_changed_boundary.py",
    "quwoquan_ops/ci/verify_hosted_integration_ruleset.py",
    "quwoquan_ops/policies/branch_policy.yaml",
    "quwoquan_ops/policies/ci_test_ownership.json",
    "quwoquan_ops/policies/flaky_test_policy.json",
    "quwoquan_ops/gate/verify_github_supply_chain.py",
)
_R3_GOVERNANCE_PREFIXES = (
    "quwoquan_ops/",
    "quwoquan_service/contracts/",
    "quwoquan_ops/environments/",
)
_RECOMMENDATION_PREFIXES = (
    "quwoquan_service/services/recommendation-service/",
    "quwoquan_service/runtime/recommendation/",
    "quwoquan_service/runtime/recpolicy/",
)
_KNOWN_TOP_LEVEL_PREFIXES = (
    ".agents/", ".codex/", ".cursor/", ".github/", "docs/", "specs/",
    "quwoquan_app/", "quwoquan_data/", "quwoquan_ops/", "quwoquan_service/",
)
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


def validate_tree_digest(value: str) -> str:
    if not isinstance(value, str) or _TREE_DIGEST_RE.fullmatch(value) is None:
        raise ImpactPlannerError("source_tree_digest 必须为 lowercase sha1/sha256 digest")
    return value


def _load_test_ownership_policy() -> tuple[dict[str, object], str]:
    try:
        payload = json.loads(TEST_OWNERSHIP_POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ImpactPlannerError(f"test ownership policy 不可读：{error}") from error
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "ci-test-ownership-policy"
        or payload.get("schemaVersion") != 1
    ):
        raise ImpactPlannerError("test ownership policy schema 不受支持")
    owners = payload.get("ownerVocabulary")
    if not isinstance(owners, list) or not owners or any(not isinstance(item, str) for item in owners):
        raise ImpactPlannerError("test ownership vocabulary 不闭合")
    for collection in ("tests", "apis", "journeys"):
        entries = payload.get(collection)
        if not isinstance(entries, dict) or not entries:
            raise ImpactPlannerError(f"test ownership {collection} 为空")
        for item_id, entry in entries.items():
            if (
                not isinstance(item_id, str)
                or not isinstance(entry, dict)
                or entry.get("owner") not in owners
                or not isinstance(entry.get("selector"), str)
                or not entry["selector"]
            ):
                raise ImpactPlannerError(f"test ownership {collection}.{item_id} 非法")
    return payload, canonical_digest(payload)


def _known_path(path: str) -> bool:
    return path in _ROOT_LEVEL_ALL_SCOPE_FILES or path in {
        "AGENTS.md", "README.md", "LICENSE", ".gitignore", ".dockerignore"
    } or path.startswith(_KNOWN_TOP_LEVEL_PREFIXES)


def _derive_risk(
    paths: list[str], *, scopes: Mapping[str, bool], device_required: bool,
    execution_profile: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    unknown = [path for path in paths if not _known_path(path)]
    if execution_profile == "promotion":
        return "R4", ["promotion_full_qualification"]
    if any(_matches_prefix(path, _R4_GOVERNANCE_PREFIXES) for path in paths):
        return "R4", ["release_or_planner_governance_changed"]
    if unknown:
        return "R3", ["unknown_path_fail_closed", *[f"unknown:{path}" for path in unknown]]
    if any(_matches_prefix(path, _R3_GOVERNANCE_PREFIXES) for path in paths):
        return "R3", ["governance_contract_or_environment_changed"]
    required_runtime = [name for name, required in scopes.items() if required]
    if device_required or len(required_runtime) > 1:
        reasons.append("cross_scope_or_device_impact")
        return "R2", reasons
    if required_runtime:
        return "R1", [f"single_scope:{required_runtime[0]}"]
    return "R0", ["non_runtime_change"]


def _require_ids(policy: Mapping[str, object], collection: str, ids: Iterable[str]) -> list[str]:
    entries = policy.get(collection)
    if not isinstance(entries, Mapping):
        raise ImpactPlannerError(f"test ownership {collection} 非法")
    result = sorted(set(ids))
    missing = [item for item in result if item not in entries]
    if missing:
        raise ImpactPlannerError(f"required {collection} IDs 未登记：{missing}")
    return result


def _derive_required_ids(
    *, policy: Mapping[str, object], scopes: Mapping[str, bool],
    device_required: bool, integration_depth: str, paths: list[str],
    execution_profile: str,
) -> dict[str, list[str]]:
    tests = ["TEST-COMMON-GOVERNANCE"]
    apis: list[str] = []
    journeys: list[str] = []
    if scopes["topology"]:
        tests.append("TEST-TOPOLOGY-REGRESSION")
    if scopes["service"]:
        tests.append("TEST-SERVICE-CORE")
        apis.extend(("API-SERVICE-CONTRACT", "API-SEARCH-CONTRACT"))
    if scopes["app"]:
        tests.extend(("TEST-APP-STATIC", "TEST-APP-LOCAL-CONTRACT"))
        journeys.append("JOURNEY-APP-LOCAL-CONTRACT")
    if scopes["data"]:
        tests.extend(("TEST-DATA-VERIFY", "TEST-DATA-LOCAL-CONTRACT"))
    if scopes["portal"]:
        tests.append("TEST-PORTAL")
        apis.append("API-PORTAL-CONTRACT")
    if any(_matches_prefix(path, _RECOMMENDATION_PREFIXES) for path in paths):
        apis.append("API-RECOMMENDATION")
    if device_required:
        tests.append("TEST-DEVICE-MATRIX")
        journeys.append("JOURNEY-DUAL-PHYSICAL-DEVICE")
    if integration_depth == "abg_release_sensitive":
        journeys.append("JOURNEY-ABG-READINESS")
    if execution_profile in {"promotion", "nightly", "manual"}:
        if scopes["service"]:
            tests.append("TEST-SERVICE-COVERAGE")
        if scopes["app"]:
            tests.extend(("TEST-APP-SERIAL", "TEST-APP-COVERAGE"))
    return {
        "testIds": _require_ids(policy, "tests", tests),
        "apiIds": _require_ids(policy, "apis", apis),
        "journeyIds": _require_ids(policy, "journeys", journeys),
    }


def planner_identity() -> dict[str, str]:
    _policy, ownership_digest = _load_test_ownership_policy()
    ruleset = {
        "source": SOURCE_IDENTITY,
        "version": SOURCE_VERSION,
        "schema": IMPACT_PLAN_SCHEMA,
        "schema_version": IMPACT_PLAN_SCHEMA_VERSION,
        "risk_levels": list(RISK_LEVELS),
        "execution_profiles": list(EXECUTION_PROFILES),
        "test_ownership_digest": ownership_digest,
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
    """把 changed paths 分类成"触及了哪些运行时 scope"的事实。

    未知根级路径在这里不扇出：它触及的运行时是零，而非全部。把它升到 R3 并要求全 scope
    是 Delivery 的 fail-closed 决策，由 `build_delivery_impact_plan` 显式施加；本地
    L-1/L0 复用本函数做秒级 focused 反馈，不能为一个陌生根文件跑遍全部 scope。
    """
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
    head_sha: str = "",
    synthetic_sha: str = "",
    source_tree_digest: str,
    execution_profile: str = "pr",
    force_device: bool = False,
    fail_closed_empty: bool = False,
    required_scopes: Iterable[str] = (),
) -> dict[str, object]:
    """Build one exact, versioned Delivery impact contract for the whole DAG."""

    source = validate_exact_sha(source_sha, label="source_sha")
    base = validate_exact_sha(base_sha, label="base_sha")
    head = validate_exact_sha(head_sha or source, label="head_sha")
    synthetic = validate_exact_sha(synthetic_sha or source, label="synthetic_sha")
    tree = validate_tree_digest(source_tree_digest)
    if source != synthetic:
        raise ImpactPlannerError("source_sha 必须等于 exact synthetic_sha")
    if execution_profile not in EXECUTION_PROFILES:
        raise ImpactPlannerError("execution_profile 不受支持")
    requested_scopes = sorted(set(required_scopes))
    if any(scope not in SCOPE_NAMES for scope in requested_scopes):
        raise ImpactPlannerError("required scope override 不受支持")

    classified = classify_impacts(paths, fail_closed_empty=fail_closed_empty)
    changed_paths = list(classified["paths"])
    runtime_scopes = dict(classified["scopes"])
    # Delivery fail-closed：任一未知根级路径都不可能被证明"不影响"，全 scope 必跑。
    if any(not _known_path(path) for path in changed_paths):
        _apply_all(runtime_scopes)
    for scope in requested_scopes:
        runtime_scopes[scope] = True
    governance_closure = any(
        _matches_prefix(path, _COVERAGE_GOVERNANCE_PREFIXES)
        or _matches_prefix(path, _R4_GOVERNANCE_PREFIXES)
        for path in changed_paths
    )
    device_required = force_device or any(
        _matches_prefix(path, _DEVICE_IMPACT_PREFIXES) for path in changed_paths
    )
    if execution_profile == "promotion":
        for name in runtime_scopes:
            runtime_scopes[name] = True
        device_required = True
        governance_closure = True
    coverage_service = bool(runtime_scopes["service"] or governance_closure)
    coverage_app = bool(runtime_scopes["app"] or governance_closure)
    scopes = {
        **runtime_scopes,
        "device": device_required,
        "coverage_service": coverage_service,
        "coverage_app": coverage_app,
    }
    states = {name: "required" if required else "not_required" for name, required in scopes.items()}
    integration_depth = derive_integration_depth({"scopes": runtime_scopes})
    risk_level, risk_reasons = _derive_risk(
        changed_paths,
        scopes=runtime_scopes,
        device_required=device_required,
        execution_profile=execution_profile,
    )
    ownership_policy, ownership_digest = _load_test_ownership_policy()
    required_ids = _derive_required_ids(
        policy=ownership_policy,
        scopes=runtime_scopes,
        device_required=device_required,
        integration_depth=integration_depth,
        paths=changed_paths,
        execution_profile=execution_profile,
    )
    candidate_products = sorted(
        name for name in ("service", "app", "portal", "data") if runtime_scopes[name]
    )
    identity = planner_identity()
    plan = {
        "schema": IMPACT_PLAN_SCHEMA,
        "schema_version": IMPACT_PLAN_SCHEMA_VERSION,
        "source_sha": source,
        "base_sha": base,
        "head_sha": head,
        "synthetic_sha": synthetic,
        "source_tree_digest": tree,
        "execution_profile": execution_profile,
        "impact_planner": identity,
        "planner_digest": identity["digest"],
        "test_ownership_digest": ownership_digest,
        "changed_paths": changed_paths,
        "changed_paths_digest": classified["path_digest"],
        "risk": {"level": risk_level, "reasons": risk_reasons},
        "integration_depth": integration_depth,
        "required_ids": required_ids,
        "candidate_products": candidate_products,
        "scopes": scopes,
        "states": states,
        "policy": {
            "device_forced": bool(force_device),
            "coverage_contract_closure": governance_closure,
            "empty_diff_fail_closed": bool(fail_closed_empty),
            "required_scope_overrides": requested_scopes,
        },
    }
    return {**plan, "plan_digest": canonical_digest(plan)}


def validate_delivery_impact_plan(
    payload: Mapping[str, object],
    *,
    expected_source_sha: str = "",
    expected_tree_digest: str = "",
) -> dict[str, object]:
    """Re-derive every policy field; a self-consistent forged plan is rejected."""

    if not isinstance(payload, Mapping):
        raise ImpactPlannerError("Delivery impact plan 必须为 object")
    if payload.get("schema") != IMPACT_PLAN_SCHEMA:
        raise ImpactPlannerError("Delivery impact plan schema 不受支持")
    if payload.get("schema_version") != IMPACT_PLAN_SCHEMA_VERSION:
        raise ImpactPlannerError("Delivery impact plan schema_version 不受支持")
    source_sha = validate_exact_sha(str(payload.get("source_sha") or ""), label="source_sha")
    if expected_source_sha and source_sha != validate_exact_sha(expected_source_sha, label="expected_source_sha"):
        raise ImpactPlannerError("Delivery impact plan source_sha 漂移")
    tree_digest = validate_tree_digest(str(payload.get("source_tree_digest") or ""))
    if expected_tree_digest and tree_digest != validate_tree_digest(expected_tree_digest):
        raise ImpactPlannerError("Delivery impact plan source tree 漂移")
    paths = payload.get("changed_paths")
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ImpactPlannerError("Delivery impact plan changed_paths 非 canonical list")
    normalized = normalize_changed_paths(paths)
    if normalized != paths:
        raise ImpactPlannerError("Delivery impact plan changed_paths 未 canonicalize")
    policy = payload.get("policy")
    if not isinstance(policy, Mapping):
        raise ImpactPlannerError("Delivery impact plan policy 非 object")
    required_scope_overrides = policy.get("required_scope_overrides")
    if not isinstance(required_scope_overrides, list) or any(
        not isinstance(item, str) for item in required_scope_overrides
    ):
        raise ImpactPlannerError("Delivery impact plan required scope overrides 非法")
    rebuilt = build_delivery_impact_plan(
        normalized,
        source_sha=source_sha,
        base_sha=str(payload.get("base_sha") or ""),
        head_sha=str(payload.get("head_sha") or ""),
        synthetic_sha=str(payload.get("synthetic_sha") or ""),
        source_tree_digest=tree_digest,
        execution_profile=str(payload.get("execution_profile") or ""),
        force_device=policy.get("device_forced") is True,
        fail_closed_empty=policy.get("empty_diff_fail_closed") is True,
        required_scopes=required_scope_overrides,
    )
    if dict(payload) != rebuilt:
        raise ImpactPlannerError("Delivery impact plan policy derivation 漂移")
    return dict(payload)
