from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
VERIFIER = (
    ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime"
    / "codegen"
    / "verify_app_generated_manifest.py"
)
MANIFEST = (
    ROOT
    / "quwoquan_app"
    / "tool"
    / "cloud_codegen"
    / "generated_manifest.json"
)
SHELL_MANIFEST = (
    ROOT
    / "quwoquan_app"
    / "tool"
    / "shell_navigation_codegen"
    / "generated_manifest.json"
)
OWNERSHIP_POLICY = (
    ROOT / "quwoquan_ops" / "policies" / "cloud_contract_ownership.json"
)
LEGACY_API_METADATA_DOMAINS = (
    "assistant",
    "chat",
    "circle",
    "content",
    "entity",
    "integration",
    "notification",
    "ops",
    "realtime",
    "recommendation",
    "rtc",
    "search",
    "tag",
    "travel",
    "user",
)
CURRENT_ALLOWED_EXACT_OUTPUTS = frozenset(
    {
        "lib/runtime/transport/generated/cloud_api_defaults.g.dart",
        "lib/service/content_service/content/post/adapters/generated/article_detail_wire_keys.g.dart",
        "lib/service/recommendation_service/recommendation/"
        "recommendation_feature_profile_view/presentation/generated/"
        "impact_help_type_metadata.g.dart",
        "lib/service/recommendation_service/recommendation/"
        "recommendation_feature_profile_view/presentation/generated/"
        "intersection_display_metadata.g.dart",
        "lib/service/content_service/content/post/presentation/generated/content_ui_config.g.dart",
        "lib/runtime/observability/generated/app_telemetry_catalog.g.dart",
        "packages/quwoquan_cloud_contracts/lib/src/rtc/"
        "rtc_operation_contracts.g.dart",
    }
)
RETIRED_ZERO_CONSUMER_OUTPUTS = frozenset(
    {
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
    }
)


