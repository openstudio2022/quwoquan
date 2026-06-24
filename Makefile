.PHONY: gate
.PHONY: gate-local-gamma
.PHONY: gate-runtime-media
.PHONY: gate-runtime-media-full
.PHONY: verify-chat-avatar-commercial-matrix
.PHONY: run-chat-avatar-commercial-matrix-local
.PHONY: verify-app-mock-isolation
.PHONY: verify-app-runtime-host-literals
.PHONY: verify-app-concept-naming
.PHONY: verify-app-auth-policy
.PHONY: verify-app-domain-error-code-registry
.PHONY: verify-app-behavior-error-stack-convergence
.PHONY: verify-app-login-entry-loop-contract
.PHONY: verify-app-lib-no-test-import
.PHONY: verify-app-page-horizontal-quality
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
.PHONY: verify-app-session-b-current
.PHONY: verify-app-assistant-search-weak-typing-ratchet
.PHONY: verify-app-assistant-old-stack-retired
.PHONY: verify-retired-terms-zero
.PHONY: verify-app-ui-app-data-source-mode-ratchet
.PHONY: verify-app-seed-manifest
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
.PHONY: verify-sms-otp-fail-open-gate
.PHONY: verify-env-packaging
.PHONY: verify-env-instance-isolation
.PHONY: observability-es-up
.PHONY: observability-es-down
.PHONY: observability-es-health
.PHONY: observability-es-bootstrap
.PHONY: observability-es-smoke
.PHONY: verify-reliable-task-topology
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
.PHONY: verify-data-role-gate-inventory
.PHONY: codegen
.PHONY: codegen-app
.PHONY: codegen-ops-portal
.PHONY: codegen-control-plane-runtime
.PHONY: codegen-content-service
.PHONY: codegen-chat-service
.PHONY: bootstrap-service-config
.PHONY: new-service
.PHONY: config-gray-rollout
.PHONY: config-rollback
.PHONY: config-slo-gate
.PHONY: stackctl-package
.PHONY: stackctl-verify
.PHONY: stackctl-up
.PHONY: stackctl-down
.PHONY: stackctl-status

PYTEST_RUNNER ?= $(shell if [ -x quwoquan_data/.venv/bin/python ]; then printf '%s' quwoquan_data/.venv/bin/python; else printf '%s' python3; fi)
.PHONY: stackctl-health
.PHONY: stackctl-inspect
.PHONY: stackctl-doctor
.PHONY: stackctl-repair
.PHONY: stackctl-deploy

# 客户端：UI/App/Core 不得直连 cloud/services/*/mock（过渡期见 specs/gates/ui_mock_isolation_allowlist.yaml）
verify-app-mock-isolation:
	@python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py

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

verify-app-lib-test-only-symbols:
	@python3 quwoquan_app/scripts/runtime/verify_lib_no_test_only_symbols.py

# lib 不得 import test/ 树（见 specs/gates/mock_test_separation_roadmap.md）
verify-app-lib-no-test-import:
	@python3 quwoquan_app/scripts/runtime/verify_lib_no_import_test_tree.py

verify-app-remote-config-contract:
	@python3 quwoquan_app/scripts/runtime/verify_app_remote_config_contract.py

# UI 层 AppDataSourceMode.mock / appDataSourceModeProvider 引用棘轮（见 specs/gates/ui_app_data_source_mode_baseline.json）
verify-app-ui-app-data-source-mode-ratchet:
	@python3 quwoquan_app/scripts/env/verify_ui_app_data_source_mode_ratchet.py

verify-app-seed-manifest:
	@python3 quwoquan_app/scripts/env/verify_app_seed_manifests.py

fetch-app-bundled-fonts:
	@python3 quwoquan_app/scripts/cli.py fonts fetch

verify-app-bundled-fonts:
	@python3 quwoquan_app/scripts/cli.py fonts verify

check-app-bundled-fonts-updates:
	@python3 quwoquan_app/scripts/cli.py fonts check-updates

verify-app-web-offline-resources:
	@python3 quwoquan_app/scripts/cli.py web verify-offline --build

