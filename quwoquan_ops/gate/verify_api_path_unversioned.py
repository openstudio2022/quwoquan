#!/usr/bin/env python3
"""禁止 HTTP API 路径携带 /vN、/internal/vN、/callbacks/vN 版本段。

扫描 metadata、网关、codegen、Portal、服务手写 client、App/Ops/Data 测试与
活跃特性树/门禁文档等 API 语境。

排除：媒体 object key（media/**/vN/）、第三方 URL、Go module path、
文档身份 schema 名、历史 changelog、负例合同测构造串。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROVIDER_ENDPOINT_CONTRACT_ROOT = ROOT / "quwoquan_ops/external"

VERSIONED_API = re.compile(
    r"(?:^|[\s\"'`(=\[])/(?:internal/|callbacks/)?v[0-9]+/"
)
MEDIA_OBJECT_KEY = re.compile(r"(?:^|[\s\"'`(=])media/")
IMMUTABLE_MEDIA_SLICE_ASSERTION = re.compile(
    r"(?:public\s+(?:slice|fixture)|公共媒体).*(?:canonical|唯一).*/v[0-9]+/",
    re.I,
)
THIRD_PARTY = re.compile(
    r"https?://(?:api\.openverse|api2?\.cursor|cursor\.com|openai\.com|github\.com|"
    r"restapi\.amap\.com|amap\.com)"
)
THIRD_PARTY_PATH = re.compile(
    r"""["'`]/v[0-9]+/(?:geocode|place|direction|weather|distance)/"""
)
FCM_PROVIDER_PATH = re.compile(
    r"""["'`]/v[0-9]+/projects/"""
)
GO_MODULE = re.compile(r"github\.com/.+/v[0-9]+")
SCHEMA_IDENTITY = re.compile(
    r"""(?:schemaVersion|schema)\s*[:=]\s*["'][^"']*/v?[0-9]+["']"""
)

SCAN_ROOTS = [
    "quwoquan_service/contracts",
    "quwoquan_service/internal/metadata",
    "quwoquan_service/services",
    "quwoquan_service/scripts",
    "quwoquan_ops/environments",
    "quwoquan_ops/cli",
    "quwoquan_ops/gate",
    "quwoquan_ops/portal/src",
    "quwoquan_ops/observability",
    "quwoquan_ops/tests",
    "quwoquan_app/lib/service",
    "quwoquan_app/lib/runtime",
    "quwoquan_app/packages/quwoquan_cloud_contracts",
    "quwoquan_app/configs",
    "quwoquan_app/scripts",
    "quwoquan_app/test",
    "quwoquan_data/scripts/content/release",
    "quwoquan_data/tests",
    "specs/feature-tree",
    "quwoquan_ops/policies/gates",
    ".cursor/rules",
]

SUFFIXES = {
    ".go",
    ".dart",
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".ts",
    ".tsx",
    ".sh",
    ".md",
    ".mdc",
}
EXTRA_NAMES = {"Caddyfile"}
SKIP_DIR_PARTS = {
    "node_modules",
    ".git",
    "vendor",
    "__pycache__",
    ".dart_tool",
    "test_fixtures",
    "changelog",  # historical CR narratives
}


def should_skip_path(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIR_PARTS:
        return True
    if "media" in path.parts and "test_fixtures" in path.as_posix():
        return True
    # Gate script and its contract test intentionally mention forbidden patterns.
    if path.name == "verify_api_path_unversioned.py":
        return True
    if path.name == "verify_api_path_runtime_unversioned.py":
        return True
    if path.name == "verify_entrypoint_script_paths.py":
        return True
    if path.name == "test_api_path_unversioned__contract__local_contract_test.py":
        return True
    if path.name == (
        "test_api_path_runtime_unversioned__contract__local_contract_test.py"
    ):
        return True
    if path.name == "allowed_path__contract__local_contract_test.go":
        return True
    return False


def load_external_provider_versioned_paths(
    contract_root: Path = PROVIDER_ENDPOINT_CONTRACT_ROOT,
) -> frozenset[str]:
    """Load exact provider-owned paths from canonical endpoint contracts."""
    return frozenset(load_external_provider_path_authorities(contract_root))


def load_external_provider_path_authorities(
    contract_root: Path = PROVIDER_ENDPOINT_CONTRACT_ROOT,
) -> dict[str, str]:
    """Map each exact provider path to the authority role that owns it."""
    authorities: dict[str, str] = {}
    for contract_path in sorted(contract_root.glob("*/contract/endpoints.yaml")):
        payload = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"{contract_path}: endpoint contract must be a mapping")
        if payload.get("schema") != "provider-endpoint-contract":
            raise RuntimeError(f"{contract_path}: unsupported endpoint contract schema")
        role = str(payload.get("role") or "").strip()
        if not role:
            raise RuntimeError(f"{contract_path}: role must be non-empty")
        for group_name in ("endpoints", "protectedEndpoints"):
            group = payload.get(group_name)
            if group is None:
                continue
            if not isinstance(group, dict):
                raise RuntimeError(f"{contract_path}: {group_name} must be a mapping")
            for endpoint_name, descriptor in group.items():
                if not isinstance(descriptor, dict):
                    raise RuntimeError(
                        f"{contract_path}: {endpoint_name} endpoint must be a mapping"
                    )
                path = str(descriptor.get("path") or "").strip()
                if not path:
                    continue
                if not path.startswith("/") or "//" in path or ".." in path:
                    raise RuntimeError(
                        f"{contract_path}: {endpoint_name} has an unsafe endpoint path"
                    )
                if VERSIONED_API.search(f'"{path}"'):
                    prior = authorities.get(path)
                    if prior is not None and prior != role:
                        raise RuntimeError(
                            f"{contract_path}: {path} is owned by both {prior} and {role}"
                        )
                    authorities[path] = role
    return authorities


