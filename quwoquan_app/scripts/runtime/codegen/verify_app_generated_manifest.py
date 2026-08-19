#!/usr/bin/env python3
"""验证 App-only emitter 固定输入与可重建输出清单。"""

from __future__ import annotations


import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = REPO_ROOT
APP = ROOT / "quwoquan_app"
SERVICE = ROOT / "quwoquan_service"
GRAPH = SERVICE / "generated/contract_graph.json"
LOCK = APP / "tool/cloud_codegen/contract_graph.lock.json"
MANIFEST = APP / "tool/cloud_codegen/generated_manifest.json"
SHELL_MANIFEST = (
    APP / "tool/shell_navigation_codegen/generated_manifest.json"
)
GENERATOR = "app-only-emitter"
SHELL_GENERATOR = "tools/codegen_app_metadata"
SHELL_OWNER = "app-shell-navigation-emitter"
SHELL_RESPONSIBILITY = "shell-navigation-metadata-only"
SHELL_OUTPUT_PREFIX = "lib/runtime/shell/navigation/generated/"
SHELL_INPUTS = frozenset(
    {
        "_shared/app_routes.yaml",
        "_shared/app_pages.yaml",
        "_shared/ui_surfaces.yaml",
        "_shared/link_templates.yaml",
    }
)
ALLOWED_PREFIXES = (
    "lib/service/assistant_service/assistant/assistant_preference/domain/generated/",
    "lib/service/assistant_service/assistant/assistant_run/domain/generated/",
    "lib/service/assistant_service/assistant/assistant_turn_view/domain/generated/",
    "lib/service/circle_service/circle_management/circle/presentation/generated/",
    "lib/service/content_service/content/post/application/generated/",
    "lib/service/content_service/content/post/application/public/generated/",
    "lib/service/content_service/content/post/domain/generated/",
    "lib/service/content_service/content/post/presentation/generated/",
    "lib/service/content_service/media/media_asset/application/generated/",
    "lib/service/content_service/media/media_upload_session/application/generated/",
    "lib/service/entity_service/entity_homepage/homepage/application/public/generated/",
    "lib/service/recommendation_service/recommendation/"
    "recommendation_feature_profile_view/application/generated/",
    "lib/service/recommendation_service/recommendation/"
    "recommendation_feature_profile_view/presentation/generated/",
    "lib/runtime/errors/generated/",
    "lib/runtime/transport/generated/",
    "lib/service/search_service/search/search_index_view/application/generated/",
    "lib/service/search_service/search/search_index_view/presentation/generated/",
    "lib/service/user_service/account/user_account/application/public/generated/",
    "packages/quwoquan_cloud_contracts/lib/src/generated/",
    "packages/quwoquan_cloud_contracts/lib/generated/",
)
ALLOWED_EXACT_PATHS = frozenset(
    {
        "lib/service/content_service/content/post/presentation/generated/content_ui_config.g.dart",
        "lib/runtime/transport/generated/cloud_api_defaults.g.dart",
        "lib/service/content_service/content/post/adapters/generated/article_detail_wire_keys.g.dart",
        "lib/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/generated/impact_help_type_metadata.g.dart",
        "lib/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/generated/intersection_display_metadata.g.dart",
        "lib/runtime/observability/generated/app_telemetry_catalog.g.dart",
        "packages/quwoquan_cloud_contracts/lib/src/rtc/"
        "rtc_operation_contracts.g.dart",
    }
)
RETIRED_GENERATED_PATHS = frozenset(
    {
        "lib/service/entity_service/entity_homepage/homepage/presentation/generated/"
        "homepage_ui_config.g.dart",
        "lib/service/content_service/content/post/adapters/generated/"
        "content_post_immersive_wire_keys.g.dart",
        "lib/service/content_service/content/post/application/generated/"
        "content_metadata.g.dart",
        "lib/service/recommendation_service/recommendation/"
        "recommendation_feature_profile_view/presentation/generated/"
        "intersection_kind_metadata.g.dart",
        "lib/service/search_service/search/search_index_view/application/generated/"
        "search_contract.g.dart",
        "lib/service/search_service/search/search_index_view/application/generated/"
        "search_registry.g.dart",
        "lib/app/navigation/generated/app_pages.g.dart",
        "lib/app/navigation/generated/app_route_paths.g.dart",
        "lib/app/navigation/generated/app_ui_surfaces.g.dart",
        "lib/app/navigation/generated/page_access_internal_routes.g.dart",
        "lib/application/content/media/generated/"
        "content_image_variant_policy.g.dart",
        "lib/application/content/media/generated/"
        "content_media_upload_policy.g.dart",
        "lib/cloud/assistant/generated/assistant_errors.g.dart",
        "lib/cloud/chat/generated/chat_errors.g.dart",
        "lib/cloud/circle/generated/circle_errors.g.dart",
        "lib/cloud/circle/generated/circle_membership_errors.g.dart",
        "lib/cloud/content/generated/content_errors.g.dart",
        "lib/cloud/content/generated/content_behaviors.g.dart",
        "lib/cloud/content/generated/content_privacy_policy.g.dart",
        "lib/cloud/content/generated/content_publication_policy.g.dart",
        "lib/cloud/entity/generated/entity_errors.g.dart",
        "lib/cloud/rtc/generated/rtc_errors.g.dart",
        "lib/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart",
        "lib/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/auth/auth_policy.g.dart",
        "lib/cloud/runtime/generated/chat/chat_api_metadata.g.dart",
        "lib/cloud/runtime/generated/chat/chat_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/circle/circle_api_metadata.g.dart",
        "lib/cloud/runtime/generated/circle/circle_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart",
        "lib/cloud/runtime/generated/circle/circle_category_tab_defaults.dart",
        "lib/cloud/runtime/generated/circle/circle_category_tab_order.dart",
        "lib/cloud/runtime/generated/circle/circle_ui_config.g.dart",
        "lib/cloud/runtime/generated/app_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/content/content_api_metadata.g.dart",
        "lib/cloud/runtime/generated/content/content_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/content/post_read_presentation.g.dart",
        "lib/cloud/runtime/generated/content/report_create_request_wire.g.dart",
        "lib/cloud/runtime/generated/content/post_read_surface_id.g.dart",
        "lib/cloud/runtime/generated/entity/entity_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/entity/entity_api_metadata.g.dart",
        "lib/cloud/runtime/generated/entity/homepage_ui_config.g.dart",
        "lib/cloud/runtime/generated/integration/integration_api_metadata.g.dart",
        "lib/cloud/runtime/generated/integration/integration_location_errors.g.dart",
        "lib/cloud/runtime/generated/integration/integration_location_metadata.g.dart",
        "lib/cloud/runtime/generated/integration/"
        "integration_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/link_templates.g.dart",
        "lib/cloud/runtime/generated/notification/notification_errors.g.dart",
        "lib/cloud/runtime/generated/notification/notification_api_metadata.g.dart",
        "lib/cloud/runtime/generated/notification/"
        "notification_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart",
        "lib/cloud/runtime/generated/ops/ops_api_metadata.g.dart",
        "lib/cloud/runtime/generated/ops/ops_event_record_errors.g.dart",
        "lib/cloud/runtime/generated/ops/ops_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/realtime/realtime_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart",
        "lib/cloud/runtime/generated/recommendation/"
        "recommendation_api_metadata.g.dart",
        "lib/cloud/runtime/generated/recommendation/"
        "recommendation_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/rtc/rtc_api_metadata.g.dart",
        "lib/cloud/runtime/generated/rtc/rtc_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/search/search_api_metadata.g.dart",
        "lib/cloud/runtime/generated/search/search_errors.g.dart",
        "lib/cloud/runtime/generated/search/search_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/tag/tag_api_metadata.g.dart",
        "lib/cloud/runtime/generated/tag/tag_errors.g.dart",
        "lib/cloud/runtime/generated/tag/tag_request_page_ids.g.dart",
        "lib/cloud/runtime/generated/user/user_api_metadata.g.dart",
        "lib/cloud/runtime/generated/user/user_errors.g.dart",
        "lib/cloud/runtime/generated/user/user_request_page_ids.g.dart",
        "lib/cloud/user/generated/user_profile_ui_config.g.dart",
        "lib/service/recommendation_service/recommendation/"
        "recommendation_feature_profile_view/application/generated/"
        "impact_help_type_metadata.g.dart",
        "packages/quwoquan_cloud_contracts/lib/src/rtc/"
        "call_session_dtos.g.dart",
    }
)
RETIRED_GENERATED_PREFIXES = (
    "lib/assistant/generated/",
)
GENERATOR_ROOT = SERVICE / "tools/codegen_app_metadata"
DOMAIN_TYPED_OWNER_PATTERN = re.compile(
    r"^packages/quwoquan_cloud_contracts/lib/src/"
    r"(?P<domain>[a-z][a-z0-9_]*)/"
    r"(?P<artifact>[a-z][a-z0-9_]*)_contracts\.g\.dart$"
)