verify-app-assistant-old-stack-retired:
	@python3 agent_ops/assistant/verify_assistant_old_stack_retired.py

verify-avatar-user-pool:
	@python3 agent_ops/avatar/verify_avatar_user_pool_consistency.py

probe-avatar-user-pool-gateway:
	@python3 agent_ops/avatar/probe_avatar_user_pool_gateway.py

verify-business-env-data-inventory:
	@python3 quwoquan_app/scripts/env/verify_business_env_data_inventory.py

verify-quwoquan-data:
	@bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh

verify-data-role-gate-inventory:
	@python3 quwoquan_data/scripts/cli.py verify data-role-gate

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
	@python3 quwoquan_data/scripts/verify/verify_media_release_contract.py

verify-sms-otp-fail-open-gate:
	@python3 quwoquan_service/scripts/verify/verify_sms_otp_fail_open_gate.py

verify-markdown-article-no-article-document:
	@python3 quwoquan_app/scripts/content/verify_markdown_article_no_article_document.py

verify-article-contract-purity:
	@python3 quwoquan_app/scripts/content/verify_article_contract_purity.py

.PHONY: verify-quwoquan-data-stages
verify-quwoquan-data-stages:
	@python3 -c "import sys; sys.path.insert(0,'quwoquan_data/lib'); from normalization.validators import load_schema; print('[schema] All schemas loadable')"
	@python3 quwoquan_data/scripts/cli.py data explore --query "smoke-test" > /dev/null

verify-app-env-package:
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env alpha >/dev/null
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env beta >/dev/null
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env gamma >/dev/null
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env prod >/dev/null

verify-service-env-package:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make verify-service-env-package SERVICE=content-service"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env alpha --service "$(SERVICE)" --include-services >/dev/null
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env beta --service "$(SERVICE)" --include-services >/dev/null
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env gamma --service "$(SERVICE)" --include-services >/dev/null
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env prod --service "$(SERVICE)" --include-services >/dev/null

verify-env-topology:
	@python3 agent_ops/gate/verify_environment_topology_manifest.py

verify-prod-plane-access-isolation:
	@python3 agent_ops/gate/verify_prod_plane_access_isolation.py

verify-local-port-manifest:
	@python3 agent_ops/gate/verify_local_env_port_manifest.py

verify-public-vs-upstream-url-contract:
	@python3 quwoquan_app/scripts/env/verify_public_vs_upstream_url_contract.py

verify-env-packaging:
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env alpha --include-services >/dev/null
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env beta --include-services >/dev/null
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env gamma --include-services >/dev/null
	@python3 agent_ops/deploy/stackctl.py --output-format json package --env prod --include-services >/dev/null
	@python3 agent_ops/gate/verify_environment_packaging_contract.py
	@python3 agent_ops/gate/verify_env_artifact_isolation.py
	@python3 quwoquan_app/scripts/env/verify_prod_package_purity.py

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
	@python3 quwoquan_app/scripts/runtime/verify_module_package_mapping.py
	@python3 quwoquan_service/scripts/recommendation/verify_reliable_task_catalog.py
	@python3 quwoquan_service/scripts/recommendation/verify_reliable_task_retention_policy.py
	@python3 quwoquan_service/scripts/runtime/verify_module_permission_scope.py
	@python3 quwoquan_service/scripts/recommendation/verify_reliable_task_migration.py

.PHONY: verify-workload-topology-inventory
verify-workload-topology-inventory:
	@python3 quwoquan_service/scripts/deploy/verify_workload_topology_inventory.py
	@python3 quwoquan_service/scripts/deploy/verify_strangler_contract_invariants.py
	@python3 quwoquan_service/scripts/deploy/verify_gamma_local_prod_isomorphism.py

build-app-env:
	@if [ -z "$(ENV)" ]; then \
		echo "FAIL: ENV is required. Example: make build-app-env ENV=beta"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py package --env "$(ENV)"

