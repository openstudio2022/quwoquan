from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quwoquan_ops.cli.repo_hygiene_audit import (
    RETAINED_PATHS,
    REVIEW_REQUIRED_PATHS,
    _category,
    _status_paths,
)
from quwoquan_ops.gate.verify_entrypoint_script_paths import (
    entrypoint_script_path_issues,
)
from quwoquan_ops.gate.verify_markdown_local_links import markdown_link_issues


ROOT = Path(__file__).resolve().parents[3]
_RETIRED_MODEL_RELOAD_PATH = "/" + "v1" + "/model/reload"


def test_retired_paths_are_absent_and_device_script_has_one_canonical_location() -> None:
    retired = (
        ".gitmodules",
        "quwoquan_service/api",
        "quwoquan_service/services/user-service/internal/infrastructure/user/persistence/pg__store.g.go",
        "quwoquan_service/services/user-service/internal/domain/user/model/.g.go",
        "quwoquan_service/api_integration.test",
        "quwoquan_app/scripts/content/verify_content_post_mock_test_roots.py",
        "quwoquan_app/docs/content_post_mock_test_alignment.md",
        "quwoquan_data/scripts/verify/audit/__init__.py",
        "quwoquan_data/scripts/verify/audit/handler.py",
        "quwoquan_service/scripts/config/bootstrap_service_config_layout.sh",
        "specs/gates/three_week_dual_engine_launch_plan.md",
        "specs/gates/launch_runbook.md",
        "specs/gates/release_scope_whitelist.md",
        "quwoquan_app/scripts/fix_flutter_devices.sh",
        "quwoquan_app/scripts/chat/regenerate_conv_grid_group_avatars.py",
        "quwoquan_app/assets/assistant/config/agent_run_observability_schema.json",
        "quwoquan_app/assets/assistant/config/geo_resolution_config.json",
        "quwoquan_app/assets/assistant/config/retrieval_time_contract.json",
        "quwoquan_app/assets/assistant/config/user_phase_hints.json",
        "quwoquan_app/scripts/runtime/.verify_dart_semantic_baseline.txt",
        "quwoquan_app/scripts/runtime/.verify_error_code_semantic_baseline.txt",
        "quwoquan_app/scripts/runtime/.verify_unified_error_semantics_ratchet_baseline.txt",
        "quwoquan_app/scripts/media/render_group_avatar_composite.swift",
        "quwoquan_app/scripts/verify_orchestration_map_governance.py",
        "quwoquan_app/scripts/run_ios_simulator.sh",
        "quwoquan_app/scripts/content/run_l2_content_tests.sh",
        "quwoquan_app/scripts/ios/test_ios_shortcut_log_hygiene.py",
        "quwoquan_app/vendor/plugins/video_thumbnail/grep",
        "quwoquan_ops/cli/gamma/check_public_ip_open_port.py",
        "quwoquan_ops/cli/gamma/start_gamma_local_media_origin.sh",
        "quwoquan_ops/cli/gamma/start_public_ip_media_origin.sh",
        "quwoquan_ops/cli/gamma/verify_gamma_environment_ready.py",
        "quwoquan_ops/cli/gamma/verify_gamma_public_gateway_routing.py",
        "quwoquan_ops/cli/gamma/run_gamma_patrol_matrix_ci.py",
        "quwoquan_ops/cli/beta/verify_ops_control_plane_smoke.sh",
        "quwoquan_ops/gate/verify_artifacts_layout.py",
        "quwoquan_ops/gate/scaffold/migrate_acceptance_test_evidence.py",
        "quwoquan_service/scripts/install-hooks.sh",
        "quwoquan_service/scripts/media/verify_gamma_curated_media_routes.py",
        "quwoquan_service/scripts/media/media_slice_server.py",
        "quwoquan_service/scripts/media/media_slice_registry.py",
        "quwoquan_service/scripts/content/run_content_import_mongo_test.sh",
        "quwoquan_service/scripts/verify/verify_redis_keyspace.py",
        "quwoquan_service/scripts/recommendation/eval_interest_profile.py",
        "quwoquan_service/scripts/search/verify_search_service_module.sh",
        "quwoquan_service/scripts/search/test_output_paths.py",
        "quwoquan_service/services/assistant-service/configs/config.yaml",
        "quwoquan_service/services/content-service/configs/config.yaml",
        "quwoquan_service/services/entity-service/configs/config.yaml",
        "quwoquan_service/services/integration-service/configs/config.yaml",
        "quwoquan_service/services/platform-ops-service/configs/config.yaml",
        "quwoquan_service/services/product-ops-service/configs/config.yaml",
        "quwoquan_service/services/search-service/configs/config.yaml",
        "quwoquan_service/services/tag-service/configs/config.yaml",
        "quwoquan_service/services/user-service/configs/config.yaml",
        "specs/feature-tree/runtime/runtime-media/gamma-local-origin-runbook.md",
        "specs/feature-tree/discovery-content/content-type-framework/content-unification-admission-gate-checklist.md",
        "quwoquan_ops/environments/workflow_consolidation_plan.md",
        "specs/changelog/CR-20260330-010-mock-isolation-implementation-wave.md",
        "specs/feature-tree/02_JOURNEY_SCENARIO_MIGRATION_GUIDE.md",
        "specs/feature-tree/03_PROFILE_HOMEPAGE_REDESIGN_MIGRATION_SAMPLE.md",
        "specs/feature-tree/recommendation-platform/preconditions.md",
        "specs/feature-tree/recommendation-platform/rec-model-service/readiness.md",
        "specs/feature-tree/runtime/runtime-recommendation/推荐系统八期审计规划.plan.md",
        "specs/feature-tree/runtime/tree.yaml",
        "specs/feature-tree/experience_coverage_standard.md",
        "specs/feature-tree/runtime/runtime-messaging/reliable-async-task-channel/self_check.md",
        "specs/feature-tree/runtime/runtime-client-foundation/user_domain_dynamic_audit.md",
        "specs/feature-tree/runtime/runtime-client-foundation/map-typing-m4-chat-user-rtc-status.md",
        "docs/intersection-unification-plan.md",
        "docs/exception-observability-rollout.md",
        "docs/user_facing_prompt_backlog.md",
        "specs/gates/environment_noise_cleanup_inventory.md",
        "specs/gates/phase2_acceptance.md",
        "specs/gates/phase3_acceptance.md",
        "specs/gates/notification_service_seed_gap.md",
        "specs/gates/session_b_current_governance.md",
        "specs/gates/metadata_client_codegen_pr_workflow.md",
        "specs/gates/alpha_beta_contract_seed_sessions.md",
        "specs/gates/assistant_alpha_beta_real_chain_spec.md",
        "specs/gates/business_alpha_beta_db_seed_spec.md",
        "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_city_01.jpg",
        "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_design_01.jpg",
        "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_food_01.jpg",
        "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_lifestyle_01.jpg",
        "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_photography_01.jpg",
        "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_travel_01.jpg",
        "quwoquan_service/runtime/agentpack/types.go",
    )
    assert all(not (ROOT / path).exists() for path in retired)
    assert (ROOT / "quwoquan_app/scripts/device/fix_flutter_devices.sh").is_file()
    app_pubspec = (ROOT / "quwoquan_app/pubspec.yaml").read_text(encoding="utf-8")
    assert "assets/assistant/config/progress_text_policy.json" in app_pubspec
    assert "assets/assistant/config/" not in app_pubspec.replace(
        "assets/assistant/config/progress_text_policy.json", ""
    )
    for script_name in (
        "verify_dart_semantic.py",
        "verify_error_code_semantic.py",
        "verify_unified_error_semantics_ratchet.py",
    ):
        source = (
            ROOT / "quwoquan_app/scripts/runtime" / script_name
        ).read_text(encoding="utf-8")
        assert "--update-baseline" not in source