def is_allowed_generated_path(relative: str) -> bool:
    if relative in RETIRED_GENERATED_PATHS or relative.startswith(
        RETIRED_GENERATED_PREFIXES
    ):
        return False
    return relative in ALLOWED_EXACT_PATHS or relative.startswith(
        ALLOWED_PREFIXES
    ) or bool(
        DOMAIN_TYPED_OWNER_PATTERN.fullmatch(relative)
    )


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise AssertionError(f"缺少文件: {path.relative_to(ROOT)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path.relative_to(ROOT)} 必须是 JSON object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_manifest(
    app_root: Path,
    manifest: dict,
    lock: dict,
    delegated_paths: frozenset[str] = frozenset(),
) -> set[str]:
    for retired_field in ("version", "schemaVersion", "registryRevision"):
        if retired_field in manifest:
            raise AssertionError(f"generated manifest 禁止退休字段: {retired_field}")
    if manifest.get("generator") != GENERATOR:
        raise AssertionError("generated manifest generator 漂移")
    graph_sha = lock.get("contractGraph", {}).get("sha256")
    if manifest.get("contractGraphSha256") != graph_sha:
        raise AssertionError("generated manifest 未绑定当前 ContractGraph lock")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise AssertionError("generated manifest outputs 不能为空")

    all_seen: set[str] = set()
    seen: set[str] = set()
    for output in outputs:
        if not isinstance(output, dict):
            raise AssertionError("generated manifest output 必须是 object")
        relative = str(output.get("path", ""))
        if relative in all_seen:
            raise AssertionError(f"重复 App generated output: {relative}")
        all_seen.add(relative)
        if relative in delegated_paths:
            continue
        if (
            not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or not is_allowed_generated_path(relative)
        ):
            raise AssertionError(f"非法 App generated output path: {relative}")
        seen.add(relative)
        if output.get("owner") != "app-only-emitter":
            raise AssertionError(f"App generated output owner 漂移: {relative}")
        if output.get("generator") != GENERATOR:
            raise AssertionError(f"App generated output generator 漂移: {relative}")
        if output.get("contractGraphSha256") != graph_sha:
            raise AssertionError(f"App generated output Graph hash 漂移: {relative}")
        path = app_root / relative
        if not path.is_file():
            raise AssertionError(f"App generated output 缺失: {relative}")
        payload = path.read_bytes()
        if len(payload) != output.get("bytes"):
            raise AssertionError(f"App generated output 大小漂移: {relative}")
        if hashlib.sha256(payload).hexdigest() != output.get("sha256"):
            raise AssertionError(f"App generated output hash 漂移: {relative}")
    return seen


