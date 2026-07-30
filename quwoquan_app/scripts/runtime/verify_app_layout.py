#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "quwoquan_app"

FORBIDDEN_EXISTING_PATHS = {
    ".cursor",
    "assistant",
    "personal_assistant",
    "node_modules",
    "package.json",
    "package-lock.json",
    "figma.config.json",
    "openspec-README.md",
    "scripts/find_team_files.js",
    "scripts/extract_figma_file_id.js",
    "scripts/quick_sync.sh",
    "scripts/run_figma_sync.sh",
    "scripts/setup_figma_config.sh",
    "scripts/sync_figma.js",
    "scripts/sync_figma.py",
    "scripts/sync_figma_enhanced.js",
}

FORBIDDEN_TRACKED_EXACT = {
    "quwoquan_app/android/local.properties",
}

FORBIDDEN_TRACKED_SEGMENTS = (
    "/.dart_tool/",
    "/.gradle/",
    "/.kotlin/",
    "/build/",
    "/node_modules/",
    "/ios/Pods/",
)
FORBIDDEN_TRACKED_NAMES = {"api", "api_integration.test"}
EXECUTABLE_MAGIC = (
    b"\x7fELF",
    b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"MZ",
)
ALLOWED_TRACKED_EXECUTABLE_PREFIXES = (
    "quwoquan_app/vendor/commercial_auth/alipay/",
    "quwoquan_app/vendor/commercial_auth/qq/",
)
REMOTE_RUNTIME_ENVS = ("alpha", "beta", "gamma", "prod")
RETIRED_RUNTIME_SEED_TOKENS = ("fixture_", "mock", "test_fixtures")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "quwoquan_app"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _remote_runtime_config_issues() -> list[str]:
    issues: list[str] = []
    for env_name in REMOTE_RUNTIME_ENVS:
        path = APP_ROOT / "configs" / env_name / "app_runtime.yaml"
        if not path.is_file():
            issues.append(f"{_rel(path)}: missing remote runtime config")
            continue
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            issues.append(f"{_rel(path)}: invalid runtime YAML: {exc}")
            continue
        if not isinstance(document, dict):
            issues.append(f"{_rel(path)}: runtime config must be a mapping")
            continue
        runtime = document.get("runtime")
        if not isinstance(runtime, dict):
            issues.append(f"{_rel(path)}: runtime mapping is required")
            continue
        if "seed" in document:
            issues.append(f"{_rel(path)}: remote runtime must not carry seed config")
        current_user = str(runtime.get("currentUserId") or "").lower()
        if any(token in current_user for token in RETIRED_RUNTIME_SEED_TOKENS):
            issues.append(
                f"{_rel(path)}: runtime.currentUserId must not reference fixture or mock data"
            )
    return issues


def app_layout_issues() -> list[str]:
    issues: list[str] = []
    for rel in sorted(FORBIDDEN_EXISTING_PATHS):
        path = APP_ROOT / rel
        if path.exists():
            issues.append(f"{_rel(path)}: retired App-local tool/config path")

    for tracked in _tracked_files():
        if tracked in FORBIDDEN_TRACKED_EXACT:
            issues.append(f"{tracked}: local machine file must not be tracked")
        if any(segment in f"/{tracked}/" for segment in FORBIDDEN_TRACKED_SEGMENTS):
            issues.append(f"{tracked}: generated/cache dependency output must not be tracked")
        path = ROOT / tracked
        if path.name in FORBIDDEN_TRACKED_NAMES or path.suffix == ".test":
            issues.append(f"{tracked}: build/test executable must not be tracked")
        if path.is_file():
            try:
                prefix = path.read_bytes()[:4]
            except OSError:
                prefix = b""
            is_executable = any(
                prefix.startswith(signature) for signature in EXECUTABLE_MAGIC
            )
            is_allowed_vendor_binary = tracked.startswith(
                ALLOWED_TRACKED_EXECUTABLE_PREFIXES
            )
            if is_executable and not is_allowed_vendor_binary:
                issues.append(f"{tracked}: executable binary must not be tracked")
    return issues + _remote_runtime_config_issues()


def main() -> int:
    issues = app_layout_issues()
    if issues:
        print("[verify_app_layout] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_app_layout] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
