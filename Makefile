.PHONY: gate
.PHONY: gate-local-gamma
.PHONY: gate-runtime-media
.PHONY: gate-runtime-media-full
.PHONY: verify-chat-avatar-commercial-matrix
.PHONY: verify-app-mock-isolation
.PHONY: verify-api-path-unversioned
.PHONY: verify-api-path-runtime
.PHONY: verify-app-runtime-host-literals
.PHONY: verify-app-concept-naming
.PHONY: verify-app-auth-policy
.PHONY: verify-app-domain-error-code-registry
.PHONY: verify-app-behavior-error-stack-convergence
.PHONY: verify-app-permission-coordinator-adoption
.PHONY: verify-app-permission-primer-copy
.PHONY: verify-app-startup-ttid
.PHONY: verify-app-startup-environment-pr
.PHONY: verify-app-startup-environment-uat
.PHONY: verify-app-startup-observability-release
.PHONY: verify-app-experience-observability
.PHONY: verify-app-recoverable-error-surface
.PHONY: verify-app-dual-platform-usability-baseline
.PHONY: verify-app-ios-hot-restart
.PHONY: build-app-startup-environment-matrix
.PHONY: verify-app-lib-no-test-import
.PHONY: verify-app-page-horizontal-quality
.PHONY: verify-app-page-object-contract
.PHONY: verify-app-content-ui-boundaries
.PHONY: verify-app-remote-config-contract
.PHONY: verify-app-native-edge-navigation
.PHONY: verify-app-pageflip-back-mainline
.PHONY: verify-app-pageflip-backward-mainline
.PHONY: verify-app-page-abc-governance
.PHONY: verify-app-page-abc-governance-enforce-a
.PHONY: verify-app-page-abc-governance-enforce-b
.PHONY: verify-app-page-abc-governance-enforce-c
.PHONY: verify-app-page-abc-governance-enforce-all
.PHONY: verify-app-ui-map-literal-budget
.PHONY: verify-app-assistant-search-weak-typing-ratchet
.PHONY: verify-app-assistant-old-stack-retired
.PHONY: verify-assistant-agent-replay-evaluation
.PHONY: verify-retired-terms-zero
.PHONY: verify-app-production-data-source-single-path
.PHONY: verify-production-wiring-purity
.PHONY: verify-app-seed-manifest
.PHONY: verify-gamma-curated-scenarios
.PHONY: generate-gamma-curated-scenarios
.PHONY: fetch-app-bundled-fonts
.PHONY: verify-app-bundled-fonts
.PHONY: check-app-bundled-fonts-updates
.PHONY: verify-app-web-offline-resources
.PHONY: verify-avatar-user-pool
.PHONY: probe-avatar-user-pool-gateway
.PHONY: verify-business-env-data-inventory
.PHONY: verify-quwoquan-data
.PHONY: verify-markdown-article-no-article-document verify-article-contract-purity
.PHONY: verify-app-env-package
.PHONY: verify-service-env-package
.PHONY: verify-env-topology verify-prod-plane-access-isolation
.PHONY: verify-local-port-manifest
.PHONY: verify-public-vs-upstream-url-contract
.PHONY: verify-domain-governance
.PHONY: verify-login-dependency-config
.PHONY: verify-env-packaging
.PHONY: verify-env-instance-isolation
.PHONY: observability-es-up
.PHONY: observability-es-down
.PHONY: observability-es-health
.PHONY: observability-es-bootstrap
.PHONY: observability-es-smoke
.PHONY: verify-reliable-task-topology
.PHONY: verify-service-architecture
.PHONY: verify-metadata
.PHONY: build-app-env
.PHONY: build-service-env
.PHONY: test-app-alpha-seed
.PHONY: test-app-beta-seed
.PHONY: beta-up
.PHONY: beta-down
.PHONY: beta-status
.PHONY: verify
.PHONY: verify-global-increment-constraints
.PHONY: verify-agent-context-contract
.PHONY: verify-retired-runtime-architecture
.PHONY: verify-service-ddd-cqrs-baseline
.PHONY: verify-commercial-contract-generation
.PHONY: verify-behavior-event-type-contract
.PHONY: verify-object-relation-edge-type-contract
.PHONY: verify-homepage-type-contract
.PHONY: verify-app-cloud-runtime-single-path
.PHONY: verify-app-cloud-security-cutovers
.PHONY: accept-app-contract-handoff
.PHONY: verify-app-contract-handoff
.PHONY: verify-app-generated-manifest
.PHONY: verify-app-cloud-package-boundaries
.PHONY: codegen
.PHONY: codegen-observability-catalog
.PHONY: verify-observability-catalog
.PHONY: verify-runtime-log-governance
.PHONY: codegen-app
.PHONY: codegen-ops-portal
.PHONY: codegen-control-plane-runtime
.PHONY: codegen-content-service
.PHONY: codegen-chat-service
.PHONY: new-service
.PHONY: config-slo-gate
.PHONY: stackctl-package
.PHONY: stackctl-verify
.PHONY: stackctl-up
.PHONY: stackctl-down
.PHONY: stackctl-status

REPO_ROOT ?= $(CURDIR)
# Always pin to the repo output root. A polluted shell export (for example a
# leftover data-local-contract temp dir) must not redirect gate/stackctl output
# into disposable pytest isolation roots scanned by verify_test_no_fake.
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
export QWQ_OUTPUT_ROOT

QWQ_PYTHON_CACHE_ROOT ?= $(HOME)/.cache/quwoquan/python-envs
export QWQ_PYTHON_CACHE_ROOT
DATA_PYTHON ?= $(QWQ_PYTHON_CACHE_ROOT)/quwoquan-data/bin/python
PYTEST_RUNNER ?= $(DATA_PYTHON)
PYTEST_INTERPRETER_FLAGS ?= -B
PYTEST_FLAGS ?= -o cache_dir=$(QWQ_OUTPUT_ROOT)/env/repo/local/tests/cache/pytest
# Go 默认按所有逻辑 CPU 并发运行 package。大型聚合门禁中，每个 test
# binary 又拥有完整 GOMAXPROCS，容易让外部媒体探针在自身 deadline 前得不到
# 调度。统一限制 package 并发；隔离 runner 可显式覆盖，但不得另写测试入口。
GO_TEST_PACKAGE_PARALLELISM ?= 4
# API integration packages provision heavyweight shared local dependencies
# (Docker, MongoDB, Redis, PostgreSQL, MinIO). The local-env gate is serial by
# topology contract; keep package binaries serial too so readiness is evidence
# of the tested service rather than host scheduler/container contention.
API_INTEGRATION_GO_TEST_PACKAGE_PARALLELISM ?= 1
export PYTHONDONTWRITEBYTECODE := 1
export PYTHONPYCACHEPREFIX := $(QWQ_OUTPUT_ROOT)/env/repo/local/test-runtime/cache/bytecode/make
.PHONY: stackctl-health
.PHONY: stackctl-inspect
.PHONY: stackctl-doctor
.PHONY: stackctl-repair
.PHONY: stackctl-deploy

