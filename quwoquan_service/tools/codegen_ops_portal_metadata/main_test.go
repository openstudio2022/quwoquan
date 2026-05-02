package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCodegenOpsPortalMetadataGeneratesExpectedFiles(t *testing.T) {
	metadataDir := t.TempDir()
	portalDir := t.TempDir()

	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "portal_shell.yaml"), `
version: 1
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
`)

	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "portal_menu.yaml"), `
version: 1
menus:
  - menu_id: overview
    label: 总览
    domain: overview
    route_path: /
    icon: layout-dashboard
    order: 10
    permission_scope: ops.portal.read
    object_types: [dashboard]
`)
	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "domain_onboarding_schema.yaml"), `
version: 1
schema:
  acceptance_statuses: [schema_frozen, metadata_ready]
  template_roles: [template_seed, replica_ready]
  rollout_groups: [wave_0_template, wave_1_copy]
  required_sections: [domain]
  required_control_plane_keys: [platform, product]
  required_test_layers: [t1, t2, t3, t4]
  required_codegen_targets: [go_runtime, python_runtime, ops_portal]
minimum_package:
  template_domain: content
  first_wave_replica_domains: [chat]
  required_deploy_sources:
    current: deploy/shared/process_domain_mapping.yaml
    plane_aware: deploy/shared/process_domain_plane_mapping.yaml
`)
	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "domains", "content.yaml"), `
version: 1
domain: content
display_name: Content
template_role: template_seed
rollout_group: wave_0_template
acceptance_status: metadata_ready
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
  metadata_files: [contracts/metadata/content/post/service.yaml]
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
`)

	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "platform", "control_plane.yaml"), `
version: 1
plane: platform-control-plane
domain: platform
dashboard:
  primary_route: /platform
  widgets: [release_health]
object_types:
  - object_type: service_config
    object_kind: policy
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
        approval_mode: single
`)

	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "platform", "config_schema.yaml"), `
version: 1
configs:
  - key: sys.gateway.rate_limit.per_user_rps
    type: int
    owner: platform-ops
    default: 30
    scope: service
    reload: hot
    rollout: progressive
    risk_level: high
    ui_editable: true
`)

	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "product", "control_plane.yaml"), `
version: 1
plane: product-control-plane
domain: product
dashboard:
  primary_route: /product/dashboard
  widgets: [moderation_summary]
object_types:
  - object_type: moderation_case
    object_kind: workflow_case
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
`)

	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "product", "config_schema.yaml"), `
version: 1
configs:
  - key: ops.product.dashboard.default_time_range_days
    type: int
    owner: product-ops
    default: 7
    scope: environment
    reload: hot
    rollout: none
    risk_level: low
    ui_editable: true
`)

	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "product", "workflow.yaml"), `
version: 1
workflows:
  - workflow_id: recovery_case_v1
    object_type: recovery_case
    states: [requested, dual_review, recovered, closed]
    transitions:
      - from: requested
        to: [dual_review]
`)

	writePortalFixture(t, filepath.Join(metadataDir, "_control_plane", "product", "audit_schema.yaml"), `
version: 1
events:
  - audit_id: recovery_decision_submitted
    label: 恢复结论提交
    object_type: recovery_case
    danger_level: critical
    required_fields: [actor, environment, object_ref, action, request_id]
`)

	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()
	os.Args = []string{
		"codegen_ops_portal_metadata",
		"--metadata-dir", metadataDir,
		"--portal-dir", portalDir,
	}

	main()

	expectedFiles := []string{
		"portalShell.generated.ts",
		"portalMenu.generated.ts",
		"domainOnboardingSchema.generated.ts",
		"domainOnboardingDomains.generated.ts",
		"platformControlPlane.generated.ts",
		"platformConfig.generated.ts",
		"productControlPlane.generated.ts",
		"productConfig.generated.ts",
		"productWorkflow.generated.ts",
		"productAudit.generated.ts",
		"index.ts",
	}

	outDir := filepath.Join(portalDir, "src", "generated", "control-plane")
	for _, file := range expectedFiles {
		path := filepath.Join(outDir, file)
		content, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("expected generated file %s: %v", file, err)
		}
		if len(content) == 0 {
			t.Fatalf("generated file %s should not be empty", file)
		}
	}

	indexContent, err := os.ReadFile(filepath.Join(outDir, "index.ts"))
	if err != nil {
		t.Fatalf("read index.ts: %v", err)
	}
	indexText := string(indexContent)
	for _, exportName := range []string{
		"portalShell.generated",
		"portalMenu.generated",
		"domainOnboardingSchema.generated",
		"domainOnboardingDomains.generated",
		"platformControlPlane.generated",
		"productControlPlane.generated",
	} {
		if !strings.Contains(indexText, exportName) {
			t.Fatalf("index.ts missing export %s: %s", exportName, indexText)
		}
	}

	platformContent, err := os.ReadFile(filepath.Join(outDir, "platformControlPlane.generated.ts"))
	if err != nil {
		t.Fatalf("read platformControlPlane.generated.ts: %v", err)
	}
	platformText := string(platformContent)
	if !strings.Contains(platformText, `"version": 1`) || !strings.Contains(platformText, `"object_kind": "policy"`) {
		t.Fatalf("platform control plane output missing version/object_kind: %s", platformText)
	}

	onboardingContent, err := os.ReadFile(filepath.Join(outDir, "domainOnboardingDomains.generated.ts"))
	if err != nil {
		t.Fatalf("read domainOnboardingDomains.generated.ts: %v", err)
	}
	if !strings.Contains(string(onboardingContent), `"content"`) || !strings.Contains(string(onboardingContent), `"template_role": "template_seed"`) {
		t.Fatalf("onboarding output missing expected content: %s", string(onboardingContent))
	}
}

func writePortalFixture(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir fixture dir: %v", err)
	}
	if err := os.WriteFile(path, []byte(strings.TrimSpace(content)+"\n"), 0o644); err != nil {
		t.Fatalf("write fixture file: %v", err)
	}
}