build-service-env:
	@if [ -z "$(SERVICE)" ] || [ -z "$(ENV)" ]; then \
		echo "FAIL: SERVICE and ENV are required. Example: make build-service-env SERVICE=content-service ENV=beta"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py package --env "$(ENV)" --service "$(SERVICE)" --include-services

stackctl-package:
	@if [ -z "$(ENV)" ]; then \
		echo "FAIL: ENV is required. Example: make stackctl-package ENV=beta INCLUDE_SERVICES=1"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py package --env "$(ENV)" $(if $(SERVICE),--service "$(SERVICE)",) $(if $(INCLUDE_SERVICES),--include-services,)

stackctl-verify:
	@python3 agent_ops/deploy/stackctl.py verify $(if $(ENV),--env "$(ENV)",) $(if $(TARGET),--target "$(TARGET)",) $(if $(KIND),--kind "$(KIND)",) $(if $(TIER),--tier "$(TIER)",)

dev-up:
	@python3 agent_ops/deploy/stackctl.py up $(if $(ENV),--env "$(ENV)",) $(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",) $(if $(SKIP_APP),--skip-app,) $(if $(ROLLOUT_MODE),--rollout-mode "$(ROLLOUT_MODE)",)

stackctl-up:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-up TARGET=beta-local"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py up --target "$(TARGET)" $(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",) $(if $(SKIP_APP),--skip-app,) $(if $(ROLLOUT_MODE),--rollout-mode "$(ROLLOUT_MODE)",)

stackctl-down:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-down TARGET=beta-local"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py down --target "$(TARGET)"

stackctl-status:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-status TARGET=gamma-local"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py status --target "$(TARGET)"

stackctl-health:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-health TARGET=prod-hosted"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py health --target "$(TARGET)" --scope "$(or $(SCOPE),full)"

stackctl-inspect:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-inspect TARGET=prod-hosted SCOPE=all"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py inspect --target "$(TARGET)" --scope "$(or $(SCOPE),all)"

stackctl-doctor:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-doctor TARGET=beta-local"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py doctor --target "$(TARGET)"

stackctl-repair:
	@if [ -z "$(TARGET)" ] || [ -z "$(FIX)" ]; then \
		echo "FAIL: TARGET and FIX are required. Example: make stackctl-repair TARGET=beta-local FIX=restart-stack"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py repair --target "$(TARGET)" --fix "$(FIX)"

stackctl-deploy:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-deploy TARGET=prod-hosted SERVICE=seed-box TO_IMAGE=v1 TO_CONFIG=v2 STEP=50"; \
		exit 2; \
	fi
	@python3 agent_ops/deploy/stackctl.py deploy --target "$(TARGET)" $(if $(STAGE),--stage "$(STAGE)",) $(if $(IMAGE_VERSION),--image-version "$(IMAGE_VERSION)",) $(if $(PREVIOUS_IMAGE_VERSION),--previous-image-version "$(PREVIOUS_IMAGE_VERSION)",) $(if $(BASE_URL),--base-url "$(BASE_URL)",) $(if $(PRODUCT_OPS_BASE_URL),--product-ops-base-url "$(PRODUCT_OPS_BASE_URL)",) $(if $(MEDIA_BASE_URL),--media-base-url "$(MEDIA_BASE_URL)",) $(if $(MEDIA_ORIGIN_BASE_URL),--media-origin-base-url "$(MEDIA_ORIGIN_BASE_URL)",) $(if $(SERVICE),--service "$(SERVICE)",) $(if $(FROM_IMAGE),--from-image "$(FROM_IMAGE)",) $(if $(TO_IMAGE),--to-image "$(TO_IMAGE)",) $(if $(FROM_CONFIG),--from-config "$(FROM_CONFIG)",) $(if $(TO_CONFIG),--to-config "$(TO_CONFIG)",) $(if $(STEP),--step "$(STEP)",) $(if $(ERROR_RATE),--error-rate "$(ERROR_RATE)",) $(if $(P95_MS),--p95-ms "$(P95_MS)",) $(if $(REDIS_ERROR_RATE),--redis-error-rate "$(REDIS_ERROR_RATE)",)