# 客户端：production lib、pubspec、Patrol/UAT 不得直连 Mock/fixture。
verify-app-mock-isolation:
	@python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py

# HTTP API path 禁止 /vN、/internal/vN、/callbacks/vN（已挂入 gate_repo.sh）
verify-api-path-unversioned:
	@python3 quwoquan_ops/gate/verify_api_path_unversioned.py

# 运行时新旧 path 探针（live；密钥/起栈就绪后执行，不强制进静态门禁）
# 例: make verify-api-path-runtime ENV=gamma
verify-api-path-runtime:
	@python3 quwoquan_ops/cli/probes/verify_api_path_runtime_unversioned.py --env $${ENV:-gamma}

verify-app-runtime-host-literals:
	@python3 quwoquan_app/scripts/env/verify_runtime_host_literals.py

verify-app-concept-naming:
	@python3 quwoquan_app/scripts/runtime/verify_concept_naming.py

# 端云错误码全集一致：云 errors.yaml code 集 == 客户端生成 *ErrorCode 枚举集
verify-app-error-endcloud-parity:
	@python3 quwoquan_app/scripts/runtime/verify_error_code_endcloud_parity.py

verify-app-domain-error-code-registry:
	@python3 quwoquan_app/scripts/runtime/verify_domain_error_code_registry.py

verify-app-behavior-error-stack-convergence:
	@python3 quwoquan_app/scripts/runtime/verify_behavior_error_stack_convergence.py

# recovery 对齐：errors.yaml recovery_action -> 生成 Go .WithRecovery（factory 风格域）
verify-service-error-recovery-alignment:
	@python3 quwoquan_service/scripts/verify/verify_error_recovery_alignment.py

# API 鉴权契约：security.auth_mode 真相源与端侧鉴权快照一致，核心受限入口必须 required
verify-app-auth-policy:
	@python3 quwoquan_app/scripts/auth/verify_auth_policy_contract.py

verify-app-login-entry-loop-contract:
	@python3 quwoquan_app/scripts/auth/verify_login_entry_loop_contract.py

verify-app-permission-coordinator-adoption:
	@python3 quwoquan_app/scripts/runtime/verify_permission_coordinator_adoption.py

verify-app-permission-primer-copy:
	@python3 quwoquan_app/scripts/runtime/verify_permission_primer_copy.py

verify-app-startup-ttid:
	@python3 quwoquan_ops/gate/verify_python_syntax.py \
		quwoquan_app/scripts/device/verify_startup_first_frame.py \
		quwoquan_app/scripts/device/verify_startup_ttid_baseline.py \
		quwoquan_app/scripts/device/verify_startup_web.py \
		quwoquan_app/scripts/device/verify_welcome_motion_frames.py
	@python3 quwoquan_app/scripts/device/verify_startup_ttid_baseline.py
	@python3 quwoquan_app/test/local_contract/app/startup_welcome_motion_probe__local_contract_test.py

verify-app-startup-environment-pr:
	@python3 quwoquan_ops/gate/verify_python_syntax.py \
		quwoquan_app/scripts/device/verify_flutter_run_defines.py \
		quwoquan_app/scripts/device/verify_ios_hot_restart.py
	@python3 quwoquan_app/scripts/runtime/verify_startup_environment_matrix.py
	@python3 quwoquan_app/test/local_contract/app/ios_runtime_dart_defines__local_contract_test.py
	@python3 quwoquan_app/test/local_contract/app/ios_hot_restart_launcher__local_contract_test.py
	@python3 quwoquan_app/test/local_contract/app/startup_probe_parser__local_contract_test.py

verify-app-ios-hot-restart:
	@test -n "$(IOS_SIMULATOR_ID)" || { echo "IOS_SIMULATOR_ID is required"; exit 2; }
	@PYTHONPATH=. python3 quwoquan_app/scripts/device/verify_ios_hot_restart.py \
		--env alpha \
		--device-id "$(IOS_SIMULATOR_ID)"

verify-app-startup-environment-uat:
	@test -n "$(STARTUP_EVIDENCE_ROOT)" || { echo "GATE_BLOCK: STARTUP_EVIDENCE_ROOT is required"; exit 2; }
	@test -n "$(STARTUP_BASELINE_ID)" || { echo "GATE_BLOCK: STARTUP_BASELINE_ID is required"; exit 2; }
	@test -n "$(STARTUP_RELEASE_ID)" || { echo "GATE_BLOCK: STARTUP_RELEASE_ID is required"; exit 2; }
	@test -n "$(STARTUP_RELEASE_DIGEST)" || { echo "GATE_BLOCK: STARTUP_RELEASE_DIGEST is required"; exit 2; }
	@REPORT_PATH="$$(cd "$(STARTUP_EVIDENCE_ROOT)" && pwd)/startup-environment-matrix-report.json"; \
	python3 quwoquan_app/scripts/runtime/verify_startup_environment_matrix.py \
		--evidence-root "$(STARTUP_EVIDENCE_ROOT)" \
		--require-runtime-evidence \
		--require-readback \
		--require-observability \
		--minimum-runtime-runs 20 \
		--require-physical-release \
		--baseline-id "$(STARTUP_BASELINE_ID)" \
		--release-id "$(STARTUP_RELEASE_ID)" \
		--release-digest "$(STARTUP_RELEASE_DIGEST)" \
		--report "$$REPORT_PATH" && \
	cd quwoquan_app && flutter test \
		test/user_acceptance/quality/performance/startup_dual_platform_matrix__user_acceptance_test.dart \
		--dart-define=QWQ_STARTUP_MATRIX_REPORT="$$REPORT_PATH"

verify-app-startup-observability-release:
	@test -n "$(STARTUP_EVIDENCE_ROOT)" || { echo "GATE_BLOCK: STARTUP_EVIDENCE_ROOT is required"; exit 2; }
	@test -n "$(STARTUP_BASELINE_ID)" || { echo "GATE_BLOCK: STARTUP_BASELINE_ID is required"; exit 2; }
	@test -n "$(STARTUP_RELEASE_ID)" || { echo "GATE_BLOCK: STARTUP_RELEASE_ID is required"; exit 2; }
	@test -n "$(STARTUP_RELEASE_DIGEST)" || { echo "GATE_BLOCK: STARTUP_RELEASE_DIGEST is required"; exit 2; }
	@python3 quwoquan_app/scripts/runtime/verify_startup_environment_matrix.py \
		--evidence-root "$(STARTUP_EVIDENCE_ROOT)" \
		--require-runtime-evidence \
		--require-readback \
		--minimum-runtime-runs 20 \
		--require-physical-release \
		--require-observability \
		--baseline-id "$(STARTUP_BASELINE_ID)" \
		--release-id "$(STARTUP_RELEASE_ID)" \
		--release-digest "$(STARTUP_RELEASE_DIGEST)"

