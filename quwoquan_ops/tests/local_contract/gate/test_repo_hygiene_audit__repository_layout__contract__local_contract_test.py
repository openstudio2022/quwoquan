# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quwoquan_ops.cli.repo_hygiene_audit import _category, _status_paths
from quwoquan_ops.gate.verify_entrypoint_script_paths import (
    entrypoint_script_path_issues,
)
from quwoquan_ops.gate.verify_markdown_local_links import markdown_link_issues


ROOT = Path(__file__).resolve().parents[4]
_RETIRED_MODEL_RELOAD_PATH = "/" + "v1" + "/model/reload"


def test_retired_directory_classes_are_absent_and_device_script_is_canonical() -> None:
    for relative in (
        ".gitmodules",
        "specs/changelog",
        "specs/gates",
        "specs/launch-plan",
        "quwoquan_service/runtime/agentpack",
        "quwoquan_service/tools/gen_tree_index",
    ):
        assert not (ROOT / relative).exists(), relative

    feature_root = ROOT / "specs/feature-tree"
    forbidden_names = {
        "acceptance.yaml",
        "tree.yaml",
        "plan.md",
        "plan.yaml",
        "tasks.md",
        "tasks.yaml",
    }
    assert not [
        path
        for path in feature_root.rglob("*")
        if path.is_file() and path.name in forbidden_names
    ]

    assert not (ROOT / "quwoquan_app/scripts/fix_flutter_devices.sh").exists()
    assert (ROOT / "quwoquan_app/scripts/tools/device/list_flutter_devices.sh").is_file()
    for script_path in (
        "quwoquan_app/scripts/runtime/observability/verify_dart_semantic.py",
        "quwoquan_app/scripts/runtime/error/verify_error_code_semantic.py",
        "quwoquan_app/scripts/runtime/error/verify_unified_error_semantics_ratchet.py",
    ):
        source = (ROOT / script_path).read_text(encoding="utf-8")
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
        "verify_cli_first",
        "verify_public_cli_live_import_zero",
        "verify_data_layout",
        "verify_script_architecture",
        "verify_python_symbols",
        "verify_no_flat_roots",
        "verify_tag_tree",
        "verify_source_digest",
        "verify_content_execution_layout",
        "verify_runtime_input_ownership",
        "verify_output_root_isolation",
        "verify_object_size_budget",
        "verify_publish_purity",
        "verify_publish_closure",
    ):
        assert gate_name in verify_handler


def test_service_runtime_config_has_no_retired_single_file_fallback() -> None:
    sources = (
        "quwoquan_service/services/tag-service/cmd/api/bootstrap.go",
        "quwoquan_service/services/entity-service/cmd/api/bootstrap.go",
        "quwoquan_service/services/circle-service/cmd/api/bootstrap.go",
        "quwoquan_service/services/chat-service/cmd/api/bootstrap.go",
        "quwoquan_service/services/search-service/cmd/api/bootstrap.go",
        "quwoquan_service/services/rtc-service/cmd/api/main.go",
        "quwoquan_service/services/integration-service/cmd/api/runtime_config.go",
        "quwoquan_service/services/content-service/cmd/api/runtime_config_and_projection.go",
        "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimeconfig/config.go",
    )
    for path in sources:
        source = (ROOT / path).read_text(encoding="utf-8")
        assert 'filepath.Join("configs", "config.yaml")' not in source


def test_service_layout_gate_scans_object_paths_and_forbids_cache() -> None:
    # 门禁实现已拆为薄入口 + service_architecture 包；文本断言覆盖两者。
    gate_sources = [ROOT / "quwoquan_ops/gate/verify_service_architecture.py"]
    gate_sources += sorted(
        (ROOT / "quwoquan_ops/gate/service_architecture").rglob("*.py")
    )
    source = "\n".join(
        gate_source.read_text(encoding="utf-8") for gate_source in gate_sources
    )
    assert "verify_source_and_test_paths" in source
    assert "verify_no_source_artifacts" in source
    assert "retired second truth source exists" in source

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
        "quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/requirements.txt"
        in ml_workflow
    )
    assert (
        ROOT / "quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/requirements.txt"
    ).is_file()

    avatar_workflow = (
        ROOT / ".github/workflows/verify-chat-avatar-commercial-matrix.yml"
    ).read_text(encoding="utf-8")
    assert "default: .qwq_output/" not in avatar_workflow
    assert 'test -f "$MANIFEST_PATH"' in avatar_workflow


def test_entrypoint_script_paths_and_operational_dependencies_are_live() -> None:
    assert entrypoint_script_path_issues() == []
    assert markdown_link_issues() == []
    for path in (
        "quwoquan_ops/tools/backup/pg_backup.sh",
        "quwoquan_ops/tools/backup/mongo_backup.sh",
        "quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/requirements.txt",
        "quwoquan_service/scripts/search-service/tools/search_load_benchmark.py",
    ):
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
    assert (
        "stackctl.py verify --service content-service --env alpha"
        in service_readme
    )
    assert "stackctl.py verify --kind all --profile baseline" not in service_readme
    assert "--tier all" not in service_readme

    assert not (ROOT / "specs/gates").exists()
    assert not (ROOT / "specs/launch-plan").exists()


def test_feature_tree_has_no_indexer_or_retired_task_pack_path() -> None:
    assert not (ROOT / "quwoquan_service/runtime/agentpack").exists()
    assert not (ROOT / "quwoquan_service/tools/gen_tree_index").exists()
    assert not list((ROOT / "specs/feature-tree").glob("*/tree.yaml"))
    # 实现单轨挪进了 lib/feature_tree 包;门面只保留 re-export。禁用回归名与
    # 「不做 yaml 兼容读取」的约束必须覆盖包内全部源文件,而不只是瘦门面。
    facade = (ROOT / "quwoquan_ops/cli/feature_tree.py").read_text(encoding="utf-8")
    assert "discover_nodes" in facade
    package_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "quwoquan_ops/cli/lib/feature_tree").glob("*.py"))
    )
    assert "tree_index.yaml" in package_sources  # only a forbidden-regression name
    assert "yaml.safe_load" not in facade
    assert "yaml.safe_load" not in package_sources


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
