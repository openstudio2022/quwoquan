#!/usr/bin/env python3
"""Enforce API-only non-production business-data provisioning.

spec_ref: specs/feature-tree/spec.md#uat-009
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_PATHS = (
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/app_alpha_dev_lite_seed_manifest.json",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/app_alpha_seed_manifest.json",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/app_beta_seed_manifest.json",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/app_gamma_seed_manifest.json",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/composition_rules.json",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_moment_channel.gamma_seed.json",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_object_cards.gamma_seed.json",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_social_graph.gamma_seed.json",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/seed_manifest.schema.json",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/source_catalog.json",
    "quwoquan_service/services/assistant-service/cmd/seed",
    "quwoquan_service/services/circle-service/cmd/seed",
    "quwoquan_service/services/user-service/cmd/seed",
    "quwoquan_service/services/user-service/cmd/acceptance-session/main.go",
    "quwoquan_service/services/user-service/internal/account/account_session/application/acceptance_subject.go",
    "quwoquan_service/services/user-service/internal/persona_management/persona/application/environmentseed/primary_persona.go",
    "quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/seedfixture/mapping.go",
    "quwoquan_service/services/content-service/cmd/jobs/seed-moment-channel",
    "quwoquan_service/services/content-service/cmd/jobs/seed-object-cards",
    "quwoquan_service/services/content-service/cmd/jobs/seed-social-graph",
    "quwoquan_ops/tests/support/environment_seeds",
)

RUNTIME_SCAN_ROOTS = (
    "quwoquan_app/configs",
    "quwoquan_app/scripts/device",
    "quwoquan_app/scripts/gamma",
    "quwoquan_ops/cli",
    "quwoquan_ops/environments",
)

FORBIDDEN_RUNTIME_TOKENS = (
    "app_alpha_seed_manifest",
    "app_beta_seed_manifest",
    "app_gamma_seed_manifest",
    "content_recommendation_moment_channel.gamma_seed",
    "content_recommendation_object_cards.gamma_seed",
    "content_recommendation_social_graph.gamma_seed",
    "go run ./services/user-service/cmd/seed",
    "go run ./services/circle-service/cmd/seed",
    "go run ./services/assistant-service/cmd/seed",
    "run_business_beta_db_seed",
    "prepare_local_provider_credentials",
    "ASSISTANT_SCENARIO_SEED_REFS",
    "--seed-refs",
)

FORBIDDEN_NONPROD_PROVIDER_TOKENS = (
    "protocol_fixture",
    "local_capture",
    "local_recorder",
    "_FIXTURE_",
)

PROD_SCAN_ROOTS = (
    "quwoquan_app/configs/prod",
    "quwoquan_ops/cli/prod",
    "quwoquan_ops/environments/prod",
    "quwoquan_service/services",
)

FORBIDDEN_PROD_TOKENS = (
    "datasetEpoch",
    "provisionRunId",
    "reconcile-nonprod-data",
)

TEXT_SUFFIXES = frozenset(
    {".dart", ".go", ".json", ".md", ".py", ".sh", ".yaml", ".yml"}
)


def _text_files(path: Path):
    if not path.exists():
        return
    candidates = (path,) if path.is_file() else path.rglob("*")
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix in TEXT_SUFFIXES:
            yield candidate


def scan_repository(root: Path) -> list[str]:
    issues: list[str] = []
    for relative in FORBIDDEN_PATHS:
        if (root / relative).exists():
            issues.append(f"retired environment business seed exists: {relative}")

    catalog = (
        root
        / "quwoquan_service/contracts/metadata/_shared/app_remote_config_catalog.yaml"
    )
    if catalog.is_file() and "id: seed_fixture" in catalog.read_text(encoding="utf-8"):
        issues.append("app_remote_config_catalog.yaml still registers seed_fixture")

    for relative in RUNTIME_SCAN_ROOTS:
        for path in _text_files(root / relative):
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in FORBIDDEN_RUNTIME_TOKENS:
                if token in text:
                    issues.append(
                        f"{path.relative_to(root).as_posix()}: forbidden runtime seed token `{token}`"
                    )

    services_root = root / "quwoquan_service/services"
    if services_root.is_dir():
        for service_root in services_root.iterdir():
            if not service_root.is_dir():
                continue
            candidates = [service_root / "deploy"]
            candidates.extend(
                service_root / "environments" / environment / "deploy"
                for environment in ("alpha", "beta", "gamma")
            )
            for candidate_root in candidates:
                for path in _text_files(candidate_root):
                    text = path.read_text(encoding="utf-8", errors="replace")
                    for token in FORBIDDEN_NONPROD_PROVIDER_TOKENS:
                        if token in text:
                            issues.append(
                                f"{path.relative_to(root).as_posix()}: "
                                f"nonprod required runtime contains in-process Provider token `{token}`"
                            )

    for relative in PROD_SCAN_ROOTS:
        base = root / relative
        for path in _text_files(base):
            normalized = path.relative_to(root).as_posix()
            if relative == "quwoquan_service/services" and "/environments/prod/" not in normalized:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in FORBIDDEN_PROD_TOKENS:
                if token in text:
                    issues.append(
                        f"{normalized}: Prod must not contain nonprod token `{token}`"
                    )
    return sorted(set(issues))


def main() -> int:
    issues = scan_repository(ROOT)
    payload = {
        "caseId": "nonprod-business-data-provisioning-purity",
        "status": "failed" if issues else "passed",
        "executed": 1,
        "skipped": 0,
        "specRefs": [
            "specs/feature-tree/spec.md#uat-009",
            "specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001",
            "specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003",
        ],
        "issues": issues,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