verify-app-experience-observability:
	@python3 quwoquan_app/scripts/runtime/verify_ops_event_schema_completeness.py
	@python3 -m unittest \
		quwoquan_ops.tests.local_contract.test_app_experience_observability__contract__local_contract_test

verify-app-recoverable-error-surface:
	@python3 quwoquan_app/scripts/runtime/verify_app_recoverable_error_surface.py

verify-app-dual-platform-usability-baseline:
	@python3 quwoquan_app/scripts/runtime/verify_dual_platform_usability_baseline.py
	@$(MAKE) verify-app-startup-environment-pr
	@$(MAKE) verify-app-recoverable-error-surface
	@$(MAKE) verify-app-page-horizontal-quality

run-app-dual-platform-usability-matrix:
	@python3 quwoquan_app/scripts/device/run_dual_platform_usability_matrix.py

build-app-startup-environment-matrix:
	@test -n "$(IOS_SIMULATOR_ID)" || { echo "IOS_SIMULATOR_ID is required"; exit 2; }
	@python3 quwoquan_app/scripts/device/build_startup_environment_matrix.py \
		--ios-simulator-id "$(IOS_SIMULATOR_ID)"

verify-app-lib-test-only-symbols:
	@python3 quwoquan_app/scripts/runtime/verify_lib_no_test_only_symbols.py

# lib 不得 import test/ 树；约束由门禁源码直接表达。
verify-app-lib-no-test-import:
	@python3 quwoquan_app/scripts/runtime/verify_lib_no_import_test_tree.py

verify-app-content-ui-boundaries:
	@python3 quwoquan_app/scripts/content/verify_content_ui_directory_boundaries.py

verify-app-remote-config-contract:
	@python3 quwoquan_app/scripts/runtime/verify_app_remote_config_contract.py

verify-app-production-data-source-single-path:
	@python3 quwoquan_app/scripts/runtime/verify_production_data_source_single_path.py
	@python3 -m unittest \
		quwoquan_app.test.local_contract.app.production_release_artifact__local_contract_test

verify-production-wiring-purity: verify-app-mock-isolation verify-app-lib-test-only-symbols verify-app-production-data-source-single-path verify-app-cloud-package-boundaries

verify-app-seed-manifest:
	@python3 quwoquan_app/scripts/env/verify_app_seed_manifests.py

verify-gamma-curated-scenarios:
	@python3 quwoquan_ops/tests/support/environment_seeds/sync_gamma_curated_scenarios.py --check

generate-gamma-curated-scenarios:
	@python3 quwoquan_ops/tests/support/environment_seeds/sync_gamma_curated_scenarios.py --write

fetch-app-bundled-fonts:
	@python3 quwoquan_app/scripts/cli.py fonts fetch

verify-app-bundled-fonts:
	@python3 quwoquan_app/scripts/cli.py fonts verify

check-app-bundled-fonts-updates:
	@python3 quwoquan_app/scripts/cli.py fonts check-updates

verify-app-web-offline-resources:
	@python3 quwoquan_app/scripts/cli.py web verify-offline --build

verify-app-assistant-old-stack-retired:
	@python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_assistant_old_stack_retired.py

verify-avatar-user-pool:
	@python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/gate/verify_avatar_user_pool_consistency.py

probe-avatar-user-pool-gateway:
	@python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/smoke/probe_avatar_user_pool_gateway.py

verify-business-env-data-inventory:
	@python3 quwoquan_app/scripts/env/verify_business_env_data_inventory.py

verify-quwoquan-data:
	@python3 quwoquan_data/scripts/cli.py verify all

.PHONY: verify-data-control-literals
verify-data-control-literals:
	@python3 quwoquan_data/scripts/cli.py verify control-literals

verify-data-release-consistency:
	@if [ -z "$(RELEASE_FILE)" ]; then \
		echo "FAIL: RELEASE_FILE is required. Example: make verify-data-release-consistency RELEASE_FILE=quwoquan_data/publish/env_releases/<releaseId>/gamma.json"; \
		exit 2; \
	fi
	@python3 quwoquan_data/scripts/cli.py verify \
		--data-release-file "$(RELEASE_FILE)" \
		$(if $(PUBLISH_ROOT),--publish-root "$(PUBLISH_ROOT)",) \
		$(if $(PHASE),--phase "$(PHASE)",)

verify-media-release-contract:
	@python3 quwoquan_data/scripts/cli.py verify media-release-contract

verify-login-dependency-config:
	@python3 quwoquan_service/scripts/verify/verify_login_dependency_config.py

verify-markdown-article-no-article-document:
	@python3 quwoquan_app/scripts/content/verify_markdown_article_no_article_document.py

verify-article-contract-purity:
	@python3 quwoquan_app/scripts/content/verify_article_contract_purity.py

verify-app-env-package:
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env alpha >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env beta >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env gamma >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env prod >/dev/null

verify-service-env-package:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make verify-service-env-package SERVICE=content-service"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env alpha --service "$(SERVICE)" --include-services >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env beta --service "$(SERVICE)" --include-services >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env gamma --service "$(SERVICE)" --include-services >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env prod --service "$(SERVICE)" --include-services >/dev/null

verify-env-topology:
	@python3 quwoquan_ops/gate/verify_environment_assembly.py

verify-prod-plane-access-isolation:
	@python3 quwoquan_ops/gate/verify_prod_plane_access_isolation.py

verify-local-port-manifest:
	@python3 quwoquan_ops/gate/verify_local_env_port_manifest.py

verify-public-vs-upstream-url-contract:
	@python3 quwoquan_app/scripts/env/verify_public_vs_upstream_url_contract.py

verify-domain-governance:
	@python3 quwoquan_ops/gate/verify_domain_governance.py

verify-env-packaging:
	@deploy_work_root="$$(mktemp -d "$${TMPDIR:-/tmp}/quwoquan-deploy.XXXXXX")"; \
	trap 'rm -rf "$$deploy_work_root"' EXIT; \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/cli/stackctl.py --output-format json package --env alpha --include-services >/dev/null && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/cli/stackctl.py --output-format json package --env beta --include-services >/dev/null && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/cli/stackctl.py --output-format json package --env gamma --include-services >/dev/null && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/cli/stackctl.py --output-format json package --env prod --include-services >/dev/null && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/gate/verify_environment_packaging_contract.py && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/gate/verify_env_artifact_isolation.py && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_app/scripts/env/verify_prod_package_purity.py