verify-env-instance-isolation:
	@python3 quwoquan_service/scripts/runtime/verify_env_instance_isolation.py

test-app-alpha-seed:
	@python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/cloud/services/contract_seeded_mock_repository_test.dart

test-app-beta-seed:
	@python3 quwoquan_app/scripts/env/run_app_alpha_beta_seed_matrix.py

beta-up:
	@DEVICE_ID="$(DEVICE_ID)" \
	START_APP="$(START_APP)" \
	AUTO_OPEN_OPS="$(AUTO_OPEN_OPS)" \
	CDN_DOMAIN="$(CDN_DOMAIN)" \
	SEED_VERIFY_MODE="$(SEED_VERIFY_MODE)" \
	MEDIA_MODE="$(MEDIA_MODE)" \
	LOCAL_PUBLIC_HOST="$(LOCAL_PUBLIC_HOST)" \
	MEDIA_BASE_URL="$(MEDIA_BASE_URL)" \
	GATEWAY_BASE_URL_OVERRIDE="$(GATEWAY_BASE_URL_OVERRIDE)" \
	bash agent_ops/deploy/beta/start_beta_stack.sh up

beta-down:
	@bash agent_ops/deploy/beta/start_beta_stack.sh down

beta-status:
	@DEVICE_ID="$(DEVICE_ID)" \
	START_APP="$(START_APP)" \
	AUTO_OPEN_OPS="$(AUTO_OPEN_OPS)" \
	bash agent_ops/deploy/beta/start_beta_stack.sh status

# 页面横向质量：矩阵列合法 + 磁盘路径与矩阵一致 + P2 清单 ⊆（与 gate app 段同向子集）
verify-app-page-horizontal-quality:
	@python3 quwoquan_app/scripts/runtime/verify_page_horizontal_quality_matrix.py
	@python3 quwoquan_app/scripts/runtime/verify_page_matrix_scan_complete.py

verify-app-native-edge-navigation:
	@python3 quwoquan_app/scripts/runtime/verify_native_edge_navigation.py

verify-app-pageflip-back-mainline:
	@python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/components/pageflip/backward_sheet_partition_contract_test.dart test/components/pageflip/pageflip_contract_test.dart test/common/pageflip/pageflip_diagnostics_visual_test.dart test/components/pageflip/pageflip_widget_test.dart

# 后翻路线 B 主线静态门禁（见 .cursor/rules/12-pageflip-backward-mainline.mdc）。
verify-app-pageflip-backward-mainline:
	@python3 quwoquan_app/scripts/content/verify_pageflip_backward_mainline.py

# 页面 A/B/C 专项扫描（默认仅报告、exit 0；加 --enforce-* 见 specs/gates/page_abc_governance.md）
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

# UI 层 Map<String,dynamic> 字面量防回退（见 specs/gates/ui_map_literal_budget.json）
verify-app-ui-map-literal-budget:
	@python3 quwoquan_app/scripts/runtime/verify_ui_map_literal_budget.py

verify-app-session-b-current:
	@python3 quwoquan_app/scripts/runtime/verify_session_b_current_governance.py

verify-retired-terms-zero:
	@python3 quwoquan_app/scripts/runtime/verify_retired_terms_zero.py

# 推荐标签链路 StrictTyping：禁裸 Future<dynamic>/Future<Object?> 返回契约（cloud/services/tag）
verify-app-cloud-tag-strict-typing:
	@python3 quwoquan_app/scripts/runtime/verify_cloud_tag_strict_typing.py

verify-global-increment-constraints:
	@bash agent_ops/scaffold/verify_global_increment_constraints.sh

verify-agent-context-contract:
	@python3 agent_ops/gate/verify_agent_context_contract.py

# 助手手写（排除 generated）+ search_repository：Map/dynamic 计数棘轮（见 specs/gates/assistant_search_weak_typing_governance.md）
verify-app-assistant-search-weak-typing-ratchet:
	@python3 agent_ops/avatar/verify_assistant_search_weak_typing_ratchet.py

