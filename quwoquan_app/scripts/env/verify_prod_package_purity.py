#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_TOKENS = (
    "APP_DATA_SOURCE=mock",
    "test_fixtures",
    "seedRefs",
    "requiresSeedReset",
    ".example",
    ".test",
    "127.0.0.1",
    "10.0.2.2",
    "192.168.",
    "mock-cdn.example.com",
)
PROD_SOURCES = [
    ROOT / "quwoquan_app" / "configs" / "prod" / "app_runtime.yaml",
]
PROD_SOURCE_GLOBS = [
    ROOT.glob("quwoquan_service/services/*/configs/prod/config.yaml"),
]
PROD_ARTIFACT_GLOBS = [
    ROOT.glob("artifacts/app-env-packages/prod/**/*"),
    ROOT.glob("artifacts/service-env-packages/*/prod/**/*"),
]


def iter_text_files() -> list[Path]:
    files = [path for path in PROD_SOURCES if path.is_file()]
    for group in PROD_SOURCE_GLOBS + PROD_ARTIFACT_GLOBS:
        for path in group:
            if path.is_file():
                files.append(path)
    deduped: dict[str, Path] = {str(path): path for path in files}
    return sorted(deduped.values())


def main() -> int:
    issues: list[str] = []
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                issues.append(f"{path.relative_to(ROOT)} contains forbidden token {token!r}")

    if issues:
        print("[verify_prod_package_purity] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_prod_package_purity] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
