package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCodegenControlPlaneRuntimeGeneratesGoAndPythonArtifacts(t *testing.T) {
	metadataDir := t.TempDir()
	goOutDir := t.TempDir()
	pythonOutDir := t.TempDir()

	writeFixture(t, filepath.Join(metadataDir, "_shared", "control_plane.yaml"), `
version: 1
planes:
  - id: platform-control-plane
    description: platform
    traffic_profile: low_qps_high_risk
    default_deploy_mode: seed_box
    supports_independent_scaling: true
danger_levels:
  - id: high
    requires_confirmation: true
approval_modes:
  - id: dual
    requires_distinct_approvers: true
object_kinds:
  - id: policy
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
scope_patterns: [ops.*, platform_ops.*]
deployment_profiles:
  - id: latency_sensitive
    co_locatable_with_user_plane: false
    preferred_container_mode: dedicated
`)
	writeFixture(t, filepath.Join(metadataDir, "_control_plane", "portal_shell.yaml"), `
version: 1
portal_id: ops-portal
title: 趣我圈运营与平台门户
default_environment: integration
supported_environments: [dev, integration, prod]
default_domain: platform-ops
domains:
  - id: platform-ops
    label: Platform Ops
    icon: server-cog
global_search:
  enabled: true
  placeholder: 搜索配置
  object_types: [service_config]
notification_channels: [rollout]
workbench_views:
  - id: active-rollout
    label: 灰度观察
context_switchers: [environment]
dashboard_defaults:
  overview:
    kpis: [rollout_health]
    charts: [release_health]
`)
	writeFixture(t, filepath.Join(metadataDir, "_control_plane", "portal_menu.yaml"), `
version: 1
menus:
  - menu_id: platform-config
    label: 配置与可靠性
    domain: platform-ops
    route_path: /platform/config
    icon: settings-2
    order: 20
    permission_scope: ops.platform.config.read
    object_types: [service_config]
`)
	writeFixture(t, filepath.Join(metadataDir, "_control_plane", "domain_onboarding_schema.yaml"), `
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
    legacy: deploy/shared/process_domain_mapping.yaml
    plane_aware: deploy/shared/process_domain_plane_mapping.yaml
`)
	writeFixture(t, filepath.Join(metadataDir, "_control_plane", "domains", "content.yaml"), `
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
  legacy_binding_source: deploy/shared/process_domain_mapping.yaml
replication:
  source_template: content
  next_copy_targets: [chat]
  copy_notes: [seed]
`)
	writeFixture(t, filepath.Join(metadataDir, "_control_plane", "platform", "control_plane.yaml"), `
version: 1
plane: platform-control-plane
domain: platform
dashboard:
  primary_route: /platform/config
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
        approval_mode: dual
`)
	writeFixture(t, filepath.Join(metadataDir, "_control_plane", "platform", "config_schema.yaml"), `
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

	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()
	os.Args = []string{
		"codegen_control_plane_runtime",
		"--metadata-dir", metadataDir,
		"--go-out-dir", goOutDir,
		"--python-out-dir", pythonOutDir,
	}

	main()

	expectedGoFiles := []string{
		"shared_control_plane.go",
		"portal_shell.go",
		"portal_menu.go",
		"domain_onboarding_schema.go",
		"domain_onboarding_domains.go",
		"platform_control_plane.go",
		"platform_config_schema.go",
	}
	for _, name := range expectedGoFiles {
		content, err := os.ReadFile(filepath.Join(goOutDir, name))
		if err != nil {
			t.Fatalf("expected go file %s: %v", name, err)
		}
		if len(content) == 0 {
			t.Fatalf("go file %s should not be empty", name)
		}
	}

	expectedPythonFiles := []string{
		"shared_control_plane.py",
		"portal_shell.py",
		"portal_menu.py",
		"domain_onboarding_schema.py",
		"domain_onboarding_domains.py",
		"platform_control_plane.py",
		"platform_config_schema.py",
		"__init__.py",
	}
	for _, name := range expectedPythonFiles {
		content, err := os.ReadFile(filepath.Join(pythonOutDir, name))
		if err != nil {
			t.Fatalf("expected python file %s: %v", name, err)
		}
		if len(content) == 0 {
			t.Fatalf("python file %s should not be empty", name)
		}
	}

	goText, err := os.ReadFile(filepath.Join(goOutDir, "platform_control_plane.go"))
	if err != nil {
		t.Fatalf("read generated go module: %v", err)
	}
	if !strings.Contains(string(goText), "MustLoadPlatformControlPlane") || !strings.Contains(string(goText), `\"object_kind\": \"policy\"`) {
		t.Fatalf("generated go file missing expected content: %s", string(goText))
	}

	pyText, err := os.ReadFile(filepath.Join(pythonOutDir, "platform_control_plane.py"))
	if err != nil {
		t.Fatalf("read generated python module: %v", err)
	}
	if !strings.Contains(string(pyText), "PLATFORM_CONTROL_PLANE") || !strings.Contains(string(pyText), `"/v1/control-plane/platform/configs/{configKey}:update"`) {
		t.Fatalf("generated python file missing expected content: %s", string(pyText))
	}

	onboardingText, err := os.ReadFile(filepath.Join(goOutDir, "domain_onboarding_domains.go"))
	if err != nil {
		t.Fatalf("read onboarding go module: %v", err)
	}
	if !strings.Contains(string(onboardingText), "MustLoadDomainOnboardingDomains") || !strings.Contains(string(onboardingText), `\"domain\": \"content\"`) {
		t.Fatalf("generated onboarding go file missing expected content: %s", string(onboardingText))
	}
}

func writeFixture(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir fixture dir: %v", err)
	}
	if err := os.WriteFile(path, []byte(strings.TrimSpace(content)+"\n"), 0o644); err != nil {
		t.Fatalf("write fixture file: %v", err)
	}
}