observability-es-up:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py up

observability-es-down:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py down

observability-es-health:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py health

observability-es-bootstrap:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py bootstrap

observability-es-smoke:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py smoke

verify-reliable-task-topology:
	@python3 quwoquan_service/scripts/recommendation/verify_reliable_task_catalog.py
	@python3 quwoquan_service/scripts/recommendation/verify_reliable_task_retention_policy.py
	@python3 quwoquan_service/scripts/runtime/verify_module_permission_scope.py
	@python3 quwoquan_service/scripts/recommendation/verify_reliable_task_migration.py

verify-service-architecture:
	@find . \( -path './.git' -o -path './.qwq_output' \) -prune -o -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -exec rm -rf {} + ; true
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_service_architecture.py

verify-metadata:
	@$(MAKE) -C quwoquan_service verify-metadata

build-app-env:
	@if [ -z "$(ENV)" ]; then \
		echo "FAIL: ENV is required. Example: make build-app-env ENV=beta"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py package --env "$(ENV)"

build-service-env:
	@if [ -z "$(SERVICE)" ] || [ -z "$(ENV)" ]; then \
		echo "FAIL: SERVICE and ENV are required. Example: make build-service-env SERVICE=content-service ENV=beta"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py package --env "$(ENV)" --service "$(SERVICE)" --include-services

stackctl-package:
	@if [ -z "$(ENV)" ]; then \
		echo "FAIL: ENV is required. Example: make stackctl-package ENV=beta INCLUDE_SERVICES=1"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py package --env "$(ENV)" $(if $(SERVICE),--service "$(SERVICE)",) $(if $(INCLUDE_SERVICES),--include-services,)

stackctl-verify:
	@if [ -z "$(PROFILE)" ]; then echo "FAIL: PROFILE is required: baseline|smoke|integration|release"; exit 2; fi
	@python3 quwoquan_ops/cli/stackctl.py verify $(if $(ENV),--env "$(ENV)",) $(if $(TARGET),--target "$(TARGET)",) $(if $(KIND),--kind "$(KIND)",) --profile "$(PROFILE)"

dev-up:
	@python3 quwoquan_ops/cli/stackctl.py up $(if $(ENV),--env "$(ENV)",) $(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",) $(if $(SKIP_APP),--skip-app,) $(if $(ROLLOUT_MODE),--rollout-mode "$(ROLLOUT_MODE)",)

stackctl-up:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-up TARGET=beta-local"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py up --target "$(TARGET)" --workload "$(or $(WORKLOAD),full)" $(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",) $(if $(SKIP_APP),--skip-app,) $(if $(ROLLOUT_MODE),--rollout-mode "$(ROLLOUT_MODE)",)

stackctl-down:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-down TARGET=beta-local"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py down --target "$(TARGET)"

stackctl-status:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-status TARGET=gamma-local"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py status --target "$(TARGET)"

stackctl-health:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-health TARGET=prod-hosted"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py health --target "$(TARGET)" --scope "$(or $(SCOPE),full)"

stackctl-inspect:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-inspect TARGET=prod-hosted SCOPE=all"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py inspect --target "$(TARGET)" --scope "$(or $(SCOPE),all)"

stackctl-doctor:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-doctor TARGET=beta-local"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py doctor --target "$(TARGET)"

stackctl-repair:
	@if [ -z "$(TARGET)" ] || [ -z "$(FIX)" ]; then \
		echo "FAIL: TARGET and FIX are required. Example: make stackctl-repair TARGET=beta-local FIX=restart-stack"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py repair --target "$(TARGET)" --fix "$(FIX)"

stackctl-deploy:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-deploy TARGET=prod-hosted SERVICE=prod-stack FROM_CANDIDATE_DIGEST=sha256:... TO_CANDIDATE_DIGEST=sha256:... RELEASE_MANIFEST=/path/manifest.json RELEASE_EVIDENCE_REF=ghcr.io/...@sha256:... STEP=25"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py deploy --target "$(TARGET)" $(if $(STAGE),--stage "$(STAGE)",) $(if $(SERVICE),--service "$(SERVICE)",) $(if $(FROM_CANDIDATE_DIGEST),--from-candidate-digest "$(FROM_CANDIDATE_DIGEST)",) $(if $(TO_CANDIDATE_DIGEST),--to-candidate-digest "$(TO_CANDIDATE_DIGEST)",) $(if $(RELEASE_MANIFEST),--release-manifest "$(RELEASE_MANIFEST)",) $(if $(RELEASE_EVIDENCE_REF),--release-evidence-ref "$(RELEASE_EVIDENCE_REF)",) $(if $(STEP),--step "$(STEP)",)

verify-env-instance-isolation:
	@python3 quwoquan_service/scripts/runtime/verify_env_instance_isolation.py

test-app-alpha-seed:
	@python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/local_contract/cloud/services/contract_seeded_mock_repository__local_contract_test.dart

test-app-beta-seed:
	@python3 quwoquan_app/scripts/env/run_app_alpha_beta_seed_matrix.py

