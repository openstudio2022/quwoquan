package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestControlPlaneMetadataRejectsInvalidApprovalMode(t *testing.T) {
	metadataDir := createControlPlaneMetadataFixture(t, controlPlaneFixtureOptions{
		platformApprovalMode: "review",
		productConfigScope:   "environment",
		productConfigRollout: "experiment",
	})

	v := &validator{metadataDir: metadataDir}
	v.run()

	if !containsError(v.errors, "approval_mode") {
		t.Fatalf("expected approval_mode validation error, got: %v", v.errors)
	}
}

func TestControlPlaneMetadataRejectsDuplicateRoutePath(t *testing.T) {
	metadataDir := createControlPlaneMetadataFixture(t, controlPlaneFixtureOptions{
		platformApprovalMode: "dual",
		productConfigScope:   "environment",
		productConfigRollout: "experiment",
		duplicateRoutePath:   true,
	})

	v := &validator{metadataDir: metadataDir}
	v.run()

	if !containsError(v.errors, "route_path") {
		t.Fatalf("expected route_path validation error, got: %v", v.errors)
	}
}

func TestControlPlaneMetadataRejectsInvalidConfigScopeAndRollout(t *testing.T) {
	metadataDir := createControlPlaneMetadataFixture(t, controlPlaneFixtureOptions{
		platformApprovalMode: "dual",
		productConfigScope:   "env",
		productConfigRollout: "gray",
	})

	v := &validator{metadataDir: metadataDir}
	v.run()

	if !containsError(v.errors, "scope") || !containsError(v.errors, "rollout") {
		t.Fatalf("expected config scope and rollout validation errors, got: %v", v.errors)
	}
}

func TestSharedControlPlaneBaselineRejectsMissingRequiredFields(t *testing.T) {
	root := t.TempDir()
	mustWriteFixtureFile(t, filepath.Join(root, "_shared", "types.yaml"), "enums: {}\n")
	mustWriteFixtureFile(t, filepath.Join(root, "_shared", "control_plane.yaml"), strings.TrimSpace(`
version: 1
planes: []
danger_levels: []
approval_modes: []
object_kinds: []
dashboard_schema:
  required_fields: []
  widget_examples: []
object_type_schema:
  required_fields: []
  optional_fields: []
operation_schema:
  required_fields: []
  optional_fields: []
http_methods: []
scope_patterns: []
deployment_profiles: []
`)+"\n")

	v := &validator{metadataDir: root}
	v.run()

	if !containsError(v.errors, "planes cannot be empty") || !containsError(v.errors, "http_methods cannot be empty") {
		t.Fatalf("expected shared control plane validation errors, got: %v", v.errors)
	}
}

func TestDomainOnboardingRejectsUnknownStatus(t *testing.T) {
	root := createDomainOnboardingFixture(t)
	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "domains", "content.yaml"), strings.TrimSpace(`
version: 1
domain: content
display_name: Content
template_role: template_seed
rollout_group: wave_0_template
acceptance_status: ready_now
metadata_paths: [content/post]
service_names: [content-service]
control_planes:
  platform:
    enabled: true
    object_types: [service_catalog_entry]
    config_prefixes: [sys.content.]
  product:
    enabled: true
    object_types: [moderation_case]
    config_prefixes: [ops.content.]
minimum_package:
  metadata_files:
    - contracts/metadata/content/post/service.yaml
  codegen_targets: [go_runtime, python_runtime, ops_portal]
  test_evidence:
    t1: [contracts/metadata/content/post/service.yaml]
    t2: [services/content-service/tests/post_comment_contract_test.go]
    t3: []
    t4: []
deployment:
  plane_binding_domain: content
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml
  current_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: [chat]
  copy_notes: [seed]
blocking_gaps: []
`)+"\n")

	v := &validator{metadataDir: root}
	v.run()

	if !containsError(v.errors, "acceptance_status") {
		t.Fatalf("expected domain onboarding status validation error, got: %v", v.errors)
	}
}

