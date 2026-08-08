#!/usr/bin/env python3
"""Select L0 commit-gate static checks and impacted tests from changed paths."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TEST_ROOT = ROOT / "quwoquan_app" / "test" / "local_contract"

DEFAULT_FLUTTER_CAP = 40
MIN_FLUTTER_CAP = 24

SMOKE_STATIC = [
    "verify-app-mock-isolation",
    "verify-app-cloud-package-boundaries",
    "verify-app-login-entry-loop",
]

PAGEFLIP_PREFIXES = (
    "quwoquan_app/lib/design_system/pageflip/",
    "quwoquan_app/lib/service/content_service/content/post/presentation/article_reader/pageflip/",
    "quwoquan_app/test/local_contract/design_system/pageflip/",
    "quwoquan_app/test/local_contract/service/content_service/content/post/works_image_book_pageflip_journey__local_contract_test.dart",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Explicit changed path relative to repo root. Repeatable.",
    )
    parser.add_argument(
        "--use-staged",
        action="store_true",
        help="Read paths from git diff --cached --name-only.",
    )
    parser.add_argument(
        "--flutter-cap",
        type=int,
        default=0,
        help="Max Flutter test files (0 = auto from CPU).",
    )
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    return parser.parse_args()


def staged_files() -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def cpu_count() -> int:
    try:
        return max(1, os.cpu_count() or 1)
    except Exception:
        return 1


def flutter_cap(explicit: int) -> int:
    if explicit > 0:
        return explicit
    cores = cpu_count()
    if cores < 6:
        return MIN_FLUTTER_CAP
    return DEFAULT_FLUTTER_CAP


def classify(paths: list[str]) -> dict[str, bool]:
    flags = {
        "has_service": False,
        "has_app": False,
        "has_data": False,
        "has_ops": False,
        "has_specs": False,
        "has_portal": False,
        "has_contracts": False,
        "has_app_contracts": False,
        "has_pageflip": False,
    }
    for path in paths:
        if path.startswith("quwoquan_service/"):
            flags["has_service"] = True
            if "/contracts/" in path or path.startswith(
                "quwoquan_service/contracts/"
            ):
                flags["has_contracts"] = True
        if path.startswith("quwoquan_app/"):
            flags["has_app"] = True
            if "contracts" in path or path.startswith(
                "quwoquan_app/packages/quwoquan_cloud_contracts/"
            ):
                flags["has_app_contracts"] = True
        if path.startswith("quwoquan_data/"):
            flags["has_data"] = True
        if path.startswith("quwoquan_ops/") or path.startswith("specs/"):
            flags["has_ops"] = True
        if path.startswith("specs/"):
            flags["has_specs"] = True
        if path.startswith("quwoquan_ops/portal/"):
            flags["has_portal"] = True
        if any(path.startswith(prefix) for prefix in PAGEFLIP_PREFIXES):
            flags["has_pageflip"] = True
    return flags


def static_checks(flags: dict[str, bool]) -> list[str]:
    checks = [
        "branch_policy",
        "feature_tree",
        "python_script_governance",
        "entrypoint_script_paths",
    ]
    if flags["has_service"] or flags["has_ops"]:
        checks.append("service_architecture")
    if flags["has_app"] or flags["has_app_contracts"]:
        checks.extend(
            [
                "app_generated_manifest",
                "app_contract_handoff",
                *SMOKE_STATIC,
            ]
        )
    if flags["has_contracts"] or flags["has_service"]:
        checks.extend(["metadata_contract", "commercial_contract"])
    if flags["has_pageflip"]:
        checks.append("pageflip_backward_mainline")
    if flags["has_data"]:
        checks.append("data_verify")
    # de-dupe preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in checks:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def map_app_path_to_tests(path: str) -> list[Path]:
    if not path.startswith("quwoquan_app/"):
        return []
    rel = path.removeprefix("quwoquan_app/")
    candidates: list[Path] = []
    if rel.startswith("test/local_contract/") and rel.endswith("_test.dart"):
        candidate = ROOT / "quwoquan_app" / rel
        if candidate.is_file():
            return [candidate]
    if rel.startswith("lib/"):
        # lib/service/chat_service/chat/conversation/foo.dart -> test/local_contract/service/chat_service/chat/conversation/**
        without_lib = rel.removeprefix("lib/")
        parts = Path(without_lib).parts
        if parts:
            # Try progressively shorter directory prefixes under local_contract.
            for depth in range(min(len(parts), 4), 0, -1):
                probe = APP_TEST_ROOT.joinpath(*parts[:depth])
                if probe.is_dir():
                    candidates.extend(sorted(probe.rglob("*_test.dart")))
                    break
                if probe.with_name(probe.name + "__local_contract_test.dart").is_file():
                    candidates.append(
                        probe.with_name(probe.name + "__local_contract_test.dart")
                    )
                    break
    return candidates


def select_flutter_tests(paths: list[str], cap: int) -> tuple[list[str], list[str]]:
    selected: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        for test_path in map_app_path_to_tests(path):
            if test_path not in seen:
                seen.add(test_path)
                selected.append(test_path)
    # Prefer tests whose path shares more segments with changed files.
    def score(test_path: Path) -> tuple[int, str]:
        rel = str(test_path.relative_to(ROOT))
        best = 0
        for changed in paths:
            shared = 0
            for a, b in zip(rel.split("/"), changed.split("/"), strict=False):
                if a == b:
                    shared += 1
                else:
                    break
            best = max(best, shared)
        return (-best, rel)

    selected.sort(key=score)
    kept = selected[:cap]
    deferred = selected[cap:]
    return (
        [str(p.relative_to(ROOT / "quwoquan_app")) for p in kept],
        [str(p.relative_to(ROOT)) for p in deferred],
    )


def select_go_services(paths: list[str]) -> list[str]:
    services: list[str] = []
    seen: set[str] = set()
    for path in paths:
        prefix = "quwoquan_service/services/"
        if not path.startswith(prefix):
            continue
        rest = path.removeprefix(prefix)
        svc = rest.split("/", 1)[0]
        if not svc or svc in seen:
            continue
        if (ROOT / "quwoquan_service" / "services" / svc).is_dir():
            seen.add(svc)
            services.append(svc)
    return services


def select_pytest_paths(paths: list[str]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for path in paths:
        for root in ("quwoquan_data/tests/local_contract", "quwoquan_ops/tests/local_contract"):
            if path.startswith(root + "/") and path.endswith(".py"):
                # A staged deletion still shows up as a changed path; handing it to
                # pytest aborts the whole run with "file or directory not found".
                if path not in seen and (ROOT / path).exists():
                    seen.add(path)
                    selected.append(path)
            elif path.startswith(root.split("/tests/")[0] + "/"):
                # Map source tree touch to corresponding tests dir if present.
                domain = root
                if domain not in seen and (ROOT / domain).is_dir():
                    # Only add whole domain once when non-test source under domain changes.
                    if "/tests/" not in path:
                        seen.add(domain)
                        selected.append(domain)
    return selected[:80]


def build_plan(paths: list[str], cap: int) -> dict:
    flags = classify(paths)
    flutter_tests, deferred = select_flutter_tests(paths, cap)
    return {
        "changed_files": paths,
        "flags": flags,
        "static_checks": static_checks(flags),
        "flutter_tests": flutter_tests,
        "deferred_to_ci": deferred,
        "flutter_cap": cap,
        "go_services": select_go_services(paths),
        "pytest_paths": select_pytest_paths(paths),
        "run_portal": flags["has_portal"] and not (
            flags["has_app"] or flags["has_service"] or flags["has_data"]
        ),
        "forbidden": ["make gate", "gate_repo --scope all", "full local_contract"],
    }


def main() -> int:
    args = parse_args()
    paths = list(args.changed_file)
    if args.use_staged or not paths:
        paths = staged_files() if args.use_staged or not paths else paths
    if not paths and args.use_staged:
        paths = staged_files()
    cap = flutter_cap(args.flutter_cap)
    plan = build_plan(paths, cap)
    if args.format == "json":
        json.dump(plan, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(f"FLUTTER_CAP={plan['flutter_cap']}")
        print(f"HAS_APP={str(plan['flags']['has_app']).lower()}")
        print(f"HAS_SERVICE={str(plan['flags']['has_service']).lower()}")
        print(f"HAS_DATA={str(plan['flags']['has_data']).lower()}")
        print(f"HAS_PAGEFLIP={str(plan['flags']['has_pageflip']).lower()}")
        print(f"FLUTTER_COUNT={len(plan['flutter_tests'])}")
        print(f"DEFERRED_COUNT={len(plan['deferred_to_ci'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