beta-up:
	@DEVICE_ID="$(DEVICE_ID)" \
	AUTO_OPEN_OPS="$(AUTO_OPEN_OPS)" \
	SEED_VERIFY_MODE="$(SEED_VERIFY_MODE)" \
	MEDIA_MODE="$(MEDIA_MODE)" \
	LOCAL_PUBLIC_HOST="$(LOCAL_PUBLIC_HOST)" \
	GATEWAY_BASE_URL_OVERRIDE="$(GATEWAY_BASE_URL_OVERRIDE)" \
	python3 quwoquan_ops/cli/stackctl.py up --target beta-local \
		$(if $(filter 0,$(START_APP)),--skip-app,) \
		$(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",) \
		$(if $(WORKLOAD),--workload "$(WORKLOAD)",)

beta-down:
	@python3 quwoquan_ops/cli/stackctl.py down --target beta-local

beta-status:
	@python3 quwoquan_ops/cli/stackctl.py status --target beta-local

# 页面质量：磁盘页面、canonical page object、route/surface 与强类型展示契约一致。
verify-app-page-horizontal-quality: verify-app-page-object-contract
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --quiet

verify-app-page-object-contract:
	@python3 quwoquan_app/scripts/runtime/verify_page_object_contract.py

verify-app-native-edge-navigation:
	@python3 quwoquan_app/scripts/runtime/verify_native_edge_navigation.py

verify-app-pageflip-back-mainline:
	@python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/local_contract/ui/components/pageflip/pageflip_contract__local_contract_test.dart test/local_contract/quality/shared/pageflip/pageflip_diagnostics_visual__local_contract_test.dart test/local_contract/ui/components/pageflip/pageflip_widget__local_contract_test.dart

# 后翻路线 B 主线静态门禁（见 .cursor/rules/12-pageflip-backward-mainline.mdc）。
verify-app-pageflip-backward-mainline:
	@python3 quwoquan_app/scripts/content/verify_pageflip_backward_mainline.py

# 页面 A/B/C 专项扫描；默认仅报告，按需加 --enforce-*。
verify-app-page-abc-governance:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py

verify-app-page-abc-governance-enforce-a:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-a

verify-app-page-abc-governance-enforce-b:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-b

verify-app-page-abc-governance-enforce-c:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-c

verify-app-page-abc-governance-enforce-all:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-a --enforce-b --enforce-c

# user_profile 头像 projection：凡暴露 avatar URL，必须显式带版本字段。
verify-app-user-profile-avatar-projection-versions:
	@python3 quwoquan_app/scripts/runtime/verify_user_profile_avatar_projection_versions.py

# UI 层 Map<String,dynamic> 字面量防回退（见 quwoquan_ops/policies/gates/ui_map_literal_budget.json）
verify-app-ui-map-literal-budget:
	@python3 quwoquan_app/scripts/runtime/verify_ui_map_literal_budget.py

verify-retired-terms-zero:
	@python3 quwoquan_app/scripts/runtime/verify_retired_terms_zero.py

# 推荐标签链路 StrictTyping：禁裸 Future<dynamic>/Future<Object?> 返回契约（cloud/services/tag）
verify-app-cloud-tag-strict-typing:
	@python3 quwoquan_app/scripts/runtime/verify_cloud_tag_strict_typing.py

verify-global-increment-constraints:
	@bash quwoquan_ops/gate/scaffold/verify_global_increment_constraints.sh

verify-agent-context-contract:
	@python3 quwoquan_ops/gate/verify_agent_context_contract.py

verify-retired-runtime-architecture:
	@python3 quwoquan_ops/gate/verify_retired_runtime_architecture.py

verify-service-ddd-cqrs-baseline:
	@$(MAKE) -C quwoquan_service verify-ddd-cqrs-baseline

verify-commercial-contract-generation:
	@python3 quwoquan_ops/gate/verify_commercial_contract_generation.py

verify-behavior-event-type-contract:
	@python3 quwoquan_ops/gate/verify_behavior_event_type_contract.py

verify-object-relation-edge-type-contract:
	@python3 quwoquan_ops/gate/verify_object_relation_edge_type_contract.py

verify-homepage-type-contract:
	@python3 quwoquan_ops/gate/verify_homepage_type_contract.py

verify-tag-collection-wiring:
	@python3 quwoquan_ops/gate/verify_tag_collection_wiring.py

verify-app-cloud-runtime-single-path:
	@python3 quwoquan_app/scripts/runtime/verify_cloud_runtime_single_path.py

verify-app-cloud-security-cutovers:
	@python3 quwoquan_app/scripts/runtime/verify_cloud_security_cutovers.py

accept-app-contract-handoff:
	@python3 quwoquan_ops/cli/cloud_contract_handoff.py accept

verify-app-contract-handoff:
	@python3 quwoquan_ops/cli/cloud_contract_handoff.py verify

verify-app-generated-manifest:
	@python3 quwoquan_app/scripts/runtime/verify_app_generated_manifest.py

verify-app-cloud-package-boundaries:
	@python3 quwoquan_app/scripts/runtime/verify_cloud_package_boundaries.py

# 助手手写（排除 generated）+ search_repository：Map/dynamic 只减不增棘轮。
verify-app-assistant-search-weak-typing-ratchet:
	@python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_assistant_search_weak_typing_ratchet.py

verify-assistant-agent-replay-evaluation:
	@cd quwoquan_service/services/assistant-service && go test ./tests/local_contract/assistant/assistant_conversation -run '^TestAgentReplayEvaluationGate$$' -count=1

gate:
	@$(MAKE) verify-global-increment-constraints
	@$(MAKE) verify-agent-context-contract
	@$(MAKE) verify-retired-runtime-architecture
	@$(MAKE) verify-service-ddd-cqrs-baseline
	@$(MAKE) verify-service-architecture
	@$(MAKE) verify-commercial-contract-generation
	@$(MAKE) verify-behavior-event-type-contract
	@$(MAKE) verify-object-relation-edge-type-contract
	@$(MAKE) verify-homepage-type-contract
	@$(MAKE) verify-app-cloud-runtime-single-path
	@$(MAKE) verify-app-contract-handoff
	@$(MAKE) verify-app-generated-manifest
	@$(MAKE) verify-app-cloud-package-boundaries
	@$(MAKE) verify-app-cloud-security-cutovers
	@$(MAKE) verify-feature-tree
	@$(MAKE) verify-assistant-agent-replay-evaluation
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-no-fake
	@$(MAKE) verify-test-nonfunctional-coverage
	# local_contract 只在 gate_repo scope 内跑一次，禁止与 test-local-contract 双跑。
	@$(MAKE) verify-reliable-task-topology
	@$(MAKE) verify-avatar-user-pool
	@$(MAKE) probe-avatar-user-pool-gateway
	@$(MAKE) verify-markdown-article-no-article-document
	@$(MAKE) verify-article-contract-purity
	@python3 quwoquan_ops/cli/stackctl.py verify --kind all --profile baseline
	@bash quwoquan_ops/gate/gate_repo.sh

# 环境端口与 gamma 验证 profile 分别由顶层端口清单和 gamma/validation_suites.json 定义。
gate-local-gamma:
	@if [ "$${LOCAL_GAMMA_DRY_RUN:-0}" = "1" ]; then \
		python3 quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py --dry-run; \
	else \
		set -e; \
		LG_HTTP_PORT="$${LOCAL_GAMMA_HTTP_PORT:-19000}"; \
		LG_PRODUCT_OPS_PORT="$${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"; \
		LG_MEDIA_PORT="$${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"; \
		LG_USER_PORT="$${LOCAL_GAMMA_USER_PORT:-19210}"; \
		export LOCAL_GAMMA_HTTP_PORT="$$LG_HTTP_PORT"; \
		export LOCAL_GAMMA_PRODUCT_OPS_PORT="$$LG_PRODUCT_OPS_PORT"; \
		export LOCAL_GAMMA_MEDIA_EDGE_PORT="$$LG_MEDIA_PORT"; \
		export LOCAL_GAMMA_USER_PORT="$$LG_USER_PORT"; \
		if [ "$${LOCAL_GAMMA_SKIP_GATE:-1}" != "1" ]; then $(MAKE) gate; fi; \
		$(MAKE) verify-app-env-package; \
		$(MAKE) verify-app-seed-manifest; \
		python3 quwoquan_ops/cli/stackctl.py up --env gamma --skip-app --workload full; \
		python3 quwoquan_app/scripts/gamma/run_local_gamma_t3.py; \
		bash quwoquan_app/scripts/gamma/run_local_gamma_t4.sh; \
		python3 quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py; \
	fi

gate-runtime-media:
	@bash quwoquan_ops/gate/gate_runtime_media.sh

gate-runtime-media-full:
	@bash quwoquan_ops/gate/gate_runtime_media.sh --full

# 群头像四环境证据机器校验（须提供 .qwq_output 中的 non-dry-run manifest）
verify-chat-avatar-commercial-matrix:
	@if [ -z "$(COMMERCIAL_MATRIX_MANIFEST)" ]; then \
		echo "FAIL: 请设置 COMMERCIAL_MATRIX_MANIFEST=$(QWQ_OUTPUT_ROOT)/env/repo/runs/commercial-matrix-chat-avatar/manifest.yaml"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/gate/verify_chat_avatar_commercial_matrix_evidence.py --manifest "$(COMMERCIAL_MATRIX_MANIFEST)"

feature-context:
	@if [ -z "$(TARGET)" ]; then echo "GATE_BLOCK: 请设置 TARGET=<spec-or-code-path>"; exit 2; fi
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py context --target "$(TARGET)"

feature-tree-overview:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py overview

feature-tree-change-report:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py change-report

feature-tree-content-review:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree_content_review.py

verify-feature-tree:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py verify --changes
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree_content_review.py

verify:
	@$(MAKE) verify-global-increment-constraints
	@$(MAKE) verify-agent-context-contract
	@$(MAKE) verify-retired-runtime-architecture
	@$(MAKE) verify-service-ddd-cqrs-baseline
	@$(MAKE) verify-service-architecture
	@$(MAKE) verify-commercial-contract-generation
	@$(MAKE) verify-app-cloud-runtime-single-path
	@$(MAKE) verify-app-contract-handoff
	@$(MAKE) verify-app-generated-manifest
	@$(MAKE) verify-app-cloud-package-boundaries
	@$(MAKE) verify-app-cloud-security-cutovers
	@$(MAKE) verify-feature-tree
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-nonfunctional-coverage
	@$(MAKE) verify-feature-tree
	@bash quwoquan_service/scripts/contract/verify_contract_metadata.sh
	@bash quwoquan_ops/environments/verify/verify_service_domain_layout.sh
	@bash quwoquan_service/scripts/runtime/verify_runtime_packaging.sh
	@bash quwoquan_ops/environments/verify/verify_ff_config_contract.sh
	@$(MAKE) verify-reliable-task-topology
	@bash quwoquan_service/scripts/recommendation/verify_recommendation_service_contract.sh
	@$(MAKE) verify-quwoquan-data

codegen:
	@$(MAKE) -C quwoquan_service codegen

codegen-observability-catalog:
	@$(MAKE) -C quwoquan_service codegen-observability-catalog

verify-observability-catalog:
	@$(MAKE) -C quwoquan_service verify-observability-catalog

verify-runtime-log-governance:
	@python3 quwoquan_ops/gate/verify_runtime_log_governance.py

codegen-app:
	@$(MAKE) verify-app-contract-handoff
	@$(MAKE) -C quwoquan_service codegen-app
	@$(MAKE) verify-app-generated-manifest

codegen-ops-portal:
	@$(MAKE) -C quwoquan_service codegen-ops-portal

codegen-control-plane-runtime:
	@$(MAKE) -C quwoquan_service codegen-control-plane-runtime

codegen-chat-service:
	@$(MAKE) -C quwoquan_service codegen-chat-service

codegen-content-service:
	@$(MAKE) -C quwoquan_service codegen-content-service

# Create one metadata-owned, object-first service vertical slice.
# Usage:
#   make new-service SERVICE=user-service CONTEXT=user.account OBJECT=user_account LANGUAGE=go
new-service:
	@if [ -z "$(SERVICE)" ] || [ -z "$(CONTEXT)" ] || [ -z "$(OBJECT)" ] || [ -z "$(LANGUAGE)" ]; then \
		echo "FAIL: SERVICE, CONTEXT, OBJECT and LANGUAGE are required"; \
		echo "Example: make new-service SERVICE=user-service CONTEXT=user.account OBJECT=user_account LANGUAGE=go"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/gate/scaffold/new_service.py \
		--service "$(SERVICE)" \
		--context "$(CONTEXT)" \
		--object "$(OBJECT)" \
		--language "$(LANGUAGE)"

# Evaluate SLO gate decision for a rollout stage.
# Example:
# make config-slo-gate ERROR_RATE=0.005 P95_MS=180 REDIS_ERROR_RATE=0.001
config-slo-gate:
	@if [ -z "$(ERROR_RATE)" ] || [ -z "$(P95_MS)" ] || [ -z "$(REDIS_ERROR_RATE)" ]; then \
		echo "FAIL: ERROR_RATE/P95_MS/REDIS_ERROR_RATE are required"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py verify --kind config-slo --profile baseline --error-rate "$(ERROR_RATE)" --p95-ms "$(P95_MS)" --redis-error-rate "$(REDIS_ERROR_RATE)"

.PHONY: commit-gate gate-smoke gate-integration gate-release test-api-contract test-api-contract-chat

# L0 本地入库门禁（pre-commit 同源）：并行静态 + 影响面测试，目标 ≤10m / 硬顶 15m。
commit-gate:
	@bash quwoquan_ops/gate/commit_gate.sh
.PHONY: prepare-test-python verify-test-no-fake verify-test-nonfunctional-coverage verify-test-directory-layout verify-test-coverage-map
.PHONY: verify-execution-profiles
.PHONY: test-local-contract test-runtime-local-contract test-api-integration test-runtime-api-integration test-runtime-api-integration-gamma test-user-acceptance

prepare-test-python:
	@python3 quwoquan_ops/cli/prepare_test_python.py

verify-test-no-fake:
	@python3 quwoquan_ops/gate/scaffold/verify_test_no_fake.py

verify-test-nonfunctional-coverage:
	@python3 quwoquan_ops/gate/scaffold/verify_runtime_error_coverage.py
	@python3 quwoquan_ops/gate/scaffold/verify_security_coverage.py
	@python3 quwoquan_ops/gate/scaffold/verify_performance_budget.py
	@python3 quwoquan_ops/gate/scaffold/verify_observability_coverage.py
	@python3 quwoquan_ops/gate/scaffold/verify_data_consistency_coverage.py

verify-test-directory-layout:
	@python3 quwoquan_ops/gate/scaffold/verify_test_directory_layout.py

verify-test-coverage-map:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py verify
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/scaffold/verify_test_coverage_map.py

verify-execution-profiles:
	@python3 quwoquan_ops/gate/verify_execution_profiles.py

verify-test-remote-env:
	@python3 quwoquan_ops/gate/scaffold/verify_test_remote_env.py --suite "$${MODE:?set MODE=api_integration|user_acceptance}" --env "$${ENV:-gamma}" --target "$${TARGET:-gamma-local}"

test-runtime-local-contract:
	@cd quwoquan_service && go test ./runtime/... -count=1 -p=$(GO_TEST_PACKAGE_PARALLELISM)

test-runtime-api-integration:
	@$(MAKE) -C quwoquan_service test-runtime-api-integration

test-runtime-api-integration-gamma:
	@bash quwoquan_ops/cli/gamma/run_reliabletask_gamma_api_integration.sh

test-local-contract:
	@$(MAKE) prepare-test-python
	@$(DATA_PYTHON) -c 'import pytest' || { echo "[test-local-contract] FAIL: DATA_PYTHON missing pytest: $(DATA_PYTHON)"; exit 1; }
	@$(MAKE) verify-feature-tree
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-no-fake
	@$(MAKE) verify-test-nonfunctional-coverage
	@$(MAKE) verify-execution-profiles
	@bash quwoquan_service/scripts/contract/verify_contract_metadata.sh
	@$(MAKE) test-runtime-local-contract
	@python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/local_contract/
	@cd quwoquan_service && go test $$(go list ./services/... | grep -v '/tests/api_integration') -count=1 -p=$(GO_TEST_PACKAGE_PARALLELISM)
	@mkdir -p "$(QWQ_OUTPUT_ROOT)/env/repo/runs/tests"
	@rm -rf "$(QWQ_OUTPUT_ROOT)/env/repo/runs/tests"/data-local-contract.*
	@DATA_TEST_OUTPUT_ROOT="$$(mktemp -d "$(QWQ_OUTPUT_ROOT)/env/repo/runs/tests/data-local-contract.XXXXXX")"; \
		trap 'rm -rf "$$DATA_TEST_OUTPUT_ROOT"' EXIT; \
		QWQ_OUTPUT_ROOT="$$DATA_TEST_OUTPUT_ROOT" $(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) \
			quwoquan_data/tests/local_contract quwoquan_ops/tests/local_contract -q; \
		status=$$?; \
		rm -rf "$$DATA_TEST_OUTPUT_ROOT"; \
		trap - EXIT; \
		exit $$status
	@rm -rf "$(QWQ_OUTPUT_ROOT)/env/repo/runs/tests"/data-local-contract.*
	@python3 quwoquan_data/scripts/verify/verify_data_layout.py

# api_integration：按统一环境名解析 HTTP 基址。API_CONTRACT_ENV 默认为 gamma。
# 变量格式：{ALPHA|BETA|GAMMA|PROD}_BASE_URL 与 *_PRODUCT_OPS_BASE_URL。
test-api-contract:
	@ENV_NAME="$${API_CONTRACT_ENV:-gamma}"; \
	case "$$ENV_NAME" in \
		alpha) BASE_URL="$${ALPHA_BASE_URL:-}"; OPS_BASE_URL="$${ALPHA_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${ALPHA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		beta) BASE_URL="$${BETA_BASE_URL:-}"; OPS_BASE_URL="$${BETA_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${BETA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		gamma) BASE_URL="$${GAMMA_BASE_URL:-}"; OPS_BASE_URL="$${GAMMA_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		prod) BASE_URL="$${PROD_BASE_URL:-}"; OPS_BASE_URL="$${PROD_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${PROD_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		*) echo "[L3] FAIL: API_CONTRACT_ENV must be one of alpha|beta|gamma|prod, got $$ENV_NAME"; exit 2 ;; \
	esac; \
	if [ -z "$$BASE_URL" ] || [ -z "$$OPS_BASE_URL" ]; then \
		echo "[L3] FAIL: set $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_BASE_URL and $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_PRODUCT_OPS_BASE_URL"; \
		exit 2; \
	fi; \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/cloud/content/api_contract_runner.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL \
		--dart-define=LOCAL_GAMMA_T3_SCOPE=$${LOCAL_GAMMA_T3_SCOPE:-} \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN && \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/cloud/user/user_api_contract_runner.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL && \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/cloud/ops/api_contract_runner.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL=$$OPS_BASE_URL \
		--dart-define=API_CONTRACT_AUTH_BASE_URL=$$BASE_URL

test-api-contract-chat:
	@ENV_NAME="$${API_CONTRACT_ENV:-gamma}"; \
	case "$$ENV_NAME" in \
		alpha) BASE_URL="$${ALPHA_BASE_URL:-}"; AUTH_TOKEN="$${ALPHA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		beta) BASE_URL="$${BETA_BASE_URL:-}"; AUTH_TOKEN="$${BETA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		gamma) BASE_URL="$${GAMMA_BASE_URL:-}"; AUTH_TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		prod) BASE_URL="$${PROD_BASE_URL:-}"; AUTH_TOKEN="$${PROD_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		*) echo "[L3] FAIL: API_CONTRACT_ENV must be one of alpha|beta|gamma|prod, got $$ENV_NAME"; exit 2 ;; \
	esac; \
	if [ -z "$$BASE_URL" ]; then \
		echo "[L3] FAIL: set $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_BASE_URL"; \
		exit 2; \
	fi; \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/cloud/chat/api_contract_runner.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN

test-app-api-integration:
	@ENV_NAME="$${ENV:-gamma}"; \
	case "$$ENV_NAME" in \
		beta) BASE_URL="$${BETA_BASE_URL:-}"; AUTH_TOKEN="$${BETA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		gamma) BASE_URL="$${GAMMA_BASE_URL:-}"; AUTH_TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		prod) BASE_URL="$${PROD_BASE_URL:-}"; AUTH_TOKEN="$${PROD_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		*) echo "[api_integration] FAIL: ENV must be one of beta|gamma|prod, got $$ENV_NAME"; exit 2 ;; \
	esac; \
	if [ -z "$$BASE_URL" ]; then \
		echo "[api_integration] FAIL: set $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_BASE_URL"; \
		exit 2; \
	fi; \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/cloud/assistant/personal_assistant_weather_ui__api_integration_test.dart test/api_integration/cloud/assistant/personal_assistant_official_sources__api_integration_test.dart test/api_integration/cloud/assistant/personal_assistant_multiturn__functional__api_integration_test.dart \
		--dart-define=APP_RUNTIME_ENV=beta \
		--dart-define=APP_DATA_SOURCE=remote \
		--dart-define=CLOUD_GATEWAY_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN && \
	ASSISTANT_SCENARIO_FIXTURE_B64="$$(python3 - <<'PY'\nimport base64\nfrom pathlib import Path\npath = Path('quwoquan_service/services/assistant-service/tests/support/contract_fixtures/scenarios/assistant_scenarios.json')\nprint(base64.b64encode(path.read_bytes()).decode('ascii'))\nPY\n)" && \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/cloud/assistant/assistant_scenario_simulator__api_integration_test.dart \
		--dart-define=APP_RUNTIME_ENV=beta \
		--dart-define=APP_DATA_SOURCE=remote \
		--dart-define=CLOUD_GATEWAY_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN \
		--dart-define=ASSISTANT_SCENARIO_FIXTURE_JSON_B64=$$ASSISTANT_SCENARIO_FIXTURE_B64 && \
	ASSISTANT_EVAL_FIXTURE_B64="$$(python3 - <<'PY'\nimport base64\nfrom pathlib import Path\npath = Path('quwoquan_service/services/assistant-service/tests/support/contract_fixtures/scenarios/assistant_skill_eval_scenarios.json')\nprint(base64.b64encode(path.read_bytes()).decode('ascii'))\nPY\n)" && \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/cloud/assistant/assistant_skill_comparison__api_integration_test.dart \
		--dart-define=APP_RUNTIME_ENV=beta \
		--dart-define=APP_DATA_SOURCE=remote \
		--dart-define=CLOUD_GATEWAY_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN \
		--dart-define=ASSISTANT_SCENARIO_FIXTURE_JSON_B64=$$ASSISTANT_EVAL_FIXTURE_B64

