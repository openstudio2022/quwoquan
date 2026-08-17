.PHONY: gate build test test-all-services test-unit test-contract test-contract-local test-integration test-runtime-api-integration test-chat-ready-index-alpha-beta lint service-contract-view verify-metadata verify-actor-persona-vocabulary verify-openapi verify-contract-graph verify-contract-graph-commercial verify-contract-graph-single-track verify-observability-catalog verify-assistant-service-errors verify-assistant-runtime-enums verify-shared-contract-enums verify-storage-keyset-single-track verify-circle-service-errors verify-content-service-codegen verify-entity-service-codegen verify-integration-service-codegen verify-external-provider-bindings verify-external-provider-governance verify-ddd-cqrs-baseline verify-codegen-contract-graph-source verify-go-single-module verify-service-layering verify-production-wiring-purity verify-api-edge-rate-limit-single-track verify-append-only-fact-command-admission verify-content-architecture verify-redis-routes codegen-redis-routes codegen codegen-openapi codegen-contract-graph codegen-observability-catalog codegen-app codegen-ops-portal codegen-control-plane-runtime codegen-assistant-service-errors codegen-assistant-runtime-enums codegen-assistant-reader-descriptors codegen-external-provider-bindings codegen-content-service codegen-circle-service codegen-entity-service codegen-notification-service codegen-rtc-service codegen-realtime-gateway codegen-integration-service codegen-product-ops-service codegen-platform-ops-service codegen-user-service codegen-chat-service codegen-chat-domain-events codegen-rec-model-python codegen-rec-policy codegen-storage dev dev-down dev-redis dev-redis-down dev-reliable-task-local dev-reliable-task-local-down clean verify-ml-features verify-ml-model-quality verify-ml-e2e verify-ml-e2e-live verify-ml-guardrail verify-ml-drift verify-ml-tests verify-rec-policy-advisor verify-content-flywheel-tests verify-content-flywheel-loop verify-operation-privacy-redaction codegen-operation-privacy
.PHONY: verify-assistant-citation-destinations codegen-assistant-citation-destinations
.PHONY: verify-storage-index-governance
.PHONY: verify-graphql-read-rest-command-single-track verify-graphql-read-rest-command-structural-zero verify-graphql-read-rest-command-migration-ratchet verify-graphql-read-rest-command-zero
.PHONY: verify-graphql-read-registry codegen-graphql-read-registry verify-graphql-app-client codegen-graphql-app-client
.PHONY: verify-link-templates-go codegen-link-templates-go
.PHONY: verify-api-edge-errors codegen-api-edge-errors
.PHONY: verify-assistant-tool-catalog codegen-assistant-tool-catalog
.PHONY: codegen-event-constants
.PHONY: verify-app-shell-navigation codegen-app-shell-navigation
.PHONY: verify-domain-model-compatibility