def test_make_and_data_cli_use_the_single_verification_entrypoint() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "verify-quwoquan-data-stages" not in makefile
    assert "python3 quwoquan_data/scripts/cli.py verify all" in makefile
    assert "normalization.validators" not in makefile
    assert "data explore --query" not in makefile

    verify_handler = (
        ROOT / "quwoquan_data/scripts/verify/handler.py"
    ).read_text(encoding="utf-8")
    for gate_name in (
        "verify_prompt_templates",
        "verify_no_flat_roots",
        "verify_no_runtime_draft_kit",
        "verify_tag_tree",
    ):
        assert gate_name in verify_handler


def test_service_runtime_config_has_no_retired_single_file_fallback() -> None:
    sources = (
        "quwoquan_service/services/tag-service/cmd/api/main.go",
        "quwoquan_service/services/entity-service/cmd/api/main.go",
        "quwoquan_service/services/circle-service/cmd/api/main.go",
        "quwoquan_service/services/chat-service/cmd/api/main.go",
        "quwoquan_service/services/search-service/cmd/api/main.go",
        "quwoquan_service/services/rtc-service/cmd/api/main.go",
        "quwoquan_service/services/integration-service/cmd/api/runtime_config.go",
        "quwoquan_service/services/content-service/cmd/api/runtime_config_and_projection.go",
        "quwoquan_service/services/assistant-service/internal/runtimeconfig/config.go",
    )
    for path in sources:
        source = (ROOT / path).read_text(encoding="utf-8")
        assert 'filepath.Join("configs", "config.yaml")' not in source