gate:
	@$(MAKE) verify-global-increment-constraints
	@$(MAKE) verify-agent-context-contract
	@$(MAKE) verify-test-specs
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-no-fake
	@$(MAKE) verify-test-coverage-map
	@$(MAKE) test-local-contract
	@bash quwoquan_service/scripts/deploy/verify_deployment_domain_mapping.sh
	@bash quwoquan_service/scripts/deploy/verify_topology_contract_regression.sh
	@$(MAKE) verify-workload-topology-inventory
	@$(MAKE) verify-reliable-task-topology
	@$(MAKE) verify-avatar-user-pool
	@$(MAKE) probe-avatar-user-pool-gateway
	@$(MAKE) verify-markdown-article-no-article-document
	@$(MAKE) verify-article-contract-purity
	@bash quwoquan_service/scripts/deploy/report_deployment_mapping_impact.sh
	@bash agent_ops/gate/gate_repo.sh

# 前置说明：Docker Hub 限流、Colima 磁盘、构建上下文见 deploy/shared/environment_matrix.md §2.1.1
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
		export LOCAL_GAMMA_GATEWAY_BASE_URL="$${LOCAL_GAMMA_GATEWAY_BASE_URL:-http://127.0.0.1:$$LG_HTTP_PORT}"; \
		export LOCAL_GAMMA_PRODUCT_OPS_BASE_URL="$${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-http://127.0.0.1:$$LG_PRODUCT_OPS_PORT}"; \
		export LOCAL_GAMMA_MEDIA_BASE_URL="$${LOCAL_GAMMA_MEDIA_BASE_URL:-http://127.0.0.1:$$LG_MEDIA_PORT}"; \
		if [ "$${LOCAL_GAMMA_SKIP_GATE:-0}" != "1" ]; then CDN_DOMAIN="$${CDN_DOMAIN:-cdn.beta.local}" $(MAKE) gate; fi; \
		$(MAKE) verify-app-env-package; \
		$(MAKE) verify-app-seed-manifest; \
		bash quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh; \
		python3 quwoquan_app/scripts/gamma/run_local_gamma_t3.py; \
		bash quwoquan_app/scripts/gamma/run_local_gamma_t4.sh; \
		python3 quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py; \
	fi

gate-runtime-media:
	@bash agent_ops/gate/gate_runtime_media.sh

gate-runtime-media-full:
	@bash agent_ops/gate/gate_runtime_media.sh --full

# 群头像商用 E1–E4 证据机器校验（须先有 non-dry-run JSON，见 commercial-e2e-matrix-runbook.md）
verify-chat-avatar-commercial-matrix:
	@if [ -z "$(COMMERCIAL_MATRIX_MANIFEST)" ]; then \
		echo "FAIL: 请设置 COMMERCIAL_MATRIX_MANIFEST=artifacts/commercial-matrix/chat-avatar/manifest.yaml"; \
		exit 2; \
	fi
	@python3 agent_ops/avatar/verify_chat_avatar_commercial_matrix_evidence.py --manifest "$(COMMERCIAL_MATRIX_MANIFEST)"

run-chat-avatar-commercial-matrix-local:
	@bash agent_ops/avatar/run_chat_avatar_commercial_matrix_orchestrator.sh

