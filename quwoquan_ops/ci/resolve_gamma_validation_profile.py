#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "quwoquan_ops" / "environments" / "gamma" / "validation_suites.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve gamma validation profile defaults for workflows and CI scripts.",
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--github-output", default="")
    parser.add_argument("--output-format", choices=("json", "shell"), default="json")
    return parser.parse_args()


def load_profile(profile_name: str) -> dict[str, Any]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    profiles = registry.get("profiles") or {}
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise SystemExit(f"unknown gamma validation profile: {profile_name}")
    return profile


def resolve_payload(profile_name: str) -> dict[str, Any]:
    profile = load_profile(profile_name)
    device_matrix = profile.get("deviceMatrix")
    if not isinstance(device_matrix, dict):
        device_matrix = {}
    smoke_cases = [str(item) for item in profile.get("smokeCases") or [] if str(item).strip()]
    ui_journeys = [str(item) for item in profile.get("uiJourneys") or [] if str(item).strip()]
    envs = [str(item) for item in device_matrix.get("envs") or [] if str(item).strip()]
    matrix_kinds = [
        str(item)
        for item in device_matrix.get("matrixKinds") or []
        if str(item).strip()
    ]
    require_all_platforms = bool(device_matrix.get("requireAllPlatforms", False))
    assistant_smoke_profile = (
        "full_semantic" if "assistant_ui_semantic_smoke" in smoke_cases else "ui_sanity"
    )
    return {
        "profile": profile_name,
        "description": str(profile.get("description", "")).strip(),
        "readiness_blocking": bool(profile.get("readinessBlocking", False)),
        "smoke_cases": smoke_cases,
        "smoke_cases_blocking": bool(profile.get("smokeCasesBlocking", False)),
        "ui_journeys": ui_journeys,
        "device_envs": envs,
        "matrix_kinds": matrix_kinds,
        "default_matrix_kind": matrix_kinds[0] if matrix_kinds else "",
        "require_all_platforms": require_all_platforms,
        "allow_missing_platforms": not require_all_platforms,
        "assistant_smoke_profile": assistant_smoke_profile,
    }


def write_github_output(path: Path, payload: dict[str, Any]) -> None:
    def emit_bool(value: bool) -> str:
        return "true" if value else "false"

    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"profile={payload['profile']}\n")
        handle.write(f"description={payload['description']}\n")
        handle.write(
            f"readiness_blocking={emit_bool(bool(payload['readiness_blocking']))}\n"
        )
        handle.write(
            "smoke_cases_json="
            + json.dumps(payload["smoke_cases"], ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )
        handle.write(
            f"smoke_cases_blocking={emit_bool(bool(payload['smoke_cases_blocking']))}\n"
        )
        handle.write(
            "ui_journeys_json="
            + json.dumps(payload["ui_journeys"], ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )
        handle.write(
            "device_env_json="
            + json.dumps(payload["device_envs"], ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )
        handle.write(
            "matrix_kinds_json="
            + json.dumps(payload["matrix_kinds"], ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )
        handle.write(f"default_matrix_kind={payload['default_matrix_kind']}\n")
        handle.write(
            "require_all_platforms="
            + emit_bool(bool(payload["require_all_platforms"]))
            + "\n"
        )
        handle.write(
            "allow_missing_platforms="
            + emit_bool(bool(payload["allow_missing_platforms"]))
            + "\n"
        )
        handle.write(
            f"assistant_smoke_profile={payload['assistant_smoke_profile']}\n"
        )


def print_shell(payload: dict[str, Any]) -> None:
    def shell_bool(value: bool) -> str:
        return "true" if value else "false"

    print(f"PROFILE={payload['profile']}")
    print(f"DESCRIPTION={json.dumps(payload['description'], ensure_ascii=False)}")
    print(f"READINESS_BLOCKING={shell_bool(bool(payload['readiness_blocking']))}")
    print(
        "SMOKE_CASES_JSON="
        + json.dumps(payload["smoke_cases"], ensure_ascii=False, separators=(",", ":"))
    )
    print(
        "SMOKE_CASES_BLOCKING="
        + shell_bool(bool(payload["smoke_cases_blocking"]))
    )
    print(
        "UI_JOURNEYS_JSON="
        + json.dumps(payload["ui_journeys"], ensure_ascii=False, separators=(",", ":"))
    )
    print(
        "DEVICE_ENV_JSON="
        + json.dumps(payload["device_envs"], ensure_ascii=False, separators=(",", ":"))
    )
    print(
        "MATRIX_KINDS_JSON="
        + json.dumps(payload["matrix_kinds"], ensure_ascii=False, separators=(",", ":"))
    )
    print(f"DEFAULT_MATRIX_KIND={payload['default_matrix_kind']}")
    print(
        "REQUIRE_ALL_PLATFORMS="
        + shell_bool(bool(payload["require_all_platforms"]))
    )
    print(
        "ALLOW_MISSING_PLATFORMS="
        + shell_bool(bool(payload["allow_missing_platforms"]))
    )
    print(f"ASSISTANT_SMOKE_PROFILE={payload['assistant_smoke_profile']}")


def main() -> int:
    args = parse_args()
    payload = resolve_payload(args.profile)
    if args.github_output:
        write_github_output(Path(args.github_output), payload)
    if args.output_format == "shell":
        print_shell(payload)
    else:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