def test_service_layout_gate_scans_service_root_and_deleted_worktree_files() -> None:
    source = (
        ROOT / "quwoquan_service/scripts/verify/verify_service_layout.py"
    ).read_text(encoding="utf-8")
    assert '["git", "ls-files", "-z", "quwoquan_service"]' in source
    assert 'root_output.name in {"api", "api_integration.test"}' in source
    assert "if not path.exists():" in source

    tracked = subprocess.run(
        ["git", "ls-files", "quwoquan_service/api_integration.test"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if "quwoquan_service/api_integration.test" in tracked.stdout.splitlines():
        status = subprocess.run(
            ["git", "status", "--short", "--", "quwoquan_service/api_integration.test"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert status.stdout.rstrip().endswith(
            "quwoquan_service/api_integration.test"
        )
        assert "D" in status.stdout[:2]
    assert not (ROOT / "quwoquan_service/api_integration.test").exists()


def test_active_workflows_do_not_reference_retired_ml_or_manifest_defaults() -> None:
    ml_workflow = (
        ROOT / ".github/workflows/ml_training_pipeline.yml"
    ).read_text(encoding="utf-8")
    assert "scripts/ml" not in ml_workflow
    assert "docker-compose.rec-model.yml" not in ml_workflow
    assert "GAMMA_MONGODB_URI" not in ml_workflow
    assert "GAMMA_REC_MODEL_URL" not in ml_workflow
    assert _RETIRED_MODEL_RELOAD_PATH not in ml_workflow
    assert (
        "quwoquan_service/services/rec-model-service/scripts/requirements.txt"
        in ml_workflow
    )
    assert (
        ROOT / "quwoquan_service/services/rec-model-service/scripts/requirements.txt"
    ).is_file()

    avatar_workflow = (
        ROOT / ".github/workflows/verify-chat-avatar-commercial-matrix.yml"
    ).read_text(encoding="utf-8")
    assert "default: .qwq_output/" not in avatar_workflow
    assert 'test -f "$MANIFEST_PATH"' in avatar_workflow


def test_entrypoint_script_paths_are_live_and_retired_candidates_are_resolved() -> None:
    assert entrypoint_script_path_issues() == []
    assert markdown_link_issues() == []
    assert REVIEW_REQUIRED_PATHS == {}
    for path in (
        "quwoquan_ops/backup/pg_backup.sh",
        "quwoquan_ops/backup/mongo_backup.sh",
        "quwoquan_service/services/rec-model-service/scripts/requirements.txt",
        "specs/gates/v6_git_branch_cleanup_decisions.md",
        "quwoquan_service/scripts/search/search_load_benchmark.py",
        "quwoquan_service/scripts/search/search_rollback_rehearsal.py",
        "quwoquan_service/scripts/search/verify_search_local_gamma_capacity.py",
    ):
        assert path in RETAINED_PATHS
        assert (ROOT / path).is_file()


def test_generated_manifest_and_live_docs_keep_canonical_paths() -> None:
    manifest = json.loads(
        (
            ROOT / "quwoquan_app/tool/cloud_codegen/generated_manifest.json"
        ).read_text(encoding="utf-8")
    )
    outputs = manifest["outputs"]
    assert outputs
    assert all(
        (ROOT / "quwoquan_app" / output["path"]).is_file()
        for output in outputs
    )
    assert all("scripts/build" not in output["path"] for output in outputs)

    service_readme = (ROOT / "quwoquan_service/README.md").read_text(
        encoding="utf-8"
    )
    assert "stackctl.py verify --env alpha --kind all --profile smoke" in service_readme
    assert "--tier all" not in service_readme

    launch_readme = (ROOT / "specs/launch-plan/README.md").read_text(
        encoding="utf-8"
    )
    assert "specs/gates/" in launch_readme
    assert "不再保留同名副本" in launch_readme


def test_feature_tree_indexer_has_no_retired_task_pack_path() -> None:
    source = (
        ROOT / "quwoquan_service/runtime/agentpack/tree_index.go"
    ).read_text(encoding="utf-8")
    assert "tasks.md" not in source
    assert "IngestTaskPack" not in source
    assert "agent_task_pack" not in source
    assert 'name == "templates"' in source
    assert not list((ROOT / "specs/feature-tree").glob("*/tree.yaml"))
    feature_tree_gate = (
        ROOT / "quwoquan_ops/gate/scaffold/verify_feature_tree_refactor.sh"
    ).read_text(encoding="utf-8")
    assert "CR-*.yaml" in feature_tree_gate
    assert "YAML.parse_file" in feature_tree_gate


def test_commercial_smoke_scripts_only_accept_canonical_environments() -> None:
    sources = [
        (
            ROOT
            / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "assistant-service/smoke/run_assistant_runtime_smoke.py"
        ).read_text(encoding="utf-8"),
        (
            ROOT
            / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "chat-service/smoke/run_chat_avatar_e2e_probe.py"
        ).read_text(encoding="utf-8"),
    ]
    for source in sources:
        assert '{"alpha", "beta", "gamma", "prod"}' in source
        assert "cloud-gamma" not in source
        assert "gamma-pr" not in source
        assert "X-Test-Local-Gamma" not in source


def test_hygiene_audit_does_not_truncate_rename_status_records() -> None:
    statuses = _status_paths()
    assert all(len(status) == 2 for status in statuses.values())
    assert "qu" not in statuses.values()
    assert not any(path.startswith("oquan_") for path in statuses)


def test_hygiene_audit_walks_disk_and_protects_ignored_local_config() -> None:
    source = (
        ROOT / "quwoquan_ops/cli/repo_hygiene_audit.py"
    ).read_text(encoding="utf-8")
    assert "disk_paths = _disk_file_paths()" in source
    assert "_ignored_paths(disk_paths - tracked)" in source
    assert '"empty_directories": empty_directories' in source

    category, _ = _category("quwoquan_app/.env", "!!", tracked=False)
    assert category == "protected_local_configuration"
    category, _ = _category("quwoquan_ops/portal/.env.bak", "!!", tracked=False)
    assert category == "protected_local_configuration"
    category, _ = _category("local-signing.keystore", "!!", tracked=False)
    assert category == "protected_local_configuration"
    category, _ = _category("quwoquan_app/build/app.dill", "!!", tracked=False)
    assert category == "reproducible_local_output"