def _references_exact_path(line: str, path: str) -> bool:
    return re.search(
        re.escape(path) + r'''(?=["'`\s,)\]}]|$)''',
        line,
    ) is not None


def _provider_reference_is_authority_scoped(
    relative_path: str,
    line: str,
    role: str,
) -> bool:
    """Permit provider paths only inside provider-facing authority boundaries."""
    rel = relative_path.replace("\\", "/")
    rel_lower = rel.lower()
    line_lower = line.lower()
    if not rel:
        return False
    if rel.startswith(f"quwoquan_ops/external/{role}/"):
        return True
    if rel.startswith("quwoquan_ops/cli/"):
        return "provider" in rel_lower or "provider" in line_lower or "sms" in rel_lower
    if rel.startswith("quwoquan_ops/tests/"):
        return "provider" in rel_lower or role in line_lower
    if rel.startswith("specs/feature-tree/"):
        return "provider" in line_lower or "替代 provider" in line_lower
    if rel.startswith("quwoquan_service/services/"):
        if "/contracts/" in rel or "/adapters/inbound/" in rel:
            return False
        if "/infrastructure/provider/" in rel or "/adapters/outbound/" in rel:
            return True
        if "/tests/" in rel:
            return (
                "provider" in rel_lower
                or "provider" in line_lower
                or "external_interaction" in rel_lower
                or "sms" in rel_lower
            )
    return False


def _third_party_path_is_authority_scoped(relative_path: str, line: str) -> bool:
    rel = relative_path.replace("\\", "/")
    rel_lower = rel.lower()
    line_lower = line.lower()
    if rel.startswith("quwoquan_ops/external/"):
        return True
    if rel.startswith("quwoquan_ops/cli/") or rel.startswith("quwoquan_ops/tests/"):
        return "provider" in rel_lower or "provider" in line_lower
    if not rel.startswith("quwoquan_service/services/"):
        return False
    if "/contracts/" in rel or "/adapters/inbound/" in rel:
        return False
    if "/infrastructure/provider/" in rel or "/adapters/outbound/" in rel:
        return True
    return "/tests/" in rel and (
        "provider" in rel_lower
        or "provider" in line_lower
        or "external_integration" in rel_lower
    )


def line_is_excluded(
    line: str,
    *,
    relative_path: str = "",
    external_provider_authorities: dict[str, str] | None = None,
) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return True
    if MEDIA_OBJECT_KEY.search(line) and re.search(r"/v[0-9]+/", line):
        if not re.search(r"""["'`\s(=]/(?:internal/|callbacks/)?v[0-9]+/""", line):
            if not re.search(r"https?://[^/\s\"']+/(?:internal/|callbacks/)?v[0-9]+/", line):
                return True
    if IMMUTABLE_MEDIA_SLICE_ASSERTION.search(line):
        return True
    if (
        THIRD_PARTY.search(line)
        or GO_MODULE.search(line)
    ):
        return True
    if (
        THIRD_PARTY_PATH.search(line) or FCM_PROVIDER_PATH.search(line)
    ) and _third_party_path_is_authority_scoped(relative_path, line):
        return True
    provider_authorities = (
        load_external_provider_path_authorities()
        if external_provider_authorities is None
        else external_provider_authorities
    )
    for path, role in provider_authorities.items():
        if not _references_exact_path(line, path):
            continue
        if _provider_reference_is_authority_scoped(relative_path, line, role):
            return True
    if SCHEMA_IDENTITY.search(line):
        return True
    if "versioned API path is forbidden" in line or "media object keys may contain" in line:
        return True
    if "VERSIONED_API.search" in line:
        return True
    # Negative assertions that forbid versioned paths.
    if "assertNotIn" in line and "/v1/" in line:
        return True
    if 'pathTemplate: "/v1/' in line and "assertNotIn" in line:
        return True
    if "/v1/" in line and "StatusNotFound" in line:
        return True
    return False


def iter_files() -> list[Path]:
    files: list[Path] = []
    for rel in SCAN_ROOTS:
        base = ROOT / rel
        if not base.exists():
            continue
        if base.is_file():
            files.append(base)
            continue
        for path in base.rglob("*"):
            if not path.is_file() or should_skip_path(path):
                continue
            if path.name in EXTRA_NAMES or path.suffix in SUFFIXES:
                files.append(path)
    return files


def main() -> int:
    failures: list[str] = []
    try:
        external_provider_authorities = load_external_provider_path_authorities()
    except (OSError, RuntimeError, yaml.YAMLError) as error:
        print(
            f"[verify_api_path_unversioned] GATE_BLOCK: {error}",
            file=sys.stderr,
        )
        return 1
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line_is_excluded(
                line,
                relative_path=rel,
                external_provider_authorities=external_provider_authorities,
            ):
                continue
            if VERSIONED_API.search(line):
                failures.append(f"{rel}:{lineno}: versioned API path is forbidden: {line.strip()}")
    if failures:
        print("[verify_api_path_unversioned] FAIL:", file=sys.stderr)
        for item in failures[:200]:
            print(f"  {item}", file=sys.stderr)
        if len(failures) > 200:
            print(f"  ... and {len(failures) - 200} more", file=sys.stderr)
        return 1
    print("[verify_api_path_unversioned] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