func TestDomainOnboardingRejectsMinimumTestReadyWithoutT2(t *testing.T) {
	root := createDomainOnboardingFixture(t)
	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "domains", "content.yaml"), strings.TrimSpace(`
version: 1
domain: content
display_name: Content
template_role: template_seed
rollout_group: wave_0_template
acceptance_status: minimum_test_ready
metadata_paths: [content/post]
service_names: [content-service]
control_planes:
  platform:
    enabled: true
    object_types: [service_catalog_entry]
    config_prefixes: [sys.content.]
  product:
    enabled: true
    object_types: [moderation_case]
    config_prefixes: [ops.content.]
minimum_package:
  metadata_files:
    - contracts/metadata/content/post/service.yaml
  codegen_targets: [go_runtime, python_runtime, ops_portal]
  test_evidence:
    t1: [contracts/metadata/content/post/service.yaml]
    t2: []
    t3: []
    t4: []
deployment:
  plane_binding_domain: content
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml
  current_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: [chat]
  copy_notes: [seed]
blocking_gaps: []
`)+"\n")
	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "domains", "chat.yaml"), strings.TrimSpace(`
version: 1
domain: chat
display_name: Chat
template_role: replica_ready
rollout_group: wave_1_copy
acceptance_status: metadata_ready
metadata_paths: [chat/thread]
service_names: [chat-service]
control_planes:
  platform:
    enabled: true
    object_types: [service_catalog_entry]
    config_prefixes: [sys.chat.]
  product:
    enabled: true
    object_types: [moderation_case]
    config_prefixes: [ops.chat.]
minimum_package:
  metadata_files:
    - contracts/metadata/chat/thread/service.yaml
  codegen_targets: [go_runtime, python_runtime, ops_portal]
  test_evidence:
    t1: [contracts/metadata/chat/thread/service.yaml]
    t2: [services/chat-service/tests/thread_contract_test.go]
    t3: []
    t4: []
deployment:
  plane_binding_domain: chat
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml
  current_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: []
  copy_notes: [copy]
blocking_gaps: []
`)+"\n")
	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "domains", "circle.yaml"), strings.TrimSpace(`
version: 1
domain: circle
display_name: Circle
template_role: replica_ready
rollout_group: wave_1_copy
acceptance_status: metadata_ready
metadata_paths: [circle/group]
service_names: [circle-service]
control_planes:
  platform:
    enabled: true
    object_types: [service_catalog_entry]
    config_prefixes: [sys.circle.]
  product:
    enabled: true
    object_types: [moderation_case]
    config_prefixes: [ops.circle.]
minimum_package:
  metadata_files:
    - contracts/metadata/circle/group/service.yaml
  codegen_targets: [go_runtime, python_runtime, ops_portal]
  test_evidence:
    t1: [contracts/metadata/circle/group/service.yaml]
    t2: [services/circle-service/tests/group_contract_test.go]
    t3: []
    t4: []
deployment:
  plane_binding_domain: circle
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml
  current_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: []
  copy_notes: [copy]
blocking_gaps: []
`)+"\n")
	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "domains", "user.yaml"), strings.TrimSpace(`
version: 1
domain: user
display_name: User
template_role: replica_ready
rollout_group: wave_1_copy
acceptance_status: metadata_ready
metadata_paths: [user/profile]
service_names: [user-service]
control_planes:
  platform:
    enabled: true
    object_types: [service_catalog_entry]
    config_prefixes: [sys.user.]
  product:
    enabled: true
    object_types: [moderation_case]
    config_prefixes: [ops.user.]
minimum_package:
  metadata_files:
    - contracts/metadata/user/profile/service.yaml
  codegen_targets: [go_runtime, python_runtime, ops_portal]
  test_evidence:
    t1: [contracts/metadata/user/profile/service.yaml]
    t2: [services/user-service/tests/profile_contract_test.go]
    t3: []
    t4: []
deployment:
  plane_binding_domain: user
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml
  current_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: []
  copy_notes: [copy]
blocking_gaps: []
`)+"\n")

	v := &validator{metadataDir: root}
	v.run()

	if !containsError(v.errors, "minimum_test_ready requires non-empty t2 evidence") {
		t.Fatalf("expected minimum_test_ready evidence validation error, got: %v", v.errors)
	}
}