verify:
	@$(MAKE) verify-global-increment-constraints
	@$(MAKE) verify-agent-context-contract
	@$(MAKE) verify-test-specs
	@$(MAKE) verify-test-directory-layout
	@bash agent_ops/scaffold/verify_feature_traceability.sh
	@bash quwoquan_service/scripts/contract/verify_contract_metadata.sh
	@bash agent_ops/scaffold/verify_acceptance_standard.sh
	@bash agent_ops/scaffold/verify_specs_l1_hierarchy.sh
	@bash agent_ops/scaffold/verify_feature_tree_refactor.sh
	@bash agent_ops/scaffold/verify_engineering_directory.sh
	@bash quwoquan_service/scripts/deploy/verify_opsx_ff_8services_consistency.sh
	@bash quwoquan_service/scripts/runtime/verify_runtime_packaging.sh
	@bash quwoquan_service/scripts/deploy/verify_ff_config_contract.sh
	@bash quwoquan_service/scripts/deploy/verify_deployment_domain_mapping.sh
	@$(MAKE) verify-reliable-task-topology
	@bash quwoquan_service/scripts/deploy/report_deployment_mapping_impact.sh
	@bash quwoquan_service/scripts/recommendation/verify_recommendation_service_contract.sh
	@bash quwoquan_service/scripts/deploy/verify_topology_contract_regression.sh
	@$(MAKE) verify-workload-topology-inventory
	@bash quwoquan_service/scripts/deploy/verify_config_gray_parallel_binding.sh
	@$(MAKE) verify-quwoquan-data

codegen:
	@$(MAKE) -C quwoquan_service codegen

codegen-app:
	@$(MAKE) -C quwoquan_service codegen-app

codegen-ops-portal:
	@$(MAKE) -C quwoquan_service codegen-ops-portal

codegen-control-plane-runtime:
	@$(MAKE) -C quwoquan_service codegen-control-plane-runtime

codegen-chat-service:
	@$(MAKE) -C quwoquan_service codegen-chat-service

codegen-content-service:
	@$(MAKE) -C quwoquan_service codegen-content-service

# Bootstrap env-split config layout for a service.
# Usage:
#   make bootstrap-service-config SERVICE=content-service
bootstrap-service-config:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make bootstrap-service-config SERVICE=content-service"; \
		exit 2; \
	fi
	@bash quwoquan_service/scripts/runtime/bootstrap_service_config_layout.sh --service "$(SERVICE)"

# Create a new service scaffold and auto-bootstrap env-split config layout.
# Usage:
#   make new-service SERVICE=user-service PORT=18081
new-service:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make new-service SERVICE=user-service PORT=18081"; \
		exit 2; \
	fi
	@bash agent_ops/scaffold/new_service_fullstack.sh --name "$(SERVICE)" --port "$(if $(PORT),$(PORT),18080)"

# Progressive rollout state update for config release.
# Example:
# make config-gray-rollout SERVICE=content-service FROM_IMAGE=1.7.2 TO_IMAGE=1.8.0 FROM_CONFIG=v2026.02.27.1 TO_CONFIG=v2026.02.28.0 STEP=25
config-gray-rollout:
	@if [ -z "$(SERVICE)" ] || [ -z "$(FROM_IMAGE)" ] || [ -z "$(TO_IMAGE)" ] || [ -z "$(FROM_CONFIG)" ] || [ -z "$(TO_CONFIG)" ] || [ -z "$(STEP)" ]; then \
		echo "FAIL: SERVICE/FROM_IMAGE/TO_IMAGE/FROM_CONFIG/TO_CONFIG/STEP are required"; \
		exit 2; \
	fi
	@bash agent_ops/deploy/prod/config_release_gray_rollout.sh --service "$(SERVICE)" --from-image "$(FROM_IMAGE)" --to-image "$(TO_IMAGE)" --from-config "$(FROM_CONFIG)" --to-config "$(TO_CONFIG)" --step "$(STEP)"

# Idempotent rollback to a target config version.
# Example:
# make config-rollback SERVICE=content-service TO_CONFIG=v2026.02.27.1
config-rollback:
	@if [ -z "$(SERVICE)" ] || [ -z "$(TO_CONFIG)" ]; then \
		echo "FAIL: SERVICE and TO_CONFIG are required"; \
		exit 2; \
	fi
	@bash agent_ops/deploy/prod/config_release_rollback.sh --service "$(SERVICE)" --to-config-version "$(TO_CONFIG)"