test-api-integration:
	@$(MAKE) prepare-test-python
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-remote-env MODE=api_integration ENV="$${ENV:-gamma}"
	@$(MAKE) test-runtime-api-integration
	@$(MAKE) test-app-api-integration ENV="$${ENV:-gamma}"
	@cd quwoquan_service && go test $$(go list ./services/... | rg '/tests/api_integration') -count=1 -p=$(API_INTEGRATION_GO_TEST_PACKAGE_PARALLELISM)
	@$(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) quwoquan_data/tests/api_integration quwoquan_ops/tests/acceptance/api_integration -q
	@$(MAKE) test-api-contract API_CONTRACT_ENV="$${ENV:-gamma}"
	@$(MAKE) test-api-contract-chat API_CONTRACT_ENV="$${ENV:-gamma}"

test-user-acceptance:
	@$(MAKE) prepare-test-python
	@$(MAKE) verify-test-remote-env MODE=user_acceptance TARGET="$${TARGET:-gamma-local}"
	@TARGET_NAME="$${TARGET:-gamma-local}"; \
	case "$$TARGET_NAME" in \
		local) python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/user_acceptance/ && $(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) quwoquan_data/tests/user_acceptance quwoquan_ops/tests/acceptance/user_acceptance -q ;; \
		gamma-local) $(MAKE) gate-local-gamma LOCAL_GAMMA_SKIP_GATE=1 ;; \
		prod-hosted) \
			if [ -z "$${PROD_BASE_URL:-}" ] || [ -z "$${PROD_PRODUCT_OPS_BASE_URL:-}" ]; then \
				echo "[user_acceptance] FAIL: PROD_BASE_URL and PROD_PRODUCT_OPS_BASE_URL are required for prod-hosted"; \
				exit 2; \
			fi; \
			TEST_TOKEN="$${PROD_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}"; \
			if [ -z "$$TEST_TOKEN" ]; then \
				echo "[user_acceptance] FAIL: PROD_TEST_AUTH_TOKEN or TEST_AUTH_TOKEN is required for prod-hosted"; \
				exit 2; \
			fi; \
			DRY_RUN_FLAG=""; \
			if [ "$${USER_ACCEPTANCE_DRY_RUN:-0}" = "1" ]; then \
				DRY_RUN_FLAG="--dry-run"; \
			elif ! command -v patrol >/dev/null 2>&1; then \
				echo "[user_acceptance] GATE_BLOCK: patrol CLI not found; install patrol or set USER_ACCEPTANCE_DRY_RUN=1 for wiring-only verification"; \
				exit 2; \
			fi; \
			python3 quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py \
				--report "$${PROD_USER_ACCEPTANCE_REPORT:-$(QWQ_OUTPUT_ROOT)/env/prod/runs/device-matrix/environment-smoke-prod-rollout-gray-initial.json}" \
				--env-name prod \
				--rollout-stage gray-initial \
				--runtime-env prod \
				--api-contract-env prod \
				--data-source remote \
				--gateway-base-url "$${PROD_BASE_URL}" \
				--product-ops-base-url "$${PROD_PRODUCT_OPS_BASE_URL}" \
				--media-avatar-base-url "$${PROD_MEDIA_AVATAR_BASE_URL}" \
				--media-image-base-url "$${PROD_MEDIA_IMAGE_BASE_URL}" \
				--media-video-base-url "$${PROD_MEDIA_VIDEO_BASE_URL}" \
				--media-upload-base-url "$${PROD_MEDIA_UPLOAD_BASE_URL}" \
				--rtc-media-connection-url "$${PROD_RTC_MEDIA_CONNECTION_URL}" \
				--test-auth-token "$$TEST_TOKEN" \
				$$DRY_RUN_FLAG ;; \
		*) echo "[user_acceptance] FAIL: TARGET must be local, gamma-local or prod-hosted, got $$TARGET_NAME"; exit 2 ;; \
	esac

