#!/usr/bin/env python3
"""校验 App Cloud 商用目录治理规格与动态 Mock 清单。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MAX_MOCK_CLASSES = 24

SPEC = (
    ROOT
    / "specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md"
)
DESIGN = (
    ROOT
    / "specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md"
)
ACCEPTANCE = (
    ROOT
    / "specs/feature-tree/runtime/system-architecture-and-engineering-guide/acceptance.yaml"
)
TESTING = ROOT / "specs/03_TESTING_STRATEGY.md"
MOCK_POLICY = ROOT / "specs/gates/mock_production_separation_backlog.md"
MOCK_CHECKLIST = ROOT / "specs/gates/mock_migration_checklist.md"
BACKLOG = ROOT / "docs/outstanding_risks_backlog.md"
CHANGE_REQUEST = (
    ROOT
    / "specs/changelog/"
    "CR-20260713-088-app-cloud-commercial-directory-governance.yaml"
)
MOCK_SCAN_ROOTS = (
    ROOT / "quwoquan_app/lib/cloud",
    ROOT / "quwoquan_app/packages/quwoquan_cloud_mock/lib",
)
APP_LIB = ROOT / "quwoquan_app/lib"
CONTRACTS_PACKAGE = ROOT / "quwoquan_app/packages/quwoquan_cloud_contracts"
MOCK_PACKAGE = ROOT / "quwoquan_app/packages/quwoquan_cloud_mock"
ALPHA_RUNNER = ROOT / "quwoquan_app/runners/alpha"

MOCK_CLASS_PATTERN = re.compile(r"^\s*class\s+(Mock[A-Za-z0-9_]+)\b", re.MULTILINE)
CHECKLIST_PATTERN = re.compile(
    r"^\|[^|\n]+\|\s*`(Mock[A-Za-z0-9_]+)`\s*\|\s*\[([ xX])\]\s*\|",
    re.MULTILINE,
)


def _read(path: Path, failures: list[str]) -> str:
    if not path.is_file():
        failures.append(f"missing required file: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def discover_mock_classes(scan_roots: tuple[Path, ...]) -> set[str]:
    classes: set[str] = set()
    for scan_root in scan_roots:
        if not scan_root.is_dir():
            continue
        for dart_file in sorted(scan_root.rglob("*.dart")):
            classes.update(MOCK_CLASS_PATTERN.findall(dart_file.read_text(encoding="utf-8")))
    return classes


def checklist_mock_classes(content: str) -> set[str]:
    return {
        class_name
        for class_name, completion_mark in CHECKLIST_PATTERN.findall(content)
        if completion_mark == " "
    }


def validate_mock_inventory(
    actual: set[str],
    documented: set[str],
    *,
    max_mock_classes: int = MAX_MOCK_CLASSES,
) -> list[str]:
    failures: list[str] = []
    undocumented = sorted(actual - documented)
    stale = sorted(documented - actual)
    if undocumented:
        failures.append("undocumented Mock classes: " + ", ".join(undocumented))
    if stale:
        failures.append("stale Mock checklist entries: " + ", ".join(stale))
    if len(actual) > max_mock_classes:
        failures.append(
            "Mock class budget increased: "
            f"{len(actual)} > {max_mock_classes}"
        )
    return failures


def validate_report_zero_compat(
    *,
    app_sources: dict[str, str],
    mock_sources: dict[str, str],
    mock_pubspec: str,
    contract_source: str,
    runner_source: str,
) -> list[str]:
    failures: list[str] = []
    forbidden_symbols = ("ReportRepository", "reportRepositoryProvider")
    for path, content in app_sources.items():
        for symbol in forbidden_symbols:
            if symbol in content:
                failures.append(f"{path}: retired Report symbol {symbol}")
    for path, content in mock_sources.items():
        for import_prefix in (
            "package:quwoquan_app/",
            "package:flutter/",
            "package:flutter_riverpod/",
        ):
            if import_prefix in content:
                failures.append(
                    f"{path}: quwoquan_cloud_mock must not import {import_prefix}"
                )
    for dependency in ("quwoquan_app:", "flutter_riverpod:"):
        if dependency in mock_pubspec:
            failures.append(
                f"quwoquan_cloud_mock/pubspec.yaml retains dependency {dependency}"
            )
    if "\n  flutter:\n" in mock_pubspec:
        failures.append(
            "quwoquan_cloud_mock/pubspec.yaml retains Flutter SDK dependency"
        )
    if "quwoquan_cloud_contracts:" not in mock_pubspec:
        failures.append(
            "quwoquan_cloud_mock/pubspec.yaml missing contracts dependency"
        )
    if "abstract interface class ContentReportCommandWriter" not in contract_source:
        failures.append("pure contracts missing ContentReportCommandWriter")
    if "surfaceId" in contract_source or "routeId" in contract_source:
        failures.append("Report business command leaks invocation metadata")
    if "buildAlphaCloudOverrides" not in runner_source:
        failures.append("alpha runner does not own Cloud override composition")
    report_surfaces = {
        "quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_report_actions.dart": (
            "homeFeedContentReportCommandWriterProvider"
        ),
        "quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_engagement_actions.dart": (
            "workBrowserContentReportCommandWriterProvider"
        ),
    }
    for path, provider in report_surfaces.items():
        source = app_sources.get(path, "")
        if provider not in source:
            failures.append(f"{path}: missing typed report command provider")
        if "BehaviorAction.report" in source:
            failures.append(f"{path}: retains report behavior dual-write")
    return failures


def validate_p0_fail_closed(
    *,
    service_sources: dict[str, str],
    runtime_auth_source: str,
    seed_box_deployment: str,
    prod_roots: dict[str, str],
    gamma_compose: str = "",
) -> list[str]:
    failures: list[str] = []
    for service in ("user", "content", "chat", "assistant"):
        source = service_sources.get(service, "")
        for token in (
            "rtauth.LoadAccessTokenConfig(",
            "rtauth.NewHS256Verifier(",
            "rtauth.Middleware(rtauth.MiddlewareConfig{",
        ):
            if token not in source:
                failures.append(
                    f"{service}-service missing P0 auth containment token {token}"
                )
    required_tokens = {
        "content": (
            "RequireSensitiveOperationPrincipal",
            "rtauth.RequireGeneratedOperationAuthorization(",
        ),
        "chat": (
            "rtauth.RequireGeneratedOperationAuthorization(",
            'operationsecurity.ForDomain("chat")',
        ),
        "assistant": ("requireVerifiedAccount",),
        "rtc": (
            "rtauth.RequireGeneratedOperationAuthorization(",
            'operationsecurity.ForDomain("rtc")',
        ),
        "notification": (
            "rtauth.RequireGeneratedOperationAuthorization(",
            'operationsecurity.ForDomain("notification")',
        ),
        "ops": (
            "rtauth.RequireGeneratedOperationAuthorization(",
            'operationsecurity.ForDomain("ops")',
        ),
        # platform-ops：ContractGraph 已登记 operation 走 Enforce fail-closed，
        # 未登记的控制面对象路径由 requireControlPlanePrincipal 拒绝匿名触达
        # （迁移期底线，随 business-object closure 收敛为全量 Require）。
        "platform_ops": (
            "rtauth.EnforceGeneratedOperationAuthorization(",
            'operationsecurity.ForDomain("ops")',
            "requireControlPlanePrincipal(",
        ),
    }
    for service, tokens in required_tokens.items():
        source = service_sources.get(service, "")
        for token in tokens:
            if token not in source:
                failures.append(
                    f"{service}-service missing P0 operation guard {token}"
                )
        if "ProtectGeneratedReadyOperations" in source:
            failures.append(
                f"{service}-service retains bypassable ready-only operation guard"
            )
    if "ProtectGeneratedReadyOperations" in runtime_auth_source:
        failures.append("runtime auth retains bypassable ready-only operation guard")
    for token in (
        "clearClientIdentityHeaders",
        "clientAccountIDHeader",
        "clientPersonaIDHeader",
        "clientDeviceActorHdr",
        "untrustedUserIDHeader",
        "untrustedActorHeader",
    ):
        if token not in runtime_auth_source:
            failures.append(f"runtime auth missing trusted-header guard {token}")
    for key in (
        "AUTH_JWT_SECRET",
        "AUTH_JWT_ISSUER",
        "AUTH_JWT_AUDIENCE",
        "AUTH_JWT_TOKEN_VERSION",
        "AUTH_DEVICE_TICKET_SECRET",
        "AUTH_DEVICE_TICKET_ISSUER",
        "AUTH_DEVICE_TICKET_AUDIENCE",
        "AUTH_DEVICE_TICKET_TOKEN_VERSION",
    ):
        if f"- name: {key}" not in seed_box_deployment:
            failures.append(f"seed-box missing required auth config {key}")
        if re.search(
            rf"key:\s*{key}\s*\n\s*optional:\s*true",
            seed_box_deployment,
        ):
            failures.append(f"seed-box {key} remains optional")
    if gamma_compose:
        try:
            compose = yaml.safe_load(gamma_compose) or {}
        except yaml.YAMLError as exc:
            failures.append(f"gamma-local compose auth wiring cannot be parsed: {exc}")
            compose = {}
        services = compose.get("services") if isinstance(compose, dict) else {}
        if not isinstance(services, dict):
            failures.append("gamma-local compose has no services mapping")
            services = {}
        access_keys = (
            "AUTH_JWT_SECRET",
            "AUTH_JWT_ISSUER",
            "AUTH_JWT_AUDIENCE",
            "AUTH_JWT_TOKEN_VERSION",
        )
        device_keys = (
            "AUTH_DEVICE_TICKET_SECRET",
            "AUTH_DEVICE_TICKET_ISSUER",
            "AUTH_DEVICE_TICKET_AUDIENCE",
            "AUTH_DEVICE_TICKET_TOKEN_VERSION",
        )
        expected = {
            "content-service": access_keys + device_keys,
            "integration-service": access_keys + device_keys,
            "user-service": access_keys,
            "chat-service": access_keys,
            "assistant-service": access_keys,
        }
        for service, keys in expected.items():
            spec = services.get(service) if isinstance(services, dict) else None
            environment = spec.get("environment") if isinstance(spec, dict) else None
            if not isinstance(environment, dict):
                failures.append(f"gamma-local {service} missing environment mapping")
                continue
            for key in keys:
                value = environment.get(key)
                if not isinstance(value, str) or ":?" not in value:
                    failures.append(
                        f"gamma-local {service} {key} must be required host configuration"
                    )
    for path, content in prod_roots.items():
        for forbidden in (
            "realtime-gateway/deploy",
            "rtc-service/deploy",
            "product-ops-service/deploy",
        ):
            if forbidden in content:
                failures.append(
                    f"{path}: unauthenticated P0 workload remains wired: {forbidden}"
                )
    return failures


def main() -> int:
    failures: list[str] = []
    required_tokens = {
        SPEC: (
            "App Cloud",
            "go-domain-source",
            "deployment-package",
            "重新裁决 aggregate",
        ),
        DESIGN: (
            "App Cloud 合同交接与单写权",
            "App Cloud 目标分层",
            "quwoquan_cloud_mock",
            "服务目录资产 profile",
        ),
        ACCEPTANCE: ("SIT7:", "cloud_commercial_directory_governance"),
        TESTING: (
            "generated client/Remote adapter",
            "kernel/AOT",
            "路径存在",
        ),
        MOCK_POLICY: (
            "历史延期项已经进入执行",
            "production Remote composition",
            "合计 31 个",
            "*CommandWriter/*Query",
        ),
        CHANGE_REQUEST: (
            "CR-20260713-088-app-cloud-commercial-directory-governance",
            "status: in_progress",
        ),
    }
    contents: dict[Path, str] = {}
    for path, tokens in required_tokens.items():
        content = _read(path, failures)
        contents[path] = content
        for token in tokens:
            if token not in content:
                failures.append(
                    f"{path.relative_to(ROOT)}: missing governance token {token!r}"
                )

    backlog = _read(BACKLOG, failures)
    for index in range(1, 11):
        risk_id = f"R-CLOUD{index:02d}"
        if risk_id not in backlog:
            failures.append(f"{BACKLOG.relative_to(ROOT)}: missing {risk_id}")

    checklist = _read(MOCK_CHECKLIST, failures)
    actual_mocks = discover_mock_classes(MOCK_SCAN_ROOTS)
    documented_mocks = checklist_mock_classes(checklist)
    failures.extend(validate_mock_inventory(actual_mocks, documented_mocks))

    report_contract = _read(
        CONTRACTS_PACKAGE / "lib/src/content/report_commands.dart",
        failures,
    )
    mock_pubspec = _read(MOCK_PACKAGE / "pubspec.yaml", failures)
    runner_composition = _read(
        ALPHA_RUNNER / "lib/alpha_cloud_composition.dart",
        failures,
    )
    app_sources = {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in sorted(APP_LIB.rglob("*.dart"))
    }
    mock_sources = {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in sorted((MOCK_PACKAGE / "lib").rglob("*.dart"))
    }
    failures.extend(
        validate_report_zero_compat(
            app_sources=app_sources,
            mock_sources=mock_sources,
            mock_pubspec=mock_pubspec,
            contract_source=report_contract,
            runner_source=runner_composition,
        )
    )
    service_sources = {
        "user": _read(
            ROOT / "quwoquan_service/services/user-service/cmd/api/main.go",
            failures,
        ),
        "content": "\n".join(
            (
                _read(
                    ROOT / "quwoquan_service/services/content-service/cmd/api/main.go",
                    failures,
                ),
                _read(
                    ROOT
                    / "quwoquan_service/services/content-service/cmd/api/"
                    "main_http_runtime.go",
                    failures,
                ),
                _read(
                    ROOT
                    / "quwoquan_service/services/content-service/internal/adapters/http/"
                    "sensitive_operation_guard.go",
                    failures,
                ),
            )
        ),
        "chat": _read(
            ROOT / "quwoquan_service/services/chat-service/cmd/api/main.go",
            failures,
        ),
        "assistant": "\n".join(
            (
                _read(
                    ROOT / "quwoquan_service/services/assistant-service/cmd/api/main.go",
                    failures,
                ),
                _read(
                    ROOT
                    / "quwoquan_service/services/assistant-service/internal/adapters/http/"
                    "handler.go",
                    failures,
                ),
            )
        ),
        "rtc": _read(
            ROOT / "quwoquan_service/services/rtc-service/cmd/api/main.go",
            failures,
        ),
        "notification": _read(
            ROOT / "quwoquan_service/services/notification-service/cmd/api/main.go",
            failures,
        ),
        "ops": _read(
            ROOT / "quwoquan_service/services/product-ops-service/cmd/api/main.go",
            failures,
        ),
        "platform_ops": _read(
            ROOT / "quwoquan_service/services/platform-ops-service/cmd/api/main.go",
            failures,
        ),
    }
    prod_root_paths = (
        "aliyun-prod",
        "volcengine-prod",
        "huaweicloud-prod",
    )
    failures.extend(
        validate_p0_fail_closed(
            service_sources=service_sources,
            runtime_auth_source=_read(
                ROOT / "quwoquan_service/runtime/auth/middleware.go",
                failures,
            ),
            seed_box_deployment=_read(
                ROOT
                / "quwoquan_service/services/seed-box/deploy/kustomize/base/"
                "deployment.yaml",
                failures,
            ),
            prod_roots={
                name: _read(
                    ROOT
                    / "quwoquan_ops/environments/kustomization"
                    / name
                    / "kustomization.yaml",
                    failures,
                )
                for name in prod_root_paths
            },
            gamma_compose=_read(
                ROOT
                / "quwoquan_ops/environments/compose/"
                "docker-compose.gamma-local.yaml",
                failures,
            ),
        )
    )

    if failures:
        for failure in failures:
            print(f"[cloud-governance] FAIL: {failure}")
        return 1

    print(
        "[cloud-governance] OK: architecture decision and non-regression checks passed; "
        f"commercial migration remains partial; Mock inventory={len(actual_mocks)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