# Evaluate SLO gate decision for a rollout stage.
# Example:
# make config-slo-gate ERROR_RATE=0.005 P95_MS=180 REDIS_ERROR_RATE=0.001
config-slo-gate:
	@if [ -z "$(ERROR_RATE)" ] || [ -z "$(P95_MS)" ] || [ -z "$(REDIS_ERROR_RATE)" ]; then \
		echo "FAIL: ERROR_RATE/P95_MS/REDIS_ERROR_RATE are required"; \
		exit 2; \
	fi
	@bash agent_ops/deploy/prod/config_release_slo_gate.sh --error-rate "$(ERROR_RATE)" --p95-ms "$(P95_MS)" --redis-error-rate "$(REDIS_ERROR_RATE)"

.PHONY: l2-content gate-full test-api-contract test-api-contract-chat
.PHONY: verify-test-specs verify-test-no-fake verify-test-coverage-map verify-test-directory-layout
.PHONY: generate-test-directory-inventory generate-app-canonical-test-wrappers generate-canonical-test-bridges
.PHONY: normalize-acceptance-recorded-paths
.PHONY: test-local-contract test-api-integration test-user-acceptance

# 本地 L2 契约测试（content-service，需 MongoDB 在 localhost:27017）
# 提交前运行以避免 CI 失败。详见 .cursor/rules/03-testing.mdc §2.1
l2-content:
	@bash quwoquan_app/scripts/content/run_l2_content_tests.sh

verify-test-specs:
	@python3 agent_ops/scaffold/verify_test_specs.py

verify-test-no-fake:
	@python3 agent_ops/scaffold/verify_test_no_fake.py

verify-test-coverage-map:
	@python3 agent_ops/scaffold/verify_test_coverage_map.py

verify-test-directory-layout:
	@python3 agent_ops/scaffold/verify_test_directory_inventory.py

verify-test-remote-env:
	@python3 agent_ops/scaffold/verify_test_remote_env.py --suite "$${MODE:?set MODE=api_integration|user_acceptance}" --env "$${ENV:-gamma}" --target "$${TARGET:-gamma-local}"

generate-test-directory-inventory:
	@python3 agent_ops/scaffold/generate_test_directory_inventory.py

generate-app-canonical-test-wrappers:
	@python3 agent_ops/scaffold/generate_canonical_test_bridges.py

generate-canonical-test-bridges:
	@python3 agent_ops/scaffold/generate_canonical_test_bridges.py

normalize-acceptance-recorded-paths:
	@python3 agent_ops/scaffold/normalize_acceptance_recorded_paths.py

test-local-contract:
	@$(MAKE) verify-test-specs
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-no-fake
	@$(MAKE) verify-test-coverage-map
	@bash quwoquan_service/scripts/contract/verify_contract_metadata.sh
	@python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/local_contract/
	@cd quwoquan_service && go test ./services/.../tests/local_contract -count=1
	@$(PYTEST_RUNNER) -m pytest quwoquan_data/tests/local_contract agent_ops/tests/local_contract -q

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
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/cloud/content/api_contract_runner.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL \
		--dart-define=LOCAL_GAMMA_T3_SCOPE=$${LOCAL_GAMMA_T3_SCOPE:-} \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN && \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/cloud/ops/api_contract_runner.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL=$$OPS_BASE_URL

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
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/cloud/chat/api_contract_runner.dart \
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
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/beta/ \
		--dart-define=APP_RUNTIME_ENV=beta \
		--dart-define=APP_DATA_SOURCE=remote \
		--dart-define=CLOUD_GATEWAY_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN && \
	ASSISTANT_SCENARIO_FIXTURE_B64="$$(python3 - <<'PY'\nimport base64\nfrom pathlib import Path\npath = Path('quwoquan_service/contracts/metadata/assistant/test_fixtures/scenarios/assistant_scenarios.json')\nprint(base64.b64encode(path.read_bytes()).decode('ascii'))\nPY\n)" && \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/gamma/assistant_alpha_beta_simulator__api_integration_test.dart \
		--dart-define=APP_RUNTIME_ENV=beta \
		--dart-define=APP_DATA_SOURCE=remote \
		--dart-define=CLOUD_GATEWAY_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN \
		--dart-define=ASSISTANT_SCENARIO_FIXTURE_JSON_B64=$$ASSISTANT_SCENARIO_FIXTURE_B64 && \
	ASSISTANT_EVAL_FIXTURE_B64="$$(python3 - <<'PY'\nimport base64\nfrom pathlib import Path\npath = Path('quwoquan_service/contracts/metadata/assistant/test_fixtures/scenarios/assistant_skill_eval_scenarios.json')\nprint(base64.b64encode(path.read_bytes()).decode('ascii'))\nPY\n)" && \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration/gamma/assistant_skill_comparison__api_integration_test.dart \
		--dart-define=APP_RUNTIME_ENV=beta \
		--dart-define=APP_DATA_SOURCE=remote \
		--dart-define=CLOUD_GATEWAY_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN \
		--dart-define=ASSISTANT_SCENARIO_FIXTURE_JSON_B64=$$ASSISTANT_EVAL_FIXTURE_B64