SCENARIO ?= content_feed
DB ?= quwoquan_content
MONGODB_URI ?= mongodb://127.0.0.1:27017/?directConnection=true
ML_DRY_RUN ?= false
ML_CANDIDATE_EVIDENCE ?=
ML_ACTIVE_EVIDENCE ?=
ML_GUARDRAIL_ENV ?= gamma
ML_GUARDRAIL_WINDOW_HOURS ?= 4
ML_GUARDRAIL_DRY_RUN ?= true
ML_GUARDRAIL_OUT ?=
ML_DRIFT_BASELINE_DATE ?=
ML_DRIFT_OUT ?=
FLYWHEEL_REQUIRE_CLOSED ?= false
FLYWHEEL_OUT ?=
GRAPHQL_READ_REGISTRY_EXAMPLE_CANDIDATE_DIGEST ?= sha256:1111111111111111111111111111111111111111111111111111111111111111
GRAPHQL_MIGRATION_BASE_SHA ?= $(shell git -C "$(REPO_ROOT)" merge-base HEAD origin/main 2>/dev/null || git -C "$(REPO_ROOT)" rev-parse HEAD)
GRAPHQL_MIGRATION_CANDIDATE_SHA ?=
DOMAIN_MODEL_BASELINE_RECEIPT ?=
DOMAIN_MODEL_BASELINE_GRAPH ?=
DOMAIN_MODEL_CURRENT_GRAPH ?= generated/contract_graph.json
DOMAIN_MODEL_COMPATIBILITY_WINDOW ?=
DOMAIN_MODEL_STORAGE_MIGRATION_PLAN ?=
DOMAIN_MODEL_COMPATIBILITY_REPORT ?= $(QWQ_OUTPUT_ROOT)/env/repo/runs/domain-model-compatibility/report.json
REPO_ROOT ?= $(abspath ..)
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
# 每个 Make 进程独占可删除编译视图，避免并发 codegen 在 ContractGraph 编译和对象
# 生成之间删除另一进程的输入。
CONTRACT_VIEW ?= $(QWQ_OUTPUT_ROOT)/env/repo/local/service-contract-view/cache/view-$(shell printf %s "$$PPID")
# ContractGraph 产物在两个 profile 下逐字节相同，profile 只决定必须通过哪一档校验。
# 默认 commercial 保持准出门禁不被削弱；存量 commercial 债务未清期间，可显式
# CONTRACT_GRAPH_PROFILE=baseline 重新生成 bundle，让下游 codegen 不被存量债务连坐。
CONTRACT_GRAPH_PROFILE ?= commercial
ML_REPORT_ROOT ?= $(QWQ_OUTPUT_ROOT)/env/repo/runs/ml
QWQ_PYTHON_CACHE_ROOT ?= $(HOME)/.cache/quwoquan/python-envs
DATA_PYTHON ?= $(QWQ_PYTHON_CACHE_ROOT)/quwoquan-data/bin/python
ML_PYTHON ?= $(QWQ_PYTHON_CACHE_ROOT)/rec-model/bin/python
ML_SCRIPTS := services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts
PYTEST_FLAGS := -o cache_dir=$(QWQ_OUTPUT_ROOT)/env/repo/local/tests/cache/pytest
DOMAIN_SERVICES := $(sort $(notdir $(patsubst %/contracts/,%,$(dir $(wildcard services/*/contracts/domain.yaml)))))
export QWQ_OUTPUT_ROOT
export PYTHONDONTWRITEBYTECODE ?= 1

# ─── Quality Gate ────────────────────────────────────────────────────
gate: verify-metadata verify-redis-routes verify-go-single-module verify-service-layering verify-production-wiring-purity verify-api-edge-rate-limit-single-track verify-append-only-fact-command-admission verify-nullability-single-semantics
	@PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/gate/verify_service_architecture.py
	@set -e; for service in $(DOMAIN_SERVICES); do \
		echo "[gate] $$service"; \
		$(MAKE) -C "services/$$service" gate; \
	done

# ─── Build ───────────────────────────────────────────────────────────
build:
	go list ./... | awk '$$0 !~ /\/tests(\/|$$)/' | xargs go build

# ─── Test ────────────────────────────────────────────────────────────
test: test-all-services

test-all-services:
	@set -e; for service in $(DOMAIN_SERVICES); do \
		echo "[test] $$service"; \
		$(MAKE) -C "services/$$service" test; \
	done

test-unit:
	$(MAKE) -C services/assistant-service test
	go test ./runtime/... ./services/content-service/... ./services/chat-service/... ./services/user-service/... ./services/rtc-service/... -v -count=1

test-contract:
	$(MAKE) -C services/assistant-service test
	go test ./services/content-service/... ./services/chat-service/... ./services/user-service/... ./services/rtc-service/... -v -count=1

# Run L2 contract tests against a locally running MongoDB (no Docker required).
# Usage:
#   make test-contract-local                          # expects MongoDB at localhost:27017
#   make test-contract-local MONGO_PORT=27018         # custom port
#
# Quick start without Docker:
#   brew services start mongodb-community             # macOS via Homebrew
#   make test-contract-local
MONGO_PORT ?= 27017
test-contract-local:
	TEST_MONGO_URI=mongodb://localhost:$(MONGO_PORT) \
	  go test ./services/content-service/... -v -count=1 -timeout=60s

test-integration: test-runtime-api-integration

test-runtime-api-integration:
	go test ./runtime/... -v -count=1 -tags=api_integration

test-chat-ready-index-alpha-beta:
	TEST_REDIS_ADDR=$${TEST_REDIS_ADDR:-localhost:6379} \
	TEST_MONGO_URI=$${TEST_MONGO_URI:-mongodb://localhost:27017/?replicaSet=rs0} \
	  go test ./runtime/reliabletask ./services/chat-service/tests -run 'TestRedisReadyIndexStandaloneStreamsClaimAck|TestGroupAvatar_RedisReadyIndexAlphaBetaLocalLoop' -v -count=1

# ─── Lint ────────────────────────────────────────────────────────────
lint:
	go vet ./runtime/...
	go vet ./tools/...

# ─── Metadata ────────────────────────────────────────────────────────
service-contract-view:
	@python3 scripts/contracts/build_service_contract_view.py --output "$(CONTRACT_VIEW)"

verify-ddd-cqrs-baseline:
	go test ./internal/metadata/load ./internal/metadata/graph ./internal/metadata/validate
	go test ./services/content-service/internal/trust_safety/report/domain/... ./services/content-service/internal/trust_safety/report/application

verify-metadata: service-contract-view verify-actor-persona-vocabulary verify-codegen-contract-graph-source verify-contract-graph-single-track verify-observability-catalog verify-api-edge-errors verify-assistant-service-errors verify-assistant-runtime-enums verify-assistant-tool-catalog verify-assistant-citation-destinations verify-link-templates-go verify-shared-contract-enums verify-storage-keyset-single-track verify-storage-index-governance verify-circle-service-errors verify-content-service-codegen verify-entity-service-codegen verify-integration-service-codegen verify-external-provider-bindings verify-external-provider-governance verify-graphql-read-registry verify-graphql-read-rest-command-structural-zero verify-graphql-read-rest-command-migration-ratchet
	@$(MAKE) verify-contract-graph-commercial
	go run ./tools/verify_metadata/ "$(CONTRACT_VIEW)"

verify-actor-persona-vocabulary:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify/consistency/verify_actor_persona_vocabulary.py

verify-observability-catalog: service-contract-view
	go run ./tools/codegen_observability_catalog --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)" --check

OPERATION_PRIVACY_DART_OUTPUT = ../quwoquan_app/lib/runtime/observability/generated/operation_privacy_catalog.g.dart

verify-operation-privacy-redaction: service-contract-view
	go run ./tools/codegen_operation_privacy --metadata-dir "$(CONTRACT_VIEW)" --dart-output "$(OPERATION_PRIVACY_DART_OUTPUT)" --check
	go test ./runtime/observability -run TestOperationPrivacy

codegen-operation-privacy: service-contract-view
	go run ./tools/codegen_operation_privacy --metadata-dir "$(CONTRACT_VIEW)" --dart-output "$(OPERATION_PRIVACY_DART_OUTPUT)"

verify-api-edge-errors: service-contract-view
	go run ./tools/codegen_service_errors --metadata-dir "$(CONTRACT_VIEW)" --domain gateway --output-root services/api-edge/generated --check

verify-assistant-service-errors: service-contract-view
	go run ./tools/codegen_service_errors --metadata-dir "$(CONTRACT_VIEW)" --domain assistant --output-root services/assistant-service/generated --check

verify-assistant-runtime-enums: service-contract-view
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --assistant-runtime-enums-go-output services/assistant-service/generated/assistant/assistant_session/assistant_runtime_enums.g.go --check-assistant-runtime-enums-go

verify-assistant-tool-catalog: service-contract-view
	go run ./tools/codegen_assistant_tool_catalog --metadata-dir "$(CONTRACT_VIEW)" --output services/assistant-service/generated/assistant/assistant_session/assistant_tool_catalog.g.go --search-access-output services/assistant-service/generated/assistant/assistant_session/assistant_search_access.g.go --check

verify-assistant-citation-destinations: service-contract-view
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --citation-destinations-go-output services/assistant-service/generated/assistant/assistant_session/citation_destinations.g.go --check-citation-destinations-go

verify-link-templates-go: service-contract-view
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/contracts/generate_link_templates_go.py --metadata-dir "$(CONTRACT_VIEW)" --output generated/linktemplates/link_templates.g.go --check

verify-shared-contract-enums: service-contract-view
	go test ./services/circle-service/tests/local_contract/circle_management/circle_membership -run 'TestPersonaCircleSlice|TestCircleSourceContract' -count=1
	go test ./services/user-service/tests/local_contract/relationship/subject_follow -run 'TestSubjectFollow' -count=1
	go test ./services/chat-service/tests/local_contract/chat/conversation -run 'TestConversationContactWireEnumsAreTyped|TestChatContactSourceMatchesNormalizerDomain|TestSelectableGroupConversationSourceMatchesQueryGuard|TestContactRelationStateStaysWithinSharedDomain' -count=1
	go test ./tools/codegen_app_metadata -run 'TestCrossDomain|TestCanonicalRequestEnumMembers|TestAcceptedAppRequestTypedEnums' -count=1

verify-storage-keyset-single-track:
	go test ./tools/codegen_storage -run 'TestStorageSchemaKeepsTopLevelKeySetClosed|TestCodegenStorageReaderKeySetIsSubsetOfSchema|TestStorageSchemaKeysArePartitionedByCodegenConsumption|TestCodegenStorageReaderHasNoDeadKeys' -count=1

# 契约可空性只有一种读法：必填缺失 fail-closed，可空的缺席与空值不得互相塌陷，
# 生成器不得补入契约未声明的默认值。没有这条过滤目标时，这些测试只是躺在树里。
verify-nullability-single-semantics:
	go test ./tools/codegen_app_metadata -run 'TestAssistantWireRequiredScalarsFailClosedOnAbsence|TestAssistantWireNullableScalarsKeepAbsenceDistinctFromEmpty|TestRtcPayloadWithoutDefaultKeepsAbsence|TestRtcPayloadWithDefaultUsesDeclaredValue' -count=1

verify-storage-index-governance:
	go run ./tools/storage_index_governance -repo-root "$(REPO_ROOT)"

verify-circle-service-errors: service-contract-view
	go run ./tools/codegen_circle_domain --metadata-dir "$(CONTRACT_VIEW)" --contract-graph generated/contract_graph.json --output-dir services/circle-service/generated/circle_management --shared-dir generated/serviceclients --check

verify-content-service-codegen: service-contract-view
	go run ./tools/codegen_content_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/content-service/generated --aggregate Post --route-service content-service --check

verify-entity-service-codegen: service-contract-view
	go run ./tools/codegen_entity_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/entity-service/generated --check

verify-integration-service-codegen: service-contract-view
	go run ./tools/codegen_integration_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/integration-service/generated --check

verify-external-provider-bindings:
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --quiet --go-bindings --check

verify-external-provider-governance:
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/gate/verify_external_provider_governance.py

verify-openapi: service-contract-view
	go run ./tools/qwq_contract check-openapi --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)"

verify-graphql-read-rest-command-single-track:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify/structure/verify_graphql_read_rest_command_single_track.py --service-root "$(CURDIR)"

# Source-only gate: structural violations are strict-zero.  Existing App/public
# REST reads are migration obligations and are governed by the immutable-SHA
# identity ratchet below, not converted into structural exceptions.
verify-graphql-read-rest-command-structural-zero:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify/structure/verify_graphql_read_rest_command_single_track.py --service-root "$(CURDIR)" --require-structural-zero --summary-only

verify-graphql-read-rest-command-migration-ratchet:
	@test -n "$(GRAPHQL_MIGRATION_BASE_SHA)" || { echo "GRAPHQL_MIGRATION_BASE_SHA is required" >&2; exit 2; }
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify/structure/verify_graphql_read_rest_command_single_track.py \
		--service-root "$(CURDIR)" \
		--migration-base-sha "$(GRAPHQL_MIGRATION_BASE_SHA)" \
		$(if $(strip $(GRAPHQL_MIGRATION_CANDIDATE_SHA)),--migration-candidate-sha "$(GRAPHQL_MIGRATION_CANDIDATE_SHA)",) \
		--require-no-migration-growth \
		--summary-only

# Release-cutover predicate only.  It intentionally stays outside
# verify-metadata: a release caller must compose it with hosted GraphQL
# readiness and the canonical minimum-build/zero-call compatibility window.
# Source-only CI cannot fabricate those lifecycle inputs.
verify-graphql-read-rest-command-zero:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify/structure/verify_graphql_read_rest_command_single_track.py --service-root "$(CURDIR)" --require-zero

verify-graphql-read-registry: service-contract-view
	go run ./tools/codegen_graphql_read_registry \
		-schema services/api-edge/resources/policies/graphql_read/schema.graphqls \
		-metadata services/api-edge/resources/policies/graphql_read/query_metadata.json \
		-metadata-dir "$(CONTRACT_VIEW)" \
		-candidate-digest "$(GRAPHQL_READ_REGISTRY_EXAMPLE_CANDIDATE_DIGEST)" \
		-output services/api-edge/resources/policies/graphql_read/persisted_query_registry.example.json \
		-check

verify-graphql-app-client: service-contract-view
	go run ./tools/codegen_graphql_app_client \
		-metadata-dir "$(CONTRACT_VIEW)" \
		-target content-post-detail \
		-check
	go run ./tools/codegen_graphql_app_client \
		-metadata-dir "$(CONTRACT_VIEW)" \
		-target search-page \
		-check

codegen-graphql-app-client: service-contract-view
	go run ./tools/codegen_graphql_app_client \
		-metadata-dir "$(CONTRACT_VIEW)" \
		-target content-post-detail
	go run ./tools/codegen_graphql_app_client \
		-metadata-dir "$(CONTRACT_VIEW)" \
		-target search-page

verify-contract-graph: verify-openapi
	go run ./tools/qwq_contract validate --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)" --profile baseline
	go run ./tools/qwq_contract check --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)" --profile baseline --input generated/contract_graph.json
	go run ./tools/qwq_contract coverage --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)"

verify-contract-graph-commercial: verify-openapi
	go run ./tools/qwq_contract validate --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)" --profile commercial
	go run ./tools/qwq_contract check --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)" --profile commercial --input generated/contract_graph.json
	go run ./tools/qwq_contract coverage --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)"

# Release-only gate: the caller must first read back the last successful hosted
# Prod full/100 receipt and its exact ContractGraph bytes.  This target is not
# part of the source-only `gate`, because a local checkout cannot fabricate the
# hosted baseline, minimum-build usage window, or storage migration evidence.
verify-domain-model-compatibility:
	@test -n "$(DOMAIN_MODEL_BASELINE_RECEIPT)" || { echo "DOMAIN_MODEL_BASELINE_RECEIPT is required" >&2; exit 2; }
	@test -n "$(DOMAIN_MODEL_BASELINE_GRAPH)" || { echo "DOMAIN_MODEL_BASELINE_GRAPH is required" >&2; exit 2; }
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify/contract_graph/verify_domain_model_compatibility.py \
		--baseline-receipt "$(DOMAIN_MODEL_BASELINE_RECEIPT)" \
		--baseline-graph "$(DOMAIN_MODEL_BASELINE_GRAPH)" \
		--current-graph "$(DOMAIN_MODEL_CURRENT_GRAPH)" \
		$(if $(strip $(DOMAIN_MODEL_COMPATIBILITY_WINDOW)),--compatibility-window "$(DOMAIN_MODEL_COMPATIBILITY_WINDOW)",) \
		$(if $(strip $(DOMAIN_MODEL_STORAGE_MIGRATION_PLAN)),--storage-migration-plan "$(DOMAIN_MODEL_STORAGE_MIGRATION_PLAN)",) \
		--report "$(DOMAIN_MODEL_COMPATIBILITY_REPORT)"

verify-contract-graph-single-track: service-contract-view
	python3 scripts/verify/contract_graph/verify_contract_graph_single_track.py --metadata-dir "$(CONTRACT_VIEW)"
	# Service gate: block legacy route inputs, client-owned binding overrides,
	# empty-green scans and path/binding drift. Fix the owning operations.yaml
	# request_bindings; request type/encoder generation remains a separate gate.
	go test ./internal/metadata/graph -run TestRepositoryRequestBindingsUseCanonicalSingleTrack -count=1

verify-codegen-contract-graph-source:
	python3 scripts/verify/contract_graph/verify_codegen_contract_graph_source.py

verify-app-shell-navigation: service-contract-view
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --app-dir ../quwoquan_app --shell-navigation-metadata-only --check-shell-navigation-metadata --shell-navigation-manifest ../quwoquan_app/tool/shell_navigation_codegen/generated_manifest.json

verify-go-single-module:
	python3 scripts/verify/structure/verify_go_single_module.py

verify-service-layering:
	python3 scripts/verify/structure/verify_service_layering.py

verify-production-wiring-purity:
	python3 scripts/verify/structure/verify_production_wiring_purity.py

verify-api-edge-rate-limit-single-track:
	python3 scripts/verify/structure/verify_api_edge_rate_limit_single_track.py

verify-append-only-fact-command-admission:
	python3 scripts/verify/structure/verify_append_only_fact_command_admission.py

verify-redis-routes:
	python3 scripts/codegen/gen_redis_router_config.py --check

codegen-redis-routes:
	python3 scripts/codegen/gen_redis_router_config.py

codegen: codegen-redis-routes codegen-contract-graph codegen-observability-catalog codegen-api-edge-errors codegen-assistant-service-errors codegen-assistant-runtime-enums codegen-assistant-reader-descriptors codegen-assistant-tool-catalog codegen-assistant-citation-destinations codegen-link-templates-go codegen-external-provider-bindings codegen-content-service codegen-circle-service codegen-entity-service codegen-notification-service codegen-rtc-service codegen-realtime-gateway codegen-integration-service codegen-product-ops-service codegen-platform-ops-service codegen-user-service codegen-chat-service codegen-chat-domain-events codegen-storage codegen-event-constants codegen-rec-model-python codegen-rec-policy codegen-rec-intersection codegen-impact codegen-control-plane-runtime codegen-ops-portal

codegen-openapi: service-contract-view
	go run ./tools/qwq_contract generate-openapi --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)"
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/contracts/sync_service_openapi.py --contract-view "$(CONTRACT_VIEW)"

codegen-contract-graph: codegen-graphql-read-registry codegen-openapi
	go run ./tools/qwq_contract generate --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)" --profile $(CONTRACT_GRAPH_PROFILE) --output generated/contract_graph.json --go-security-output generated/operationsecurity/descriptors.g.go

codegen-graphql-read-registry: service-contract-view
	go run ./tools/codegen_graphql_read_registry \
		-schema services/api-edge/resources/policies/graphql_read/schema.graphqls \
		-metadata services/api-edge/resources/policies/graphql_read/query_metadata.json \
		-metadata-dir "$(CONTRACT_VIEW)" \
		-candidate-digest "$(GRAPHQL_READ_REGISTRY_EXAMPLE_CANDIDATE_DIGEST)" \
		-output services/api-edge/resources/policies/graphql_read/persisted_query_registry.example.json

codegen-observability-catalog codegen-rec-intersection codegen-impact \
codegen-ops-portal codegen-control-plane-runtime \
codegen-api-edge-errors codegen-assistant-service-errors codegen-assistant-runtime-enums \
codegen-assistant-tool-catalog codegen-assistant-citation-destinations codegen-content-service \
codegen-circle-service codegen-entity-service codegen-notification-service \
codegen-rtc-service codegen-realtime-gateway codegen-integration-service \
codegen-product-ops-service codegen-platform-ops-service codegen-user-service \
codegen-chat-service codegen-chat-domain-events codegen-event-constants codegen-rec-model-python \
codegen-storage: service-contract-view

codegen-app: codegen-contract-graph

codegen-observability-catalog:
	go run ./tools/codegen_observability_catalog --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)"

codegen-api-edge-errors:
	go run ./tools/codegen_service_errors --metadata-dir "$(CONTRACT_VIEW)" --domain gateway --output-root services/api-edge/generated

codegen-rec-intersection:
	go run ./tools/codegen_rec_intersection --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/content-service/generated/content/post

codegen-impact:
	go run ./tools/codegen_impact --metadata-dir "$(CONTRACT_VIEW)" --output-dir runtime/impact

codegen-app:
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --contract-graph generated/contract_graph.json --contract-graph-lock ../quwoquan_app/tool/cloud_codegen/contract_graph.lock.json --app-dir ../quwoquan_app --generated-manifest ../quwoquan_app/tool/cloud_codegen/generated_manifest.json

codegen-app-shell-navigation: service-contract-view
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --app-dir ../quwoquan_app --shell-navigation-metadata-only --shell-navigation-manifest ../quwoquan_app/tool/shell_navigation_codegen/generated_manifest.json

codegen-link-templates-go: service-contract-view
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/contracts/generate_link_templates_go.py --metadata-dir "$(CONTRACT_VIEW)" --output generated/linktemplates/link_templates.g.go

codegen-ops-portal:
	go run ./tools/codegen_ops_portal_metadata --metadata-dir "$(CONTRACT_VIEW)" --portal-dir ../quwoquan_ops/portal

codegen-control-plane-runtime:
	go run ./tools/codegen_control_plane_runtime --metadata-dir "$(CONTRACT_VIEW)" --go-out-dir ./generated/control_plane --python-out-dir ./services/recommendation-service/generated/recommendation/recommendation_model_release/control_plane

codegen-assistant-service-errors:
	go run ./tools/codegen_service_errors --metadata-dir "$(CONTRACT_VIEW)" --domain assistant --output-root services/assistant-service/generated

codegen-assistant-runtime-enums:
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --assistant-runtime-enums-go-output services/assistant-service/generated/assistant/assistant_session/assistant_runtime_enums.g.go

codegen-assistant-reader-descriptors: service-contract-view
	go run ./tools/codegen_assistant_reader_descriptors --metadata-dir "$(CONTRACT_VIEW)" --output services/assistant-service/generated/assistant/domain_reader_descriptor/reader_descriptors.g.go

codegen-assistant-tool-catalog:
	go run ./tools/codegen_assistant_tool_catalog --metadata-dir "$(CONTRACT_VIEW)" --output services/assistant-service/generated/assistant/assistant_session/assistant_tool_catalog.g.go --search-access-output services/assistant-service/generated/assistant/assistant_session/assistant_search_access.g.go

codegen-assistant-citation-destinations:
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --citation-destinations-go-output services/assistant-service/generated/assistant/assistant_session/citation_destinations.g.go

codegen-external-provider-bindings:
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --quiet --go-bindings

codegen-content-service:
	go run ./tools/codegen_content_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/content-service/generated --aggregate Post --route-service content-service

codegen-circle-service:
	go run ./tools/codegen_circle_domain --metadata-dir "$(CONTRACT_VIEW)" --contract-graph generated/contract_graph.json --output-dir services/circle-service/generated/circle_management --shared-dir generated/serviceclients

codegen-entity-service:
	go run ./tools/codegen_entity_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/entity-service/generated

codegen-notification-service:
	go run ./tools/codegen_notification_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/notification-service/generated/notification_delivery/notification

codegen-rtc-service:
	go run ./tools/codegen_rtc_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/rtc-service/generated/rtc/call_session

codegen-realtime-gateway:
	go run ./tools/codegen_realtime_gateway --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/realtime-gateway/generated/realtime/connection

codegen-integration-service:
	go run ./tools/codegen_integration_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/integration-service/generated

codegen-product-ops-service:
	go run ./tools/codegen_product_ops_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/product-ops-service/generated

codegen-platform-ops-service:
	go run ./tools/codegen_platform_ops_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir control-plane/platform-ops/generated/platform_ops/config_snapshot
	go run ./tools/codegen_platform_ops_service --metadata-dir "$(CONTRACT_VIEW)" --source-path ops/platform_ops/config_instance_report/errors.yaml --output-dir control-plane/platform-ops/generated/platform_ops/config_instance_report

codegen-user-service:
	go run ./tools/codegen_user_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/user-service/generated

codegen-chat-service:
	go run ./tools/codegen_chat_service --metadata-dir "$(CONTRACT_VIEW)" --contracts-dir services/chat-service/contracts --output-dir services/chat-service/generated

codegen-chat-domain-events:
	go run ./tools/codegen_chat_domain_events --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/chat-service/generated/chat

codegen-event-constants: codegen-content-service codegen-circle-service codegen-chat-domain-events codegen-storage
	go run ./tools/codegen_event_constants --metadata-dir "$(CONTRACT_VIEW)" --service-root . --python-output generated/event_constants.py --manifest-output generated/event_constants_manifest.json

codegen-rec-model-python:
	go run ./tools/codegen_rec_model_python --metadata-dir "$(CONTRACT_VIEW)" --service-dir recommendation/recommendation/recommendation_model_release --output-dir services/recommendation-service/generated/recommendation/recommendation_model_release --content-feature-profile-go-output services/content-service/generated/content/post/recommendation_feature_profile.g.go

codegen-rec-policy:
	go run ./tools/codegen_rec_policy --source services/content-service/resources/policies/content/post/recommendation_policy.yaml --out-dir runtime/recpolicy

codegen-storage:
	@echo "=== codegen-storage: content-service ==="
	go run ./tools/codegen_storage --metadata-dir "$(CONTRACT_VIEW)" --service-dir services/content-service
	@echo "=== codegen-storage: user-service ==="
	go run ./tools/codegen_storage --metadata-dir "$(CONTRACT_VIEW)" --service-dir services/user-service
	@echo "=== codegen-storage: tag-service ==="
	go run ./tools/codegen_storage --metadata-dir "$(CONTRACT_VIEW)" --service-dir services/tag-service

# ─── Dev Environment ─────────────────────────────────────────────────
dev:
	docker compose -f ../quwoquan_ops/environments/compose/docker-compose.yaml up -d
	@echo "Waiting for services..."
	@sleep 5
	@docker compose -f ../quwoquan_ops/environments/compose/docker-compose.yaml ps

dev-down:
	docker compose -f ../quwoquan_ops/environments/compose/docker-compose.yaml down -v

dev-redis:
	docker compose -f ../quwoquan_ops/environments/compose/docker-compose.local-redis.yml up -d
	@docker compose -f ../quwoquan_ops/environments/compose/docker-compose.local-redis.yml ps

dev-redis-down:
	docker compose -f ../quwoquan_ops/environments/compose/docker-compose.local-redis.yml down

dev-reliable-task-local: dev-redis

dev-reliable-task-local-down: dev-redis-down

# ─── Clean ───────────────────────────────────────────────────────────
clean:
	go clean -testcache
	rm -rf tmp/

# ─── ML Verification ────────────────────────────────────────────────
verify-ml-features:
	$(ML_PYTHON) $(ML_SCRIPTS)/verify_feature_consistency.py

verify-ml-tests:
	$(ML_PYTHON) -m pytest $(PYTEST_FLAGS) services/recommendation-service/tests/local_contract/recommendation/recommendation_model_release -q

verify-rec-policy-advisor:
	$(ML_PYTHON) -m pytest $(PYTEST_FLAGS) ../quwoquan_ops/tests/local_contract/observability/test_rec_policy_advisor__product_ops_tool__local_contract_test.py -q

verify-content-flywheel-tests:
	$(ML_PYTHON) -m pytest $(PYTEST_FLAGS) ../quwoquan_ops/tests/local_contract/observability/test_eval_content_flywheel_loop__product_ops_tool__local_contract_test.py -q

verify-content-flywheel-loop:
	$(ML_PYTHON) scripts/product-ops-service/tools/eval_content_flywheel_loop.py --mongodb-uri "$(MONGODB_URI)" $(if $(filter 1 true yes,$(FLYWHEEL_REQUIRE_CLOSED)),--require-closed-loop,) $(if $(strip $(FLYWHEEL_OUT)),--output "$(FLYWHEEL_OUT)",)

verify-ml-model-quality:
	@test -n "$(strip $(ML_CANDIDATE_EVIDENCE))" || (echo "ML_CANDIDATE_EVIDENCE is required" >&2; exit 1)
	@mkdir -p "$(ML_REPORT_ROOT)"
	$(ML_PYTHON) $(ML_SCRIPTS)/evaluate_gate.py --candidate-evidence "$(ML_CANDIDATE_EVIDENCE)" $(if $(strip $(ML_ACTIVE_EVIDENCE)),--active-evidence "$(ML_ACTIVE_EVIDENCE)",) $(if $(filter 1 true yes,$(ML_DRY_RUN)),--dry-run,) --out "$(ML_REPORT_ROOT)/model_release_verification.json"

verify-ml-e2e:
	$(ML_PYTHON) $(ML_SCRIPTS)/e2e_learning_loop_verify.py --scenario "$(SCENARIO)" --full-pipeline $(if $(strip $(REC_MODEL_URL)),--rec-model $(REC_MODEL_URL),--skip-service)

verify-ml-e2e-live:
	@test -n "$(strip $(REC_MODEL_URL))" || (echo "REC_MODEL_URL is required for verify-ml-e2e-live" >&2; exit 1)
	$(ML_PYTHON) $(ML_SCRIPTS)/e2e_learning_loop_verify.py --scenario "$(SCENARIO)" --mongodb-uri "$(MONGODB_URI)" --db "$(DB)" --rec-model "$(REC_MODEL_URL)"

verify-ml-guardrail:
	$(ML_PYTHON) $(ML_SCRIPTS)/online_guardrail.py --scenario "$(SCENARIO)" --window-hours "$(ML_GUARDRAIL_WINDOW_HOURS)" --env "$(ML_GUARDRAIL_ENV)" $(if $(filter 1 true yes,$(ML_GUARDRAIL_DRY_RUN)),--dry-run,) $(if $(strip $(ML_GUARDRAIL_OUT)),--out "$(ML_GUARDRAIL_OUT)",)

verify-ml-drift:
	$(ML_PYTHON) $(ML_SCRIPTS)/feature_drift_monitor.py --scenario "$(SCENARIO)" --baseline-date "$(ML_DRIFT_BASELINE_DATE)" $(if $(strip $(ML_DRIFT_OUT)),--out "$(ML_DRIFT_OUT)",)