def load_verifier_module():
    spec = importlib.util.spec_from_file_location(
        "verify_app_generated_manifest",
        VERIFIER,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("无法加载 App generated manifest verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AppGeneratedManifestContractTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
    def test_runtime_generated_targets_have_single_canonical_roots(self) -> None:
        verifier = load_verifier_module()
        canonical = {
            "lib/service/content_service/media/media_asset/application/generated/"
            "content_image_variant_policy.g.dart",
            "lib/service/content_service/media/media_upload_session/application/generated/"
            "content_media_upload_policy.g.dart",
            "lib/runtime/errors/generated/assistant/assistant_errors.g.dart",
            "lib/runtime/errors/generated/chat/chat_errors.g.dart",
            "lib/runtime/errors/generated/circle/circle_errors.g.dart",
            "lib/runtime/errors/generated/circle/circle_membership_errors.g.dart",
            "lib/runtime/errors/generated/content/content_errors.g.dart",
            "lib/runtime/errors/generated/entity/entity_errors.g.dart",
            "lib/runtime/errors/generated/integration/integration_location_errors.g.dart",
            "lib/runtime/errors/generated/notification/notification_errors.g.dart",
            "lib/runtime/errors/generated/ops/ops_event_record_errors.g.dart",
            "lib/runtime/errors/generated/rtc/rtc_errors.g.dart",
            "lib/runtime/errors/generated/search/search_errors.g.dart",
            "lib/runtime/errors/generated/tag/tag_errors.g.dart",
            "lib/runtime/errors/generated/user/user_errors.g.dart",
            "lib/runtime/observability/generated/app_telemetry_catalog.g.dart",
            "lib/service/search_service/search/search_index_view/application/generated/"
            "search_execution_policy.g.dart",
            "lib/service/search_service/search/search_index_view/presentation/generated/"
            "search_display_metadata.g.dart",
            "packages/quwoquan_cloud_contracts/lib/src/generated/search/"
            "search_contract_vocabulary.g.dart",
            "lib/service/content_service/content/post/domain/generated/"
            "content_publication_policy.g.dart",
            "lib/service/content_service/content/post/application/generated/"
            "content_feed_category_policy.g.dart",
            "lib/service/content_service/content/post/domain/generated/"
            "content_post_snapshot_policy.g.dart",
            "lib/service/content_service/content/post/presentation/generated/"
            "post_read_surface_id.g.dart",
            "lib/service/circle_service/circle_management/circle/presentation/generated/"
            "circle_ui_config.g.dart",
            "lib/service/entity_service/entity_homepage/homepage/presentation/generated/"
            "homepage_ui_config.g.dart",
            "lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/presentation/generated/"
            "impact_help_type_metadata.g.dart",
            "lib/service/user_service/account/user_account/application/public/generated/"
            "user_profile_ui_config.g.dart",
        }
        for domain in (
            "assistant",
            "chat",
            "circle",
            "content",
            "entity",
            "integration",
            "notification",
            "ops",
            "realtime",
            "recommendation",
            "rtc",
            "search",
            "tag",
            "travel",
            "user",
        ):
            canonical.add(
                "lib/runtime/transport/generated/"
                f"{domain}/{domain}_request_page_ids.g.dart"
            )
        retired = set(verifier.RETIRED_GENERATED_PATHS)

        self.assertEqual(len(canonical), 42)
        for path in canonical:
            self.assertTrue(
                verifier.is_allowed_generated_path(path),
                msg=f"canonical generated target rejected: {path}",
            )
        for path in retired:
            self.assertFalse(
                verifier.is_allowed_generated_path(path),
                msg=f"retired generated target still accepted: {path}",
            )
        shell_outputs = {
            item["path"]
            for item in json.loads(
                SHELL_MANIFEST.read_text(encoding="utf-8")
            )["outputs"]
        }
        self.assertEqual(len(shell_outputs), 5)
        for path in shell_outputs:
            self.assertFalse(
                verifier.is_allowed_generated_path(path),
                msg=f"Cloud emitter still owns shell output: {path}",
            )
        self.assertFalse(
            verifier.is_allowed_generated_path(
                "lib/runtime/observability/generated/runtime_log_catalog.g.dart"
            ),
            msg="App emitter must not own the independent observability catalog",
        )
        self.assertFalse(
            verifier.is_allowed_generated_path(
                "lib/service/recommendation_service/recommendation/"
                "recommendation_feature_profile_view/application/generated/"
                "impact_help_type_metadata.g.dart"
            ),
            msg="impact presentation metadata must not drift into application",
        )

    # spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
    def test_retired_generated_outputs_are_fail_closed(self) -> None:
        verifier = load_verifier_module()
        retired_outputs = {
            "lib/assistant/generated/contracts/assistant_replay_case.g.dart",
            "lib/assistant/generated/contracts/assistant_run_response.g.dart",
            "lib/cloud/content/generated/content_behaviors.g.dart",
            "lib/cloud/content/generated/content_privacy_policy.g.dart",
            "lib/cloud/runtime/generated/app_request_page_ids.g.dart",
            "lib/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart",
            "lib/cloud/runtime/generated/circle/circle_category_tab_defaults.dart",
            "lib/cloud/runtime/generated/circle/circle_category_tab_order.dart",
            "lib/cloud/runtime/generated/content/report_create_request_wire.g.dart",
            "lib/cloud/runtime/generated/content/post_read_presentation.g.dart",
            "packages/quwoquan_cloud_contracts/lib/src/rtc/"
            "call_session_dtos.g.dart",
            "lib/cloud/runtime/generated/auth/auth_policy.g.dart",
            "lib/cloud/runtime/generated/integration/"
            "integration_location_metadata.g.dart",
        }
        retired_outputs.update(
            "lib/cloud/runtime/generated/"
            f"{domain}/{domain}_api_metadata.g.dart"
            for domain in LEGACY_API_METADATA_DOMAINS
        )
        retired_outputs.update(RETIRED_ZERO_CONSUMER_OUTPUTS)
        for path in retired_outputs:
            self.assertFalse(
                verifier.is_allowed_generated_path(path),
                msg=f"retired generated output still accepted: {path}",
            )

    # spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
    def test_legacy_mixed_roots_accept_only_current_exact_outputs(self) -> None:
        verifier = load_verifier_module()
        self.assertEqual(
            {
                path
                for path in verifier.ALLOWED_EXACT_PATHS
                if path.startswith("lib/cloud/runtime/generated/")
            },
            frozenset(),
        )
        self.assertEqual(
            verifier.ALLOWED_EXACT_PATHS,
            CURRENT_ALLOWED_EXACT_OUTPUTS,
        )
        for path in {
            "lib/runtime/transport/generated/cloud_api_defaults.g.dart",
            "lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/presentation/generated/"
            "intersection_display_metadata.g.dart",
        }:
            self.assertTrue(verifier.is_allowed_generated_path(path))
        for path in RETIRED_ZERO_CONSUMER_OUTPUTS:
            self.assertFalse(verifier.is_allowed_generated_path(path))
        self.assertTrue(
            verifier.is_allowed_generated_path(
                "lib/service/content_service/content/post/presentation/generated/content_ui_config.g.dart"
            )
        )
        self.assertFalse(
            verifier.is_allowed_generated_path(
                "lib/cloud/runtime/generated/content/unowned_output.g.dart"
            )
        )
        self.assertFalse(
            verifier.is_allowed_generated_path(
                "lib/cloud/content/generated/unowned_output.g.dart"
            )
        )

    # spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
    def test_impact_help_metadata_prepares_canonical_presentation_owner(self) -> None:
        verifier = load_verifier_module()
        canonical = (
            "lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/presentation/generated/"
            "impact_help_type_metadata.g.dart"
        )
        wrong_layer = (
            "lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/application/generated/"
            "impact_help_type_metadata.g.dart"
        )
        self.assertTrue(verifier.is_allowed_generated_path(canonical))
        self.assertFalse(verifier.is_allowed_generated_path(wrong_layer))

        policy = json.loads(OWNERSHIP_POLICY.read_text(encoding="utf-8"))
        resource = next(
            item
            for item in policy["resources"]
            if item["id"] == "app-generated-output"
        )
        write_paths = set(resource["writePaths"])
        self.assertIn(
            "quwoquan_app/lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/presentation/generated/**",
            write_paths,
        )
        self.assertNotIn(
            "quwoquan_app/lib/cloud/runtime/generated/recommendation/"
            "impact_help_type_metadata.g.dart",
            write_paths,
        )

    # spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
    def test_app_emitter_ownership_uses_only_canonical_output_roots(self) -> None:
        verifier = load_verifier_module()
        policy = json.loads(OWNERSHIP_POLICY.read_text(encoding="utf-8"))
        resource = next(
            item
            for item in policy["resources"]
            if item["id"] == "app-generated-output"
        )
        write_paths = set(resource["writePaths"])
        for retired in {
            "quwoquan_app/lib/app/navigation/generated/**",
            "quwoquan_app/lib/application/content/media/generated/**",
            "quwoquan_app/lib/cloud/**/generated/**",
            "quwoquan_app/lib/cloud/runtime/generated/**",
        }:
            self.assertNotIn(retired, write_paths)
        for canonical in {
            "quwoquan_app/lib/runtime/errors/generated/**",
            "quwoquan_app/lib/runtime/transport/generated/**",
            "quwoquan_app/lib/service/search_service/search/search_index_view/"
            "application/generated/**",
            "quwoquan_app/lib/service/search_service/search/search_index_view/"
            "presentation/generated/**",
            "quwoquan_app/lib/service/content_service/media/media_asset/application/generated/**",
            "quwoquan_app/lib/service/content_service/media/media_upload_session/application/generated/**",
            "quwoquan_app/lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/presentation/generated/**",
            "quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/generated/**",
            "quwoquan_app/tool/cloud_codegen/generated_manifest.json",
        }:
            self.assertIn(canonical, write_paths)
        self.assertNotIn(
            "quwoquan_app/lib/runtime/shell/navigation/generated/**",
            write_paths,
        )
        shell_resource = next(
            item
            for item in policy["resources"]
            if item["id"] == "app-shell-navigation-generated-output"
        )
        self.assertEqual(
            shell_resource["owner"],
            "app-shell-navigation-emitter",
        )
        self.assertEqual(
            set(shell_resource["writePaths"]),
            {
                "quwoquan_app/lib/runtime/shell/navigation/generated/**",
                "quwoquan_app/tool/shell_navigation_codegen/"
                "generated_manifest.json",
            },
        )

        for path in CURRENT_ALLOWED_EXACT_OUTPUTS:
            if path.startswith("packages/"):
                continue
            self.assertIn(f"quwoquan_app/{path}", write_paths)
        for path in RETIRED_ZERO_CONSUMER_OUTPUTS:
            self.assertNotIn(f"quwoquan_app/{path}", write_paths)
        self.assertIn(
            "quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/rtc/**",
            write_paths,
        )
        self.assertEqual(
            {
                path
                for path in write_paths
                if path.startswith("quwoquan_app/lib/cloud/runtime/generated/")
            },
            set(),
        )

        retired_legacy_runtime = {
            "quwoquan_app/lib/cloud/runtime/generated/auth/auth_policy.g.dart",
            "quwoquan_app/lib/cloud/runtime/generated/integration/"
            "integration_location_metadata.g.dart",
        }
        retired_legacy_runtime.update(
            "quwoquan_app/lib/cloud/runtime/generated/"
            f"{domain}/{domain}_api_metadata.g.dart"
            for domain in LEGACY_API_METADATA_DOMAINS
        )
        self.assertTrue(retired_legacy_runtime.isdisjoint(write_paths))

        canonical_registry = (
            "packages/quwoquan_cloud_contracts/lib/src/generated/"
            "operation_contracts.g.dart"
        )
        self.assertTrue(
            verifier.is_allowed_generated_path(canonical_registry),
            msg="canonical operation registry must remain App-emitter owned",
        )

    # spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
    def test_runtime_log_catalog_has_an_independent_exact_output_owner(self) -> None:
        policy = json.loads(OWNERSHIP_POLICY.read_text(encoding="utf-8"))
        resource = next(
            item
            for item in policy["resources"]
            if item["id"] == "runtime-observability-catalog-output"
        )
        self.assertEqual(resource["owner"], "observability-catalog-emitter")
        self.assertEqual(
            set(resource["writePaths"]),
            {
                "quwoquan_service/runtime/observability/catalog_generated.go",
                "quwoquan_app/lib/runtime/observability/generated/"
                "runtime_log_catalog.g.dart",
                "quwoquan_ops/cli/lib/generated/runtime_log_catalog.py",
                "quwoquan_data/scripts/core/generated/runtime_log_catalog.py",
                "quwoquan_ops/portal/src/generated/observability/"
                "runtimeLogCatalog.generated.ts",
            },
        )
        all_owned_paths = {
            path
            for item in policy["resources"]
            for path in item.get("writePaths", [])
        }
        self.assertNotIn(
            "quwoquan_app/lib/core/observability/generated/"
            "runtime_log_catalog.g.dart",
            all_owned_paths,
        )

    def test_fixed_graph_clean_rebuild_is_byte_exact(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFIER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn("clean rebuild", result.stdout)

    def test_manifests_partition_cloud_and_shell_outputs(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        outputs = {item["path"] for item in manifest["outputs"]}
        shell_manifest = json.loads(
            SHELL_MANIFEST.read_text(encoding="utf-8")
        )
        shell_outputs = {
            item["path"] for item in shell_manifest["outputs"]
        }

        self.assertIn(
            "packages/quwoquan_cloud_contracts/lib/src/generated/"
            "operation_contracts.g.dart",
            outputs,
        )
        self.assertIn(
            "packages/quwoquan_cloud_contracts/lib/src/rtc/"
            "rtc_operation_contracts.g.dart",
            outputs,
        )
        self.assertIn(
            "packages/quwoquan_cloud_contracts/lib/src/generated/requests/rtc/"
            "rtc_operation_contracts.g.requests.g.dart",
            outputs,
        )
        self.assertIn(
            "packages/quwoquan_cloud_contracts/lib/src/content/"
            "preview_track_manifest_contracts.g.dart",
            outputs,
        )
        self.assertNotIn(
            "packages/quwoquan_cloud_contracts/lib/src/travel/"
            "travel_operation_contracts.g.dart",
            outputs,
        )
        self.assertNotIn(
            "packages/quwoquan_cloud_contracts/lib/src/generated/requests/"
            "travel/travel_operation_contracts.g.requests.g.dart",
            outputs,
        )
        for domain in ("tag", "integration", "notification"):
            self.assertIn(
                "packages/quwoquan_cloud_contracts/lib/src/"
                f"{domain}/{domain}_operation_contracts.g.dart",
                outputs,
            )
            self.assertIn(
                "packages/quwoquan_cloud_contracts/lib/src/generated/requests/"
                f"{domain}/{domain}_operation_contracts.g.requests.g.dart",
                outputs,
            )
        self.assertIn(
            "lib/runtime/shell/navigation/generated/app_route_paths.g.dart",
            shell_outputs,
        )
        self.assertIn(
            "lib/runtime/shell/navigation/generated/app_ui_surfaces.g.dart",
            shell_outputs,
        )
        self.assertNotIn("contractGraphSha256", shell_manifest)
        self.assertEqual(
            shell_manifest["responsibility"],
            "shell-navigation-metadata-only",
        )


if __name__ == "__main__":
    unittest.main()