test-api-integration:
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-remote-env MODE=api_integration ENV="$${ENV:-gamma}"
	@$(MAKE) test-app-api-integration ENV="$${ENV:-gamma}"
	@cd quwoquan_service && go test ./services/.../tests/api_integration -count=1
	@$(PYTEST_RUNNER) -m pytest quwoquan_data/tests/api_integration agent_ops/acceptance/api_integration -q
	@$(MAKE) test-api-contract API_CONTRACT_ENV="$${ENV:-gamma}"
	@$(MAKE) test-api-contract-chat API_CONTRACT_ENV="$${ENV:-gamma}"

test-user-acceptance:
	@$(MAKE) verify-test-remote-env MODE=user_acceptance TARGET="$${TARGET:-gamma-local}"
	@TARGET_NAME="$${TARGET:-gamma-local}"; \
	case "$$TARGET_NAME" in \
		local) python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/user_acceptance/ && $(PYTEST_RUNNER) -m pytest quwoquan_data/tests/user_acceptance agent_ops/acceptance/user_acceptance -q ;; \
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
			python3 agent_ops/deploy/smoke/run_environment_patrol_smoke.py \
				--report "$${PROD_USER_ACCEPTANCE_REPORT:-artifacts/device-matrix/environment-smoke/prod_gray_initial_report.json}" \
				--env-name prod-gray-initial \
				--runtime-env prod \
				--api-contract-env prod \
				--data-source remote \
				--gateway-base-url "$${PROD_BASE_URL}" \
				--product-ops-base-url "$${PROD_PRODUCT_OPS_BASE_URL}" \
				--media-base-url "$${PROD_MEDIA_BASE_URL:-}" \
				--test-auth-token "$$TEST_TOKEN" \
				$$DRY_RUN_FLAG ;; \
		*) echo "[user_acceptance] FAIL: TARGET must be local, gamma-local or prod-hosted, got $$TARGET_NAME"; exit 2 ;; \
	esac

# gate-full: local_contract + api_integration + user_acceptance（daily CI / pre-release）
# PR 日常开发用 make gate；pre-release 用 make gate-full。
gate-full:
	@$(MAKE) gate
	@if [ -n "$${PROD_BASE_URL:-}" ] && [ -n "$${PROD_PRODUCT_OPS_BASE_URL:-}" ]; then \
		echo "[gate-full] PROD_* set; running prod gray-initial api_integration + user_acceptance"; \
		$(MAKE) test-api-integration ENV=prod; \
		$(MAKE) test-user-acceptance TARGET=prod-hosted; \
	else \
		echo "[gate-full] PROD_* not set; running gamma-local api_integration + user_acceptance"; \
		$(MAKE) test-api-integration ENV=gamma; \
		$(MAKE) test-user-acceptance TARGET=gamma-local; \
	fi

# Deploy to beta integration K8s. CLOUD_PROVIDER=aliyun|volcengine|huaweicloud (default: aliyun).
# Usage: make deploy-beta-k8s [CLOUD_PROVIDER=volcengine]
.PHONY: deploy-beta-k8s
deploy-beta-k8s:
	@bash agent_ops/deploy/beta/deploy_beta_k8s.sh