gate-smoke:
	@$(MAKE) gate
	@python3 quwoquan_ops/cli/stackctl.py verify --env alpha --kind all --profile smoke

gate-integration:
	@if [ "$(ENV)" != "beta" ] && [ "$(ENV)" != "gamma" ]; then echo "FAIL: ENV must be beta or gamma"; exit 2; fi
	@$(MAKE) gate
	@python3 quwoquan_ops/cli/stackctl.py verify --env "$(ENV)" --kind all --profile integration

gate-release:
	@if [ "$(ENV)" != "gamma" ] && [ "$(ENV)" != "prod" ]; then echo "FAIL: ENV must be gamma or prod"; exit 2; fi
	@$(MAKE) gate
	@$(MAKE) test-runtime-api-integration
	@python3 quwoquan_ops/gate/verify_provider_conformance_evidence.py --require-ready "$(ENV)"
	@python3 quwoquan_ops/cli/stackctl.py verify --env "$(ENV)" --kind all --profile release

# Deploy to beta integration K8s. CLOUD_PROVIDER=aliyun|volcengine|huaweicloud (default: aliyun).
# Usage: make deploy-beta-k8s [CLOUD_PROVIDER=volcengine]
.PHONY: deploy-beta-k8s
deploy-beta-k8s:
	@python3 quwoquan_ops/cli/stackctl.py deploy --env beta --mode environment-assembly