def validate_shell_manifest(app_root: Path, manifest: dict) -> frozenset[str]:
    for forbidden_field in (
        "contractGraphSha256",
        "appExposedOperations",
        "operationHandoff",
    ):
        if forbidden_field in manifest:
            raise AssertionError(
                f"shell navigation manifest 禁止 Cloud handoff 字段: {forbidden_field}"
            )
    if manifest.get("generator") != SHELL_GENERATOR:
        raise AssertionError("shell navigation manifest generator 漂移")
    if manifest.get("responsibility") != SHELL_RESPONSIBILITY:
        raise AssertionError("shell navigation manifest responsibility 漂移")
    metadata_sha = str(manifest.get("metadataSha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", metadata_sha):
        raise AssertionError("shell navigation manifest metadataSha256 非法")

    inputs = manifest.get("inputs")
    if not isinstance(inputs, list):
        raise AssertionError("shell navigation manifest inputs 必须是列表")
    input_paths: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict):
            raise AssertionError("shell navigation manifest input 必须是 object")
        relative = str(item.get("path", ""))
        if relative in input_paths:
            raise AssertionError(
                f"shell navigation manifest input 重复: {relative}"
            )
        input_paths.add(relative)
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            raise AssertionError(
                f"shell navigation manifest input hash 非法: {relative}"
            )
    if input_paths != set(SHELL_INPUTS):
        raise AssertionError(
            "shell navigation manifest 输入职责漂移: "
            f"{sorted(input_paths ^ set(SHELL_INPUTS))}"
        )

    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise AssertionError("shell navigation manifest outputs 不能为空")
    seen: set[str] = set()
    for output in outputs:
        if not isinstance(output, dict):
            raise AssertionError(
                "shell navigation manifest output 必须是 object"
            )
        relative = str(output.get("path", ""))
        if (
            not relative.startswith(SHELL_OUTPUT_PREFIX)
            or relative.startswith("/")
            or ".." in Path(relative).parts
        ):
            raise AssertionError(
                f"非法 shell navigation generated output path: {relative}"
            )
        if relative in seen:
            raise AssertionError(
                f"重复 shell navigation generated output: {relative}"
            )
        seen.add(relative)
        if output.get("owner") != SHELL_OWNER:
            raise AssertionError(
                f"shell navigation output owner 漂移: {relative}"
            )
        if output.get("generator") != SHELL_GENERATOR:
            raise AssertionError(
                f"shell navigation output generator 漂移: {relative}"
            )
        path = app_root / relative
        if not path.is_file():
            raise AssertionError(
                f"shell navigation generated output 缺失: {relative}"
            )
        payload = path.read_bytes()
        if len(payload) != output.get("bytes"):
            raise AssertionError(
                f"shell navigation generated output 大小漂移: {relative}"
            )
        if hashlib.sha256(payload).hexdigest() != output.get("sha256"):
            raise AssertionError(
                f"shell navigation generated output hash 漂移: {relative}"
            )
    return frozenset(seen)