func TestDomainOnboardingRejectsIntegrationPassWithBlockingGaps(t *testing.T) {
	root := createDomainOnboardingFixture(t)
	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "domains", "content.yaml"), strings.TrimSpace(`
version: 1
domain: content
display_name: Content
template_role: template_seed
rollout_group: wave_0_template
acceptance_status: integration_pass
metadata_paths: [content/post]
service_names: [content-service]
control_planes:
  platform:
    enabled: true
    object_types: [service_catalog_entry]
    config_prefixes: [sys.content.]
  product:
    enabled: true
    object_types: [moderation_case]
    config_prefixes: [ops.content.]
minimum_package:
  metadata_files:
    - contracts/metadata/content/post/service.yaml
  codegen_targets: [go_runtime, python_runtime, ops_portal]
  test_evidence:
    t1: [contracts/metadata/content/post/service.yaml]
    t2: [services/content-service/tests/post_comment_contract_test.go]
    t3: [contracts/metadata/content/post/service.yaml]
    t4: []
deployment:
  plane_binding_domain: content
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml
  current_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: [chat]
  copy_notes: [seed]
blocking_gaps:
  - waiting for final patrol
`)+"\n")
	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "domains", "chat.yaml"), strings.TrimSpace(`
version: 1
domain: chat
display_name: Chat
template_role: replica_ready
rollout_group: wave_1_copy
acceptance_status: metadata_ready
metadata_paths: [chat/thread]
service_names: [chat-service]
control_planes:
  platform:
    enabled: true
    object_types: [service_catalog_entry]
    config_prefixes: [sys.chat.]
  product:
    enabled: true
    object_types: [moderation_case]
    config_prefixes: [ops.chat.]
minimum_package:
  metadata_files:
    - contracts/metadata/chat/thread/service.yaml
  codegen_targets: [go_runtime, python_runtime, ops_portal]
  test_evidence:
    t1: [contracts/metadata/chat/thread/service.yaml]
    t2: [services/chat-service/tests/thread_contract_test.go]
    t3: []
    t4: []
deployment:
  plane_binding_domain: chat
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml
  current_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: []
  copy_notes: [copy]
blocking_gaps: []
`)+"\n")
	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "domains", "circle.yaml"), strings.TrimSpace(`
version: 1
domain: circle
display_name: Circle
template_role: replica_ready
rollout_group: wave_1_copy
acceptance_status: metadata_ready
metadata_paths: [circle/group]
service_names: [circle-service]
control_planes:
  platform:
    enabled: true
    object_types: [service_catalog_entry]
    config_prefixes: [sys.circle.]
  product:
    enabled: true
    object_types: [moderation_case]
    config_prefixes: [ops.circle.]
minimum_package:
  metadata_files:
    - contracts/metadata/circle/group/service.yaml
  codegen_targets: [go_runtime, python_runtime, ops_portal]
  test_evidence:
    t1: [contracts/metadata/circle/group/service.yaml]
    t2: [services/circle-service/tests/group_contract_test.go]
    t3: []
    t4: []
deployment:
  plane_binding_domain: circle
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml
  current_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: []
  copy_notes: [copy]
blocking_gaps: []
`)+"\n")
	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "domains", "user.yaml"), strings.TrimSpace(`
version: 1
domain: user
display_name: User
template_role: replica_ready
rollout_group: wave_1_copy
acceptance_status: metadata_ready
metadata_paths: [user/profile]
service_names: [user-service]
control_planes:
  platform:
    enabled: true
    object_types: [service_catalog_entry]
    config_prefixes: [sys.user.]
  product:
    enabled: true
    object_types: [moderation_case]
    config_prefixes: [ops.user.]
minimum_package:
  metadata_files:
    - contracts/metadata/user/profile/service.yaml
  codegen_targets: [go_runtime, python_runtime, ops_portal]
  test_evidence:
    t1: [contracts/metadata/user/profile/service.yaml]
    t2: [services/user-service/tests/profile_contract_test.go]
    t3: []
    t4: []
deployment:
  plane_binding_domain: user
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml
  current_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: []
  copy_notes: [copy]
blocking_gaps: []
`)+"\n")

	v := &validator{metadataDir: root}
	v.run()

	if !containsError(v.errors, "integration_pass requires blocking_gaps to be empty") {
		t.Fatalf("expected integration_pass blocking gap validation error, got: %v", v.errors)
	}
}