def discover_generated_files() -> set[str]:
    discovered: set[str] = set()
    for prefix in ALLOWED_PREFIXES:
        root = APP / prefix
        if not root.is_dir():
            continue
        for path in root.rglob("*.dart"):
            header = path.read_text(encoding="utf-8", errors="replace")[:300]
            normalized = header.lower()
            if "generated" in normalized and "do not edit" in normalized:
                discovered.add(path.relative_to(APP).as_posix())
    for relative in ALLOWED_EXACT_PATHS:
        path = APP / relative
        if not path.is_file():
            continue
        header = path.read_text(encoding="utf-8", errors="replace")[:300]
        normalized = header.lower()
        if "generated" in normalized and "do not edit" in normalized:
            discovered.add(relative)
    domain_root = APP / "packages/quwoquan_cloud_contracts/lib/src"
    for path in domain_root.glob("*/*_contracts.g.dart"):
        relative = path.relative_to(APP).as_posix()
        if not DOMAIN_TYPED_OWNER_PATTERN.fullmatch(relative):
            continue
        header = path.read_text(encoding="utf-8", errors="replace")[:300]
        normalized = header.lower()
        if "generated" in normalized and "do not edit" in normalized:
            discovered.add(relative)
    return discovered


def discover_shell_generated_files(app_root: Path) -> set[str]:
    root = app_root / SHELL_OUTPUT_PREFIX
    if not root.is_dir():
        return set()
    discovered: set[str] = set()
    for path in root.rglob("*.dart"):
        header = path.read_text(encoding="utf-8", errors="replace")[:300]
        normalized = header.lower()
        if "generated" in normalized and "do not edit" in normalized:
            discovered.add(path.relative_to(app_root).as_posix())
    return discovered


def without_delegated_outputs(
    manifest: dict,
    delegated_paths: frozenset[str],
) -> dict:
    normalized = dict(manifest)
    normalized["outputs"] = [
        output
        for output in manifest.get("outputs", [])
        if str(output.get("path", "")) not in delegated_paths
    ]
    return normalized


def verify_rebuild(
    committed: dict,
    committed_shell: dict,
    delegated_paths: frozenset[str],
) -> None:
    output_root = ROOT / ".qwq_output/env/repo/local/app-codegen/cache"
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="qwq-app-codegen-",
        dir=output_root,
    ) as temp:
        contract_view = Path(temp) / "service-contract-view"
        temp_app = Path(temp) / "quwoquan_app"
        temp_manifest = temp_app / "tool/cloud_codegen/generated_manifest.json"
        temp_shell_manifest = (
            temp_app
            / "tool/shell_navigation_codegen/generated_manifest.json"
        )
        build_view = subprocess.run(
            [
                sys.executable,
                "scripts/contracts/build_service_contract_view.py",
                "--output",
                str(contract_view),
            ],
            cwd=SERVICE,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if build_view.returncode != 0:
            raise AssertionError(
                "App generated clean rebuild 无法构建服务契约视图:\n"
                f"{build_view.stdout}\n{build_view.stderr}"
            )
        check_graph = subprocess.run(
            [
                "go",
                "run",
                "./tools/qwq_contract",
                "check",
                "--metadata-dir",
                str(contract_view),
                "--repo-root",
                str(ROOT),
                "--profile",
                "commercial",
                "--input",
                str(GRAPH),
            ],
            cwd=SERVICE,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if check_graph.returncode != 0:
            raise AssertionError(
                "App generated clean rebuild 的服务契约视图与固定 Graph 不一致:\n"
                f"{check_graph.stdout}\n{check_graph.stderr}"
            )
        command = [
            "go",
            "run",
            "./tools/codegen_app_metadata",
            "--metadata-dir",
            str(contract_view),
            "--contract-graph",
            str(GRAPH),
            "--contract-graph-lock",
            str(LOCK),
            "--app-dir",
            str(temp_app),
            "--generated-manifest",
            str(temp_manifest),
        ]
        result = subprocess.run(
            command,
            cwd=SERVICE,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if result.returncode != 0:
            raise AssertionError(
                "App generated clean rebuild 失败:\n"
                f"{result.stdout}\n{result.stderr}"
            )
        rebuilt = load_json(temp_manifest)
        validate_manifest(temp_app, rebuilt, load_json(LOCK))
        normalized_committed = without_delegated_outputs(
            committed,
            delegated_paths,
        )
        if rebuilt != normalized_committed:
            committed_outputs = {
                item["path"]: item
                for item in normalized_committed.get("outputs", [])
            }
            rebuilt_outputs = {
                item["path"]: item for item in rebuilt.get("outputs", [])
            }
            changed = sorted(
                path
                for path in committed_outputs.keys() | rebuilt_outputs.keys()
                if committed_outputs.get(path) != rebuilt_outputs.get(path)
            )
            raise AssertionError(
                "删除 generated 后全量重建结果与 committed manifest 不一致: "
                f"{changed[:20]}"
            )

        shell_command = [
            "go",
            "run",
            "./tools/codegen_app_metadata",
            "--metadata-dir",
            str(contract_view),
            "--app-dir",
            str(temp_app),
            "--shell-navigation-metadata-only",
            "--shell-navigation-manifest",
            str(temp_shell_manifest),
        ]
        shell_result = subprocess.run(
            shell_command,
            cwd=SERVICE,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if shell_result.returncode != 0:
            raise AssertionError(
                "App shell navigation clean rebuild 失败:\n"
                f"{shell_result.stdout}\n{shell_result.stderr}"
            )
        rebuilt_shell = load_json(temp_shell_manifest)
        validate_shell_manifest(temp_app, rebuilt_shell)
        if rebuilt_shell != committed_shell:
            raise AssertionError(
                "shell navigation clean rebuild 与 committed manifest 不一致"
            )

def verify_emitter_boundary() -> None:
    main_text = (GENERATOR_ROOT / "main.go").read_text(encoding="utf-8")
    service_makefile = (SERVICE / "Makefile").read_text(encoding="utf-8")
    if "initializeContractGraphBundle(" not in main_text:
        raise AssertionError("App emitter 未消费固定 ContractGraph bundle")
    if "initializeContractGraph(metadataDir)" in main_text:
        raise AssertionError("App emitter 仍在运行时编译 metadata YAML")
    if "--integration-service-dir" in service_makefile:
        raise AssertionError("codegen-app 仍可写领域服务输出")
    shell_target = service_makefile.split(
        "codegen-app-shell-navigation:",
        1,
    )[1].split("\n\n", 1)[0]
    for forbidden in (
        "--contract-graph",
        "--contract-graph-lock",
        "codegen-contract-graph",
    ):
        if forbidden in shell_target:
            raise AssertionError(
                "shell navigation codegen target 仍绑定 Cloud handoff: "
                f"{forbidden}"
            )
    for source in sorted(GENERATOR_ROOT.glob("*.go")):
        # app_identity_codegen.go 与 shell_navigation_codegen.go 同类：它们是
        # `--app-identity-only` / `--shell-navigation-metadata-only` 独立模式，
        # 以 app_artifact_manifest.yaml 为源、由各自的 generated_manifest.json 与
        # verify-app-identity / verify-app-shell-navigation 单独绑定，不属于
        # ContractGraph 驱动的 App emitter，因此不受 Graph/lock 唯一输入约束。
        if source.name.endswith("_test.go") or source.name in {
            "contract_graph_source.go",
            "shell_navigation_codegen.go",
            "app_identity_codegen.go",
        }:
            continue
        text = source.read_text(encoding="utf-8")
        if source.name == "assistant_codegen.go":
            # 该文件尾部的 service-owned Go enum check 分支不属于 App emitter；
            # App 生成路径只检查此前的 Dart 输出逻辑。
            text = text.split("func generateAssistantRuntimeEnumsGo(", 1)[0]
        if source.name == "link_templates_codegen.go":
            # citation destination Go 校验只读取 service-owned 既有生成物；
            # 保留同文件后续 App link template emitter 的边界扫描。
            before, remainder = text.split(
                "func generateCitationDestinationsGo(",
                1,
            )
            _, after = remainder.split(
                "func renderCitationDestinationsGo(",
                1,
            )
            text = before + "func renderCitationDestinationsGo(" + after
        if "os.ReadFile(" in text:
            raise AssertionError(
                f"App emitter 禁止读取 Graph/lock 之外的文件: {source.name}"
            )


def main() -> int:
    lock = load_json(LOCK)
    if digest(GRAPH) != lock.get("contractGraph", {}).get("sha256"):
        raise AssertionError("ContractGraph bundle 与 App lock hash 不一致")
    shell_manifest = load_json(SHELL_MANIFEST)
    shell_listed = validate_shell_manifest(APP, shell_manifest)
    manifest = load_json(MANIFEST)
    listed = validate_manifest(APP, manifest, lock, shell_listed)
    discovered = discover_generated_files()
    shell_discovered = discover_shell_generated_files(APP)
    retired_present = {
        relative
        for relative in RETIRED_GENERATED_PATHS
        if (APP / relative).is_file()
    }
    for prefix in RETIRED_GENERATED_PREFIXES:
        retired_root = APP / prefix
        if retired_root.is_dir():
            retired_present.update(
                path.relative_to(APP).as_posix()
                for path in retired_root.rglob("*.dart")
                if path.is_file()
            )
    retired_present = sorted(retired_present)
    if retired_present:
        raise AssertionError(
            "App generated 退休路径仍存在: "
            f"{retired_present}"
        )
    missing = sorted(discovered - listed)
    stale = sorted(listed - discovered)
    if missing or stale:
        raise AssertionError(
            "App generated manifest 覆盖不完整: "
            f"未登记={missing}, 非生成项={stale}"
        )
    shell_missing = sorted(shell_discovered - shell_listed)
    shell_stale = sorted(shell_listed - shell_discovered)
    if shell_missing or shell_stale:
        raise AssertionError(
            "shell navigation generated manifest 覆盖不完整: "
            f"未登记={shell_missing}, 非生成项={shell_stale}"
        )
    verify_emitter_boundary()
    verify_rebuild(manifest, shell_manifest, shell_listed)
    print(
        "PASS: App-only emitter fixed Graph + shell metadata clean rebuild "
        f"(cloudOutputs={len(listed)}, shellOutputs={len(shell_listed)}, "
        f"graph={manifest['contractGraphSha256']})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