type controlPlaneFixtureOptions struct {
	platformApprovalMode string
	productConfigScope   string
	productConfigRollout string
	duplicateRoutePath   bool
}

func createControlPlaneMetadataFixture(t *testing.T, opts controlPlaneFixtureOptions) string {
	t.Helper()

	root := t.TempDir()
	mustWriteFixtureFile(t, filepath.Join(root, "_shared", "types.yaml"), "enums: {}\n")
	mustWriteFixtureFile(t, filepath.Join(root, "_shared", "control_plane.yaml"), strings.TrimSpace(`
version: 1
planes:
  - id: user-plane
    description: user
    traffic_profile: high_qps
    default_deploy_mode: service_container
    supports_independent_scaling: true
danger_levels:
  - id: low
    requires_confirmation: false
approval_modes:
  - id: none
    requires_distinct_approvers: false
object_kinds:
  - id: snapshot
dashboard_schema:
  required_fields: [primary_route, widgets]
  widget_examples: [release_health]
object_type_schema:
  required_fields: [object_type, label, source_entity, view_model, risk_level, deployment_profile, operations]
  optional_fields: [object_kind]
operation_schema:
  required_fields: [operation, method, path, scopes]
  optional_fields: [danger_level, approval_mode]
http_methods: [GET, POST]
scope_patterns: [ops.*, platform_ops.*, product_ops.*]
deployment_profiles:
  - id: latency_sensitive
    co_locatable_with_user_plane: false
    preferred_container_mode: dedicated
`)+"\n")

	platformRoute := "/platform/config"
	if opts.duplicateRoutePath {
		platformRoute = "/"
	}

	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "portal_shell.yaml"), strings.TrimSpace(`
portal_id: ops-portal
title: 趣我圈运营与平台门户
default_environment: integration
supported_environments: [dev, integration, prod]
default_domain: product-ops
domains:
  - id: overview
    label: 总览
    icon: layout-dashboard
global_search:
  enabled: true
  placeholder: 搜索对象
  object_types: [moderation_case]
notification_channels: [audit]
workbench_views:
  - id: pending-approval
    label: 待我审批
context_switchers: [environment, tenant]
dashboard_defaults:
  overview:
    kpis: [moderation_pending]
    charts: [moderation_case_trend]
`)+"\n")

	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "portal_menu.yaml"), strings.TrimSpace(`
menus:
  - menu_id: overview
    label: 总览
    domain: overview
    route_path: /
    icon: layout-dashboard
    order: 10
    permission_scope: ops.portal.read
    object_types: [dashboard]
  - menu_id: platform-config
    label: 配置与可靠性
    domain: platform-ops
    route_path: `+platformRoute+`
    icon: settings-2
    order: 20
    permission_scope: ops.platform.config.read
    object_types: [service_config]
`)+"\n")

	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "platform", "control_plane.yaml"), strings.TrimSpace(`
plane: platform-control-plane
domain: platform
dashboard:
  primary_route: /platform/config
  widgets: [release_health]
object_types:
  - object_type: service_config
    label: 服务配置
    source_entity: RuntimeConfig
    view_model: ServiceConfig
    risk_level: high
    deployment_profile: latency_sensitive
    operations:
      - operation: UpdateServiceConfig
        method: POST
        path: /v1/control-plane/platform/configs/{configKey}:update
        scopes: [ops.platform.config.write]
        danger_level: high
        approval_mode: `+opts.platformApprovalMode+`
`)+"\n")

	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "platform", "config_schema.yaml"), strings.TrimSpace(`
configs:
  - key: sys.gateway.rate_limit.per_user_rps
    type: int
    owner: platform-ops
    default: 30
    scope: service
    reload: hot
    rollout: package
    risk_level: high
    ui_editable: true
`)+"\n")

	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "product", "control_plane.yaml"), strings.TrimSpace(`
plane: product-control-plane
domain: product
dashboard:
  primary_route: /product/dashboard
  widgets: [moderation_summary]
object_types:
  - object_type: moderation_case
    label: 治理案例
    source_entity: Report
    view_model: ModerationCase
    risk_level: high
    deployment_profile: audit_heavy
    operations:
      - operation: ApplyEnforcementAction
        method: POST
        path: /v1/control-plane/product/moderation/cases/{caseId}:applyAction
        scopes: [ops.case.write]
        danger_level: high
        approval_mode: dual
`)+"\n")

	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "product", "config_schema.yaml"), strings.TrimSpace(`
configs:
  - key: ops.product.dashboard.default_time_range_days
    type: int
    owner: product-ops
    default: 7
    scope: `+opts.productConfigScope+`
    reload: hot
    rollout: `+opts.productConfigRollout+`
    risk_level: low
    ui_editable: true
`)+"\n")

	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "product", "workflow.yaml"), strings.TrimSpace(`
workflows:
  - workflow_id: recovery_case_v1
    object_type: recovery_case
    states: [requested, dual_review, recovered, closed]
    transitions:
      - from: requested
        to: [dual_review]
      - from: dual_review
        to: [recovered]
`)+"\n")

	mustWriteFixtureFile(t, filepath.Join(root, "_control_plane", "product", "audit_schema.yaml"), strings.TrimSpace(`
events:
  - audit_id: recovery_decision_submitted
    label: 恢复结论提交
    object_type: recovery_case
    danger_level: critical
    required_fields: [actor, environment, object_ref, action, request_id]
`)+"\n")

	return root
}

func mustWriteFixtureFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir fixture dir: %v", err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write fixture file: %v", err)
	}
}

func containsError(errs []string, want string) bool {
	for _, err := range errs {
		if strings.Contains(err, want) {
			return true
		}
	}
	return false
}

func createDomainOnboardingFixture(t *testing.T) string {
	t.Helper()

	baseMetadata := createControlPlaneMetadataFixture(t, controlPlaneFixtureOptions{
		platformApprovalMode: "dual",
		productConfigScope:   "environment",
		productConfigRollout: "experiment",
	})
	repoRoot := t.TempDir()
	metadataRoot := filepath.Join(repoRoot, "contracts", "metadata")
	copyDir(t, baseMetadata, metadataRoot)

	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "_control_plane", "domain_onboarding_schema.yaml"), strings.TrimSpace(`
version: 1
schema:
  acceptance_statuses: [schema_frozen, metadata_ready, codegen_ready, gate_ready, minimum_test_ready, deploy_bound, integration_pass_with_gaps, integration_pass]
  template_roles: [template_seed, replica_ready]
  rollout_groups: [wave_0_template, wave_1_copy]
  required_sections: [domain, display_name, template_role, rollout_group, acceptance_status, metadata_paths, service_names, control_planes, minimum_package, deployment, replication, blocking_gaps]
  required_control_plane_keys: [platform, product]
  required_test_layers: [t1, t2, t3, t4]
  required_codegen_targets: [go_runtime, python_runtime, ops_portal]
  status_rules:
    minimum_test_ready:
      min_test_layers: [t1, t2]
      require_all_codegen_targets: true
      require_plane_binding: false
      require_blocking_gaps_cleared: false
    deploy_bound:
      min_test_layers: [t1, t2]
      require_all_codegen_targets: true
      require_plane_binding: true
      require_blocking_gaps_cleared: false
    integration_pass_with_gaps:
      min_test_layers: [t1, t2, t3]
      require_all_codegen_targets: true
      require_plane_binding: true
      require_blocking_gaps_cleared: false
    integration_pass:
      min_test_layers: [t1, t2, t3]
      require_all_codegen_targets: true
      require_plane_binding: true
      require_blocking_gaps_cleared: true
minimum_package:
  template_domain: content
  first_wave_replica_domains: [chat, circle, user]
  required_deploy_sources:
    current: deploy/shared/process_domain_mapping.yaml
    plane_aware: deploy/shared/process_domain_plane_mapping.yaml
`)+"\n")

	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "content", "post", "aggregate.yaml"), "aggregate_root: Post\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "content", "post", "fields.yaml"), "entities:\n  Post:\n    fields: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "content", "post", "events.yaml"), "events: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "content", "post", "storage.yaml"), "collections: {}\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "content", "post", "service.yaml"), "routes: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "chat", "thread", "aggregate.yaml"), "aggregate_root: Thread\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "chat", "thread", "fields.yaml"), "entities:\n  Thread:\n    fields: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "chat", "thread", "events.yaml"), "events: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "chat", "thread", "storage.yaml"), "collections: {}\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "chat", "thread", "service.yaml"), "routes: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "circle", "group", "aggregate.yaml"), "aggregate_root: Group\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "circle", "group", "fields.yaml"), "entities:\n  Group:\n    fields: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "circle", "group", "events.yaml"), "events: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "circle", "group", "storage.yaml"), "collections: {}\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "circle", "group", "service.yaml"), "routes: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "user", "profile", "aggregate.yaml"), "aggregate_root: Profile\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "user", "profile", "fields.yaml"), "entities:\n  Profile:\n    fields: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "user", "profile", "events.yaml"), "events: []\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "user", "profile", "storage.yaml"), "collections: {}\n")
	mustWriteFixtureFile(t, filepath.Join(metadataRoot, "user", "profile", "service.yaml"), "routes: []\n")
	mustWriteFixtureFile(t, filepath.Join(repoRoot, "services", "content-service", "tests", "post_comment_contract_test.go"), "package tests\n")
	mustWriteFixtureFile(t, filepath.Join(repoRoot, "services", "chat-service", "tests", "thread_contract_test.go"), "package tests\n")
	mustWriteFixtureFile(t, filepath.Join(repoRoot, "services", "circle-service", "tests", "group_contract_test.go"), "package tests\n")
	mustWriteFixtureFile(t, filepath.Join(repoRoot, "services", "user-service", "tests", "profile_contract_test.go"), "package tests\n")

	return metadataRoot
}

func copyDir(t *testing.T, src, dst string) {
	t.Helper()
	entries, err := os.ReadDir(src)
	if err != nil {
		t.Fatalf("read source dir: %v", err)
	}
	for _, entry := range entries {
		srcPath := filepath.Join(src, entry.Name())
		dstPath := filepath.Join(dst, entry.Name())
		if entry.IsDir() {
			if err := os.MkdirAll(dstPath, 0o755); err != nil {
				t.Fatalf("mkdir dst dir: %v", err)
			}
			copyDir(t, srcPath, dstPath)
			continue
		}
		data, err := os.ReadFile(srcPath)
		if err != nil {
			t.Fatalf("read src file: %v", err)
		}
		mustWriteFixtureFile(t, dstPath, string(data))
	}
}
