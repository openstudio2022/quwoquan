package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

func main() {
	metadataDir := "contracts/metadata"
	if len(os.Args) > 1 {
		metadataDir = os.Args[1]
	}

	v := &validator{
		metadataDir: metadataDir,
		errors:      nil,
		warnings:    nil,
	}

	v.run()

	if len(v.warnings) > 0 {
		fmt.Printf("\n⚠ Warnings (%d):\n", len(v.warnings))
		for _, w := range v.warnings {
			fmt.Printf("  - %s\n", w)
		}
	}

	if len(v.errors) > 0 {
		fmt.Printf("\n✗ Errors (%d):\n", len(v.errors))
		for _, e := range v.errors {
			fmt.Printf("  - %s\n", e)
		}
		os.Exit(1)
	}

	fmt.Printf("\n✓ Metadata validation passed. %d aggregates/entities, %d enums.\n",
		v.objectCount, v.enumCount)
}

type validator struct {
	metadataDir string
	errors      []string
	warnings    []string
	enums       map[string]bool
	objectCount int
	enumCount   int
}

func (v *validator) errorf(format string, args ...any) {
	v.errors = append(v.errors, fmt.Sprintf(format, args...))
}

func (v *validator) warnf(format string, args ...any) {
	v.warnings = append(v.warnings, fmt.Sprintf(format, args...))
}

func (v *validator) run() {
	v.loadSharedEnums()
	v.validateSharedControlPlaneBaseline()
	v.validateControlPlaneMetadata()
	v.validateDomainOnboardingMetadata()
	v.validateBusinessObjects()
}

type sharedControlPlaneDefinition struct {
	Version int `yaml:"version"`
	Planes  []struct {
		ID                      string `yaml:"id"`
		Description             string `yaml:"description"`
		TrafficProfile          string `yaml:"traffic_profile"`
		DefaultDeployMode       string `yaml:"default_deploy_mode"`
		SupportsIndependentScal bool   `yaml:"supports_independent_scaling"`
	} `yaml:"planes"`
	DangerLevels []struct {
		ID                   string `yaml:"id"`
		RequiresConfirmation bool   `yaml:"requires_confirmation"`
	} `yaml:"danger_levels"`
	ApprovalModes []struct {
		ID                       string `yaml:"id"`
		RequiresDistinctApprover bool   `yaml:"requires_distinct_approvers"`
	} `yaml:"approval_modes"`
	ObjectKinds []struct {
		ID string `yaml:"id"`
	} `yaml:"object_kinds"`
	DashboardSchema struct {
		RequiredFields []string `yaml:"required_fields"`
		WidgetExamples []string `yaml:"widget_examples"`
	} `yaml:"dashboard_schema"`
	ObjectTypeSchema struct {
		RequiredFields []string `yaml:"required_fields"`
		OptionalFields []string `yaml:"optional_fields"`
	} `yaml:"object_type_schema"`
	OperationSchema struct {
		RequiredFields []string `yaml:"required_fields"`
		OptionalFields []string `yaml:"optional_fields"`
	} `yaml:"operation_schema"`
	HTTPMethods        []string `yaml:"http_methods"`
	ScopePatterns      []string `yaml:"scope_patterns"`
	DeploymentProfiles []struct {
		ID                     string `yaml:"id"`
		CoLocatableWithUser    bool   `yaml:"co_locatable_with_user_plane"`
		PreferredContainerMode string `yaml:"preferred_container_mode"`
	} `yaml:"deployment_profiles"`
}

type controlPlanePortalShell struct {
	PortalID           string `yaml:"portal_id"`
	Title              string `yaml:"title"`
	DefaultEnvironment string `yaml:"default_environment"`
}

type controlPlanePortalMenu struct {
	Menus []struct {
		MenuID          string   `yaml:"menu_id"`
		ParentMenuID    string   `yaml:"parent_menu_id"`
		Label           string   `yaml:"label"`
		Domain          string   `yaml:"domain"`
		RoutePath       string   `yaml:"route_path"`
		PermissionScope string   `yaml:"permission_scope"`
		ObjectTypes     []string `yaml:"object_types"`
	} `yaml:"menus"`
}

type controlPlaneDefinition struct {
	Plane     string `yaml:"plane"`
	Domain    string `yaml:"domain"`
	Dashboard struct {
		PrimaryRoute string   `yaml:"primary_route"`
		Widgets      []string `yaml:"widgets"`
	} `yaml:"dashboard"`
	ObjectTypes []struct {
		ObjectType        string `yaml:"object_type"`
		RiskLevel         string `yaml:"risk_level"`
		DeploymentProfile string `yaml:"deployment_profile"`
		Operations        []struct {
			Operation    string   `yaml:"operation"`
			Method       string   `yaml:"method"`
			Path         string   `yaml:"path"`
			Scopes       []string `yaml:"scopes"`
			DangerLevel  string   `yaml:"danger_level"`
			ApprovalMode string   `yaml:"approval_mode"`
		} `yaml:"operations"`
		AnalyticsViews []struct {
			ViewID           string   `yaml:"view_id"`
			WidgetTypes      []string `yaml:"widget_types"`
			DrilldownRouteID string   `yaml:"drilldown_route_id"`
		} `yaml:"analytics_views"`
	} `yaml:"object_types"`
}

type controlPlaneConfigSchema struct {
	Configs []struct {
		Key       string `yaml:"key"`
		Scope     string `yaml:"scope"`
		Reload    string `yaml:"reload"`
		Rollout   string `yaml:"rollout"`
		RiskLevel string `yaml:"risk_level"`
	} `yaml:"configs"`
}

type controlPlaneWorkflowSchema struct {
	Workflows []struct {
		WorkflowID  string `yaml:"workflow_id"`
		ObjectType  string `yaml:"object_type"`
		States      []string
		Transitions []struct {
			From string   `yaml:"from"`
			To   []string `yaml:"to"`
		} `yaml:"transitions"`
	} `yaml:"workflows"`
}

type controlPlaneAuditSchema struct {
	Events []struct {
		AuditID        string   `yaml:"audit_id"`
		ObjectType     string   `yaml:"object_type"`
		DangerLevel    string   `yaml:"danger_level"`
		RequiredFields []string `yaml:"required_fields"`
	} `yaml:"events"`
}

type domainOnboardingSchema struct {
	Schema struct {
		AcceptanceStatuses       []string `yaml:"acceptance_statuses"`
		TemplateRoles            []string `yaml:"template_roles"`
		RolloutGroups            []string `yaml:"rollout_groups"`
		RequiredSections         []string `yaml:"required_sections"`
		RequiredControlPlaneKeys []string `yaml:"required_control_plane_keys"`
		RequiredTestLayers       []string `yaml:"required_test_layers"`
		RequiredCodegenTargets   []string `yaml:"required_codegen_targets"`
		StatusRules              map[string]struct {
			MinTestLayers              []string `yaml:"min_test_layers"`
			RequireAllCodegenTargets   bool     `yaml:"require_all_codegen_targets"`
			RequirePlaneBinding        bool     `yaml:"require_plane_binding"`
			RequireBlockingGapsCleared bool     `yaml:"require_blocking_gaps_cleared"`
		} `yaml:"status_rules"`
	} `yaml:"schema"`
	MinimumPackage struct {
		TemplateDomain          string   `yaml:"template_domain"`
		FirstWaveReplicaDomains []string `yaml:"first_wave_replica_domains"`
		RequiredDeploySources   struct {
			Legacy     string `yaml:"legacy"`
			PlaneAware string `yaml:"plane_aware"`
		} `yaml:"required_deploy_sources"`
	} `yaml:"minimum_package"`
}

type domainOnboardingFile struct {
	Domain           string   `yaml:"domain"`
	DisplayName      string   `yaml:"display_name"`
	TemplateRole     string   `yaml:"template_role"`
	RolloutGroup     string   `yaml:"rollout_group"`
	AcceptanceStatus string   `yaml:"acceptance_status"`
	MetadataPaths    []string `yaml:"metadata_paths"`
	ServiceNames     []string `yaml:"service_names"`
	ControlPlanes    map[string]struct {
		Enabled        bool     `yaml:"enabled"`
		ObjectTypes    []string `yaml:"object_types"`
		ConfigPrefixes []string `yaml:"config_prefixes"`
	} `yaml:"control_planes"`
	MinimumPackage struct {
		MetadataFiles  []string            `yaml:"metadata_files"`
		CodegenTargets []string            `yaml:"codegen_targets"`
		TestEvidence   map[string][]string `yaml:"test_evidence"`
	} `yaml:"minimum_package"`
	Deployment struct {
		PlaneBindingDomain  string `yaml:"plane_binding_domain"`
		PlaneBindingSource  string `yaml:"plane_binding_source"`
		LegacyBindingSource string `yaml:"legacy_binding_source"`
	} `yaml:"deployment"`
	Replication struct {
		SourceTemplate  string   `yaml:"source_template"`
		NextCopyTargets []string `yaml:"next_copy_targets"`
		CopyNotes       []string `yaml:"copy_notes"`
	} `yaml:"replication"`
	BlockingGaps []string `yaml:"blocking_gaps"`
}

func (v *validator) validateControlPlaneMetadata() {
	root := filepath.Join(v.metadataDir, "_control_plane")
	info, err := os.Stat(root)
	if err != nil {
		v.warnf("_control_plane/: not found, skip control plane validation")
		return
	}
	if !info.IsDir() {
		v.errorf("_control_plane: should be a directory")
		return
	}

	v.validatePortalShell(root)
	routePaths := v.validatePortalMenu(root)
	v.validateControlPlaneDomain(root, "platform", routePaths, false)
	v.validateControlPlaneDomain(root, "product", routePaths, true)
}

func (v *validator) validateDomainOnboardingMetadata() {
	schemaPath := filepath.Join(v.metadataDir, "_control_plane", "domain_onboarding_schema.yaml")
	if !fileExists(schemaPath) {
		v.warnf("_control_plane/domain_onboarding_schema.yaml: not found, skip domain onboarding validation")
		return
	}

	data, ok := v.readYAMLFile(schemaPath)
	if !ok {
		return
	}

	var schema domainOnboardingSchema
	if err := yaml.Unmarshal(data, &schema); err != nil {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: parse error: %v", err)
		return
	}
	if len(schema.Schema.AcceptanceStatuses) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.acceptance_statuses cannot be empty")
	}
	if len(schema.Schema.TemplateRoles) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.template_roles cannot be empty")
	}
	if len(schema.Schema.RolloutGroups) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.rollout_groups cannot be empty")
	}
	if len(schema.Schema.RequiredControlPlaneKeys) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_control_plane_keys cannot be empty")
	}
	if len(schema.Schema.RequiredTestLayers) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_test_layers cannot be empty")
	}
	if len(schema.Schema.RequiredCodegenTargets) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_codegen_targets cannot be empty")
	}
	if len(schema.Schema.RequiredSections) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_sections cannot be empty")
	}
	for _, section := range schema.Schema.RequiredSections {
		if strings.TrimSpace(section) == "" {
			v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_sections cannot contain empty values")
		}
	}
	for status, rule := range schema.Schema.StatusRules {
		if !contains(schema.Schema.AcceptanceStatuses, status) {
			v.errorf("_control_plane/domain_onboarding_schema.yaml: status_rules.%s references unknown acceptance_status", status)
		}
		for _, layer := range rule.MinTestLayers {
			if !contains(schema.Schema.RequiredTestLayers, layer) {
				v.errorf("_control_plane/domain_onboarding_schema.yaml: status_rules.%s.min_test_layers contains unknown layer %q", status, layer)
			}
		}
	}
	if schema.MinimumPackage.TemplateDomain == "" {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: minimum_package.template_domain is required")
	}
	if schema.MinimumPackage.RequiredDeploySources.Legacy == "" || schema.MinimumPackage.RequiredDeploySources.PlaneAware == "" {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: minimum_package.required_deploy_sources.{legacy,plane_aware} are required")
	}

	domainsDir := filepath.Join(v.metadataDir, "_control_plane", "domains")
	entries, err := os.ReadDir(domainsDir)
	if err != nil {
		v.errorf("_control_plane/domains: %v", err)
		return
	}

	allowedStatuses := sliceToSet(schema.Schema.AcceptanceStatuses)
	allowedTemplateRoles := sliceToSet(schema.Schema.TemplateRoles)
	allowedRolloutGroups := sliceToSet(schema.Schema.RolloutGroups)
	allowedCodegenTargets := sliceToSet(schema.Schema.RequiredCodegenTargets)
	allowedLayers := sliceToSet(schema.Schema.RequiredTestLayers)
	requiredControlPlaneKeys := sliceToSet(schema.Schema.RequiredControlPlaneKeys)
	statusRules := schema.Schema.StatusRules
	statusRank := map[string]int{}
	for idx, status := range schema.Schema.AcceptanceStatuses {
		statusRank[status] = idx
	}

	seenDomains := map[string]bool{}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".yaml") {
			continue
		}
		path := filepath.Join(domainsDir, entry.Name())
		raw, ok := v.readYAMLFile(path)
		if !ok {
			continue
		}

		var rawDoc map[string]any
		if err := yaml.Unmarshal(raw, &rawDoc); err != nil {
			v.errorf("%s: parse error: %v", pathRelative(v.metadataDir, path), err)
			continue
		}
		for _, section := range schema.Schema.RequiredSections {
			if _, ok := rawDoc[section]; !ok {
				v.errorf("%s: missing required section %q", pathRelative(v.metadataDir, path), section)
			}
		}

		var parsed domainOnboardingFile
		if err := yaml.Unmarshal(raw, &parsed); err != nil {
			v.errorf("%s: parse error: %v", pathRelative(v.metadataDir, path), err)
			continue
		}
		if parsed.Domain == "" {
			v.errorf("%s: domain is required", pathRelative(v.metadataDir, path))
			continue
		}
		if seenDomains[parsed.Domain] {
			v.errorf("%s: duplicate domain %q", pathRelative(v.metadataDir, path), parsed.Domain)
			continue
		}
		seenDomains[parsed.Domain] = true

		if parsed.DisplayName == "" {
			v.errorf("%s: display_name is required", pathRelative(v.metadataDir, path))
		}
		if !allowedTemplateRoles[parsed.TemplateRole] {
			v.errorf("%s: template_role %q is invalid", pathRelative(v.metadataDir, path), parsed.TemplateRole)
		}
		if !allowedRolloutGroups[parsed.RolloutGroup] {
			v.errorf("%s: rollout_group %q is invalid", pathRelative(v.metadataDir, path), parsed.RolloutGroup)
		}
		if !allowedStatuses[parsed.AcceptanceStatus] {
			v.errorf("%s: acceptance_status %q is invalid", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
		}
		if len(parsed.MetadataPaths) == 0 {
			v.errorf("%s: metadata_paths cannot be empty", pathRelative(v.metadataDir, path))
		}
		for _, metadataPath := range parsed.MetadataPaths {
			if !fileExists(filepath.Join(v.metadataDir, metadataPath)) {
				v.errorf("%s: metadata_paths entry %q does not exist", pathRelative(v.metadataDir, path), metadataPath)
			}
		}
		if len(parsed.ServiceNames) == 0 {
			v.errorf("%s: service_names cannot be empty", pathRelative(v.metadataDir, path))
		}
		for key := range requiredControlPlaneKeys {
			controlPlane, ok := parsed.ControlPlanes[key]
			if !ok {
				v.errorf("%s: missing control_planes.%s", pathRelative(v.metadataDir, path), key)
				continue
			}
			if controlPlane.Enabled {
				if len(controlPlane.ObjectTypes) == 0 {
					v.errorf("%s: control_planes.%s.object_types cannot be empty when enabled", pathRelative(v.metadataDir, path), key)
				}
				if len(controlPlane.ConfigPrefixes) == 0 {
					v.errorf("%s: control_planes.%s.config_prefixes cannot be empty when enabled", pathRelative(v.metadataDir, path), key)
				}
			}
		}
		missingCodegenTargets := missingItems(parsed.MinimumPackage.CodegenTargets, schema.Schema.RequiredCodegenTargets)
		for _, target := range parsed.MinimumPackage.CodegenTargets {
			if !allowedCodegenTargets[target] {
				v.errorf("%s: codegen_targets entry %q is invalid", pathRelative(v.metadataDir, path), target)
			}
		}
		if len(parsed.MinimumPackage.CodegenTargets) == 0 {
			v.errorf("%s: minimum_package.codegen_targets cannot be empty", pathRelative(v.metadataDir, path))
		}
		if len(missingCodegenTargets) > 0 {
			v.errorf("%s: minimum_package.codegen_targets missing required targets %q", pathRelative(v.metadataDir, path), strings.Join(missingCodegenTargets, ", "))
		}
		for _, filePath := range parsed.MinimumPackage.MetadataFiles {
			if !fileExists(filepath.Join(v.repoRoot(), filePath)) {
				v.errorf("%s: metadata_files entry %q does not exist", pathRelative(v.metadataDir, path), filePath)
			}
		}
		if len(parsed.MinimumPackage.MetadataFiles) == 0 {
			v.errorf("%s: minimum_package.metadata_files cannot be empty", pathRelative(v.metadataDir, path))
		}
		for layer := range allowedLayers {
			files := parsed.MinimumPackage.TestEvidence[layer]
			if files == nil {
				v.errorf("%s: missing minimum_package.test_evidence.%s", pathRelative(v.metadataDir, path), layer)
				continue
			}
			for _, filePath := range files {
				if !fileExists(filepath.Join(v.repoRoot(), filePath)) {
					v.errorf("%s: test_evidence.%s entry %q does not exist", pathRelative(v.metadataDir, path), layer, filePath)
				}
			}
		}
		if parsed.Deployment.PlaneBindingDomain == "" || parsed.Deployment.PlaneBindingSource == "" || parsed.Deployment.LegacyBindingSource == "" {
			v.errorf("%s: deployment plane binding fields are required", pathRelative(v.metadataDir, path))
		}
		if parsed.Deployment.PlaneBindingDomain != parsed.Domain {
			v.errorf("%s: deployment.plane_binding_domain must equal domain", pathRelative(v.metadataDir, path))
		}
		if parsed.Deployment.PlaneBindingSource != schema.MinimumPackage.RequiredDeploySources.PlaneAware {
			v.errorf("%s: deployment.plane_binding_source must equal %q", pathRelative(v.metadataDir, path), schema.MinimumPackage.RequiredDeploySources.PlaneAware)
		}
		if parsed.Deployment.LegacyBindingSource != schema.MinimumPackage.RequiredDeploySources.Legacy {
			v.errorf("%s: deployment.legacy_binding_source must equal %q", pathRelative(v.metadataDir, path), schema.MinimumPackage.RequiredDeploySources.Legacy)
		}
		if parsed.TemplateRole == "template_seed" && parsed.Replication.SourceTemplate != parsed.Domain {
			v.errorf("%s: template_seed domain must self-reference replication.source_template", pathRelative(v.metadataDir, path))
		}
		if rule, ok := statusRules[parsed.AcceptanceStatus]; ok {
			for _, layer := range rule.MinTestLayers {
				if len(parsed.MinimumPackage.TestEvidence[layer]) == 0 {
					v.errorf("%s: %s requires non-empty %s evidence", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus, layer)
				}
			}
			if rule.RequireAllCodegenTargets && len(missingCodegenTargets) > 0 {
				v.errorf("%s: %s requires all required codegen targets", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
			}
			if rule.RequirePlaneBinding {
				if parsed.Deployment.PlaneBindingDomain == "" || parsed.Deployment.PlaneBindingSource == "" || parsed.Deployment.LegacyBindingSource == "" {
					v.errorf("%s: %s requires deployment plane binding fields", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
				}
			}
			if rule.RequireBlockingGapsCleared && len(parsed.BlockingGaps) > 0 {
				v.errorf("%s: %s requires blocking_gaps to be empty", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
			}
		}
		if threshold, ok := statusRank["integration_pass_with_gaps"]; ok && statusRank[parsed.AcceptanceStatus] >= threshold && len(parsed.MinimumPackage.TestEvidence["t3"]) == 0 {
			v.errorf("%s: %s requires non-empty t3 evidence", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
		}
		if threshold, ok := statusRank["deploy_bound"]; ok && statusRank[parsed.AcceptanceStatus] >= threshold && len(parsed.MinimumPackage.TestEvidence["t1"]) == 0 {
			v.errorf("%s: %s requires non-empty t1 evidence", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
		}
	}

	if !seenDomains[schema.MinimumPackage.TemplateDomain] {
		v.errorf("_control_plane/domains: template domain %q not found", schema.MinimumPackage.TemplateDomain)
	}
	for _, domain := range schema.MinimumPackage.FirstWaveReplicaDomains {
		if !seenDomains[domain] {
			v.errorf("_control_plane/domains: first-wave replica domain %q not found", domain)
		}
	}
}

func (v *validator) validateSharedControlPlaneBaseline() {
	path := filepath.Join(v.metadataDir, "_shared", "control_plane.yaml")
	data, err := os.ReadFile(path)
	if err != nil {
		v.errorf("_shared/control_plane.yaml: %v", err)
		return
	}

	var parsed sharedControlPlaneDefinition
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("_shared/control_plane.yaml: parse error: %v", err)
		return
	}

	if parsed.Version <= 0 {
		v.errorf("_shared/control_plane.yaml: version must be >= 1")
	}
	if len(parsed.Planes) == 0 {
		v.errorf("_shared/control_plane.yaml: planes cannot be empty")
	}
	if len(parsed.DangerLevels) == 0 {
		v.errorf("_shared/control_plane.yaml: danger_levels cannot be empty")
	}
	if len(parsed.ApprovalModes) == 0 {
		v.errorf("_shared/control_plane.yaml: approval_modes cannot be empty")
	}
	if len(parsed.ObjectKinds) == 0 {
		v.errorf("_shared/control_plane.yaml: object_kinds cannot be empty")
	}
	if len(parsed.DashboardSchema.RequiredFields) == 0 {
		v.errorf("_shared/control_plane.yaml: dashboard_schema.required_fields cannot be empty")
	}
	if len(parsed.ObjectTypeSchema.RequiredFields) == 0 {
		v.errorf("_shared/control_plane.yaml: object_type_schema.required_fields cannot be empty")
	}
	if len(parsed.OperationSchema.RequiredFields) == 0 {
		v.errorf("_shared/control_plane.yaml: operation_schema.required_fields cannot be empty")
	}
	if len(parsed.HTTPMethods) == 0 {
		v.errorf("_shared/control_plane.yaml: http_methods cannot be empty")
	}
	if len(parsed.ScopePatterns) == 0 {
		v.errorf("_shared/control_plane.yaml: scope_patterns cannot be empty")
	}
	if len(parsed.DeploymentProfiles) == 0 {
		v.errorf("_shared/control_plane.yaml: deployment_profiles cannot be empty")
	}

	seenIDs := map[string]string{}
	for _, plane := range parsed.Planes {
		if plane.ID == "" {
			v.errorf("_shared/control_plane.yaml: plane id is required")
			continue
		}
		if previous, exists := seenIDs[plane.ID]; exists {
			v.errorf("_shared/control_plane.yaml: duplicate id %q found in %s and planes", plane.ID, previous)
		}
		seenIDs[plane.ID] = "planes"
		if plane.DefaultDeployMode == "" {
			v.errorf("_shared/control_plane.yaml: plane %q default_deploy_mode is required", plane.ID)
		}
	}
	for _, item := range parsed.DangerLevels {
		if item.ID == "" {
			v.errorf("_shared/control_plane.yaml: danger_levels id is required")
		}
	}
	for _, item := range parsed.ApprovalModes {
		if item.ID == "" {
			v.errorf("_shared/control_plane.yaml: approval_modes id is required")
		}
	}
	for _, item := range parsed.ObjectKinds {
		if item.ID == "" {
			v.errorf("_shared/control_plane.yaml: object_kinds id is required")
		}
	}
	for _, item := range parsed.DeploymentProfiles {
		if item.ID == "" {
			v.errorf("_shared/control_plane.yaml: deployment_profiles id is required")
		}
		if item.PreferredContainerMode == "" {
			v.errorf("_shared/control_plane.yaml: deployment_profile %q preferred_container_mode is required", item.ID)
		}
	}
}

func (v *validator) validatePortalShell(root string) {
	path := filepath.Join(root, "portal_shell.yaml")
	data, ok := v.readYAMLFile(path)
	if !ok {
		return
	}

	var parsed controlPlanePortalShell
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("_control_plane/portal_shell.yaml: parse error: %v", err)
		return
	}
	if parsed.PortalID == "" {
		v.errorf("_control_plane/portal_shell.yaml: portal_id is required")
	}
	if parsed.Title == "" {
		v.errorf("_control_plane/portal_shell.yaml: title is required")
	}
	if parsed.DefaultEnvironment == "" {
		v.errorf("_control_plane/portal_shell.yaml: default_environment is required")
	}
}

func (v *validator) validatePortalMenu(root string) map[string]string {
	path := filepath.Join(root, "portal_menu.yaml")
	data, ok := v.readYAMLFile(path)
	if !ok {
		return map[string]string{}
	}

	var parsed controlPlanePortalMenu
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("_control_plane/portal_menu.yaml: parse error: %v", err)
		return map[string]string{}
	}

	seenMenuIDs := make(map[string]bool)
	seenRoutes := make(map[string]string)
	for _, menu := range parsed.Menus {
		if menu.MenuID == "" {
			v.errorf("_control_plane/portal_menu.yaml: menu_id is required")
			continue
		}
		if seenMenuIDs[menu.MenuID] {
			v.errorf("_control_plane/portal_menu.yaml: duplicate menu_id %q", menu.MenuID)
		}
		seenMenuIDs[menu.MenuID] = true

		if menu.RoutePath == "" {
			v.errorf("_control_plane/portal_menu.yaml: %s route_path is required", menu.MenuID)
		} else {
			if previous, exists := seenRoutes[menu.RoutePath]; exists {
				v.errorf("_control_plane/portal_menu.yaml: duplicate route_path %q used by %s and %s", menu.RoutePath, previous, menu.MenuID)
			}
			seenRoutes[menu.RoutePath] = menu.MenuID
			if !strings.HasPrefix(menu.RoutePath, "/") {
				v.errorf("_control_plane/portal_menu.yaml: %s route_path must start with /", menu.MenuID)
			}
		}

		if menu.PermissionScope == "" {
			v.errorf("_control_plane/portal_menu.yaml: %s permission_scope is required", menu.MenuID)
		}
		if len(menu.ObjectTypes) == 0 {
			v.errorf("_control_plane/portal_menu.yaml: %s object_types cannot be empty", menu.MenuID)
		}
	}
	return seenRoutes
}

func (v *validator) validateControlPlaneDomain(root, domain string, routePaths map[string]string, requireWorkflow bool) {
	baseDir := filepath.Join(root, domain)
	if !fileExists(baseDir) {
		v.errorf("_control_plane/%s: directory is required", domain)
		return
	}

	v.validateControlPlaneFile(filepath.Join(baseDir, "control_plane.yaml"), domain, routePaths)
	v.validateConfigSchemaFile(filepath.Join(baseDir, "config_schema.yaml"), domain)
	if requireWorkflow {
		v.validateWorkflowFile(filepath.Join(baseDir, "workflow.yaml"), domain)
		v.validateAuditSchemaFile(filepath.Join(baseDir, "audit_schema.yaml"), domain)
	}
}

func (v *validator) validateControlPlaneFile(path, domain string, routePaths map[string]string) {
	data, ok := v.readYAMLFile(path)
	if !ok {
		return
	}

	var parsed controlPlaneDefinition
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("%s: parse error: %v", filepath.Base(filepath.Dir(path))+"/control_plane.yaml", err)
		return
	}

	if parsed.Plane == "" {
		v.errorf("%s: plane is required", pathRelative(v.metadataDir, path))
	}
	if parsed.Domain == "" {
		v.errorf("%s: domain is required", pathRelative(v.metadataDir, path))
	}
	if parsed.Dashboard.PrimaryRoute == "" {
		v.errorf("%s: dashboard.primary_route is required", pathRelative(v.metadataDir, path))
	} else if _, exists := routePaths[parsed.Dashboard.PrimaryRoute]; !exists {
		v.errorf("%s: dashboard.primary_route %q not declared in portal_menu.yaml", pathRelative(v.metadataDir, path), parsed.Dashboard.PrimaryRoute)
	}

	for _, obj := range parsed.ObjectTypes {
		if obj.ObjectType == "" {
			v.errorf("%s: object_type is required", pathRelative(v.metadataDir, path))
			continue
		}
		if !isAllowed(obj.RiskLevel, "low", "medium", "high", "critical") {
			v.errorf("%s: %s risk_level %q is invalid", pathRelative(v.metadataDir, path), obj.ObjectType, obj.RiskLevel)
		}
		if !isAllowed(obj.DeploymentProfile, "latency_sensitive", "audit_heavy", "batch_heavy") {
			v.errorf("%s: %s deployment_profile %q is invalid", pathRelative(v.metadataDir, path), obj.ObjectType, obj.DeploymentProfile)
		}
		for _, op := range obj.Operations {
			if op.Operation == "" || op.Method == "" || op.Path == "" {
				v.errorf("%s: %s has incomplete operation declaration", pathRelative(v.metadataDir, path), obj.ObjectType)
				continue
			}
			if len(op.Scopes) == 0 {
				v.errorf("%s: %s/%s scopes cannot be empty", pathRelative(v.metadataDir, path), obj.ObjectType, op.Operation)
			}
			if op.DangerLevel != "" && !isAllowed(op.DangerLevel, "low", "medium", "high", "critical") {
				v.errorf("%s: %s/%s danger_level %q is invalid", pathRelative(v.metadataDir, path), obj.ObjectType, op.Operation, op.DangerLevel)
			}
			if op.ApprovalMode != "" && !isAllowed(op.ApprovalMode, "none", "single", "dual") {
				v.errorf("%s: %s/%s approval_mode %q is invalid", pathRelative(v.metadataDir, path), obj.ObjectType, op.Operation, op.ApprovalMode)
			}
		}
		for _, view := range obj.AnalyticsViews {
			if view.ViewID == "" {
				v.errorf("%s: %s analytics view_id is required", pathRelative(v.metadataDir, path), obj.ObjectType)
			}
			if len(view.WidgetTypes) == 0 {
				v.errorf("%s: %s analytics widget_types cannot be empty", pathRelative(v.metadataDir, path), obj.ObjectType)
			}
			if view.DrilldownRouteID == "" {
				v.errorf("%s: %s analytics drilldown_route_id is required", pathRelative(v.metadataDir, path), obj.ObjectType)
			}
		}
	}

	_ = domain
}

func (v *validator) validateConfigSchemaFile(path, domain string) {
	data, ok := v.readYAMLFile(path)
	if !ok {
		return
	}

	var parsed controlPlaneConfigSchema
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("%s: parse error: %v", pathRelative(v.metadataDir, path), err)
		return
	}

	prefix := "ops."
	if domain == "platform" {
		prefix = "sys."
	}

	for _, cfg := range parsed.Configs {
		if !strings.HasPrefix(cfg.Key, prefix) {
			v.errorf("%s: config key %q must start with %s", pathRelative(v.metadataDir, path), cfg.Key, prefix)
		}
		if !isAllowed(cfg.Scope, "global", "environment", "service", "domain", "audience", "experiment") {
			v.errorf("%s: config %q scope %q is invalid", pathRelative(v.metadataDir, path), cfg.Key, cfg.Scope)
		}
		if !isAllowed(cfg.Reload, "hot", "warm", "restart") {
			v.errorf("%s: config %q reload %q is invalid", pathRelative(v.metadataDir, path), cfg.Key, cfg.Reload)
		}
		if !isAllowed(cfg.Rollout, "none", "progressive", "experiment", "package") {
			v.errorf("%s: config %q rollout %q is invalid", pathRelative(v.metadataDir, path), cfg.Key, cfg.Rollout)
		}
		if !isAllowed(cfg.RiskLevel, "low", "medium", "high", "critical") {
			v.errorf("%s: config %q risk_level %q is invalid", pathRelative(v.metadataDir, path), cfg.Key, cfg.RiskLevel)
		}
	}
}

func (v *validator) validateWorkflowFile(path, _ string) {
	data, ok := v.readYAMLFile(path)
	if !ok {
		return
	}

	var parsed controlPlaneWorkflowSchema
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("%s: parse error: %v", pathRelative(v.metadataDir, path), err)
		return
	}
	for _, workflow := range parsed.Workflows {
		if workflow.WorkflowID == "" {
			v.errorf("%s: workflow_id is required", pathRelative(v.metadataDir, path))
		}
		if workflow.ObjectType == "" {
			v.errorf("%s: workflow %q object_type is required", pathRelative(v.metadataDir, path), workflow.WorkflowID)
		}
		if len(workflow.States) == 0 {
			v.errorf("%s: workflow %q states cannot be empty", pathRelative(v.metadataDir, path), workflow.WorkflowID)
		}
		for _, tr := range workflow.Transitions {
			if tr.From == "" || len(tr.To) == 0 {
				v.errorf("%s: workflow %q has invalid transition", pathRelative(v.metadataDir, path), workflow.WorkflowID)
			}
		}
	}
}

func (v *validator) validateAuditSchemaFile(path, _ string) {
	data, ok := v.readYAMLFile(path)
	if !ok {
		return
	}

	var parsed controlPlaneAuditSchema
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("%s: parse error: %v", pathRelative(v.metadataDir, path), err)
		return
	}
	for _, event := range parsed.Events {
		if event.AuditID == "" {
			v.errorf("%s: audit_id is required", pathRelative(v.metadataDir, path))
		}
		if event.ObjectType == "" {
			v.errorf("%s: audit %q object_type is required", pathRelative(v.metadataDir, path), event.AuditID)
		}
		if !isAllowed(event.DangerLevel, "low", "medium", "high", "critical") {
			v.errorf("%s: audit %q danger_level %q is invalid", pathRelative(v.metadataDir, path), event.AuditID, event.DangerLevel)
		}
		if len(event.RequiredFields) == 0 {
			v.errorf("%s: audit %q required_fields cannot be empty", pathRelative(v.metadataDir, path), event.AuditID)
		}
	}
}

func (v *validator) readYAMLFile(path string) ([]byte, bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		v.errorf("%s: %v", pathRelative(v.metadataDir, path), err)
		return nil, false
	}
	return data, true
}

func isAllowed(value string, allowed ...string) bool {
	for _, item := range allowed {
		if value == item {
			return true
		}
	}
	return false
}

func pathRelative(root, path string) string {
	rel, err := filepath.Rel(root, path)
	if err != nil {
		return path
	}
	return filepath.ToSlash(rel)
}

func sliceToSet(items []string) map[string]bool {
	out := make(map[string]bool, len(items))
	for _, item := range items {
		out[item] = true
	}
	return out
}

func contains(items []string, want string) bool {
	for _, item := range items {
		if item == want {
			return true
		}
	}
	return false
}

func missingItems(actual, required []string) []string {
	actualSet := sliceToSet(actual)
	missing := make([]string, 0)
	for _, item := range required {
		if !actualSet[item] {
			missing = append(missing, item)
		}
	}
	return missing
}

func (v *validator) repoRoot() string {
	if filepath.Base(v.metadataDir) == "metadata" && filepath.Base(filepath.Dir(v.metadataDir)) == "contracts" {
		return filepath.Dir(filepath.Dir(v.metadataDir))
	}
	if filepath.Base(v.metadataDir) == "metadata" {
		return filepath.Dir(v.metadataDir)
	}
	return v.metadataDir
}

func (v *validator) loadSharedEnums() {
	v.enums = make(map[string]bool)

	typesPath := filepath.Join(v.metadataDir, "_shared", "types.yaml")
	data, err := os.ReadFile(typesPath)
	if err != nil {
		v.errorf("_shared/types.yaml: %v", err)
		return
	}

	var parsed struct {
		Enums map[string][]string `yaml:"enums"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("_shared/types.yaml parse error: %v", err)
		return
	}

	for name := range parsed.Enums {
		v.enums[name] = true
	}
	v.enumCount = len(v.enums)
	fmt.Printf("  ✓ _shared/types.yaml: %d enums loaded\n", v.enumCount)
}

func (v *validator) validateBusinessObjects() {
	entries, err := os.ReadDir(v.metadataDir)
	if err != nil {
		v.errorf("cannot read metadata dir: %v", err)
		return
	}

	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), "_") {
			continue
		}
		dir := filepath.Join(v.metadataDir, entry.Name())
		// Domain container: directory without aggregate.yaml/entity.yaml → recurse one level.
		if !fileExists(filepath.Join(dir, "aggregate.yaml")) && !fileExists(filepath.Join(dir, "entity.yaml")) {
			subs, err := os.ReadDir(dir)
			if err != nil {
				v.errorf("cannot read domain dir %s: %v", entry.Name(), err)
				continue
			}
			for _, sub := range subs {
				if !sub.IsDir() || strings.HasPrefix(sub.Name(), "_") {
					continue
				}
				v.validateObjectAt(entry.Name()+"/"+sub.Name(), filepath.Join(dir, sub.Name()))
				v.objectCount++
			}
			continue
		}
		v.validateObject(entry.Name())
		v.objectCount++
	}
}

func (v *validator) validateObject(dirName string) {
	dir := filepath.Join(v.metadataDir, dirName)
	v.validateObjectAt(dirName, dir)
}

func (v *validator) validateObjectAt(dirName, dir string) {
	// Wire JSON / hand-authored fixtures only (no aggregate/entity/service graph).
	if filepath.Base(dir) == "test_fixtures" {
		fmt.Printf("  skip %s/ (fixtures only)\n", dirName)
		return
	}

	fmt.Printf("  checking %s/ ...\n", dirName)

	aggFile := filepath.Join(dir, "aggregate.yaml")
	entFile := filepath.Join(dir, "entity.yaml")
	schemaFile := filepath.Join(dir, "schema.yaml")
	hasAgg := fileExists(aggFile)
	hasEnt := fileExists(entFile)
	hasSchema := fileExists(schemaFile)

	if hasSchema && !hasAgg && !hasEnt {
		v.validateSchemaObject(dirName, schemaFile)
		return
	}

	if !hasAgg && !hasEnt {
		v.errorf("%s: neither aggregate.yaml nor entity.yaml found", dirName)
		return
	}
	if hasAgg && hasEnt {
		v.warnf("%s: both aggregate.yaml and entity.yaml found, using aggregate.yaml", dirName)
	}

	requiredFiles := []string{"fields.yaml", "events.yaml", "storage.yaml", "service.yaml"}
	for _, f := range requiredFiles {
		if !fileExists(filepath.Join(dir, f)) {
			v.errorf("%s: missing required file %s", dirName, f)
		}
	}

	var rootName string
	if hasAgg {
		rootName = v.parseAggRoot(dir, dirName)
	} else {
		rootName = v.parseEntityRoot(dir, dirName)
	}

	fieldsEntities := v.parseFieldsEntities(dir, dirName)
	v.validateEnumRefs(dir, dirName, fieldsEntities)
	v.validateEventsPayload(dir, dirName, fieldsEntities)
	v.validateStorageEntities(dir, dirName, fieldsEntities)
	v.validateServiceEntities(dir, dirName, fieldsEntities)

	_ = rootName
}

func (v *validator) validateSchemaObject(dirName, schemaFile string) {
	data, err := os.ReadFile(schemaFile)
	if err != nil {
		v.errorf("%s/schema.yaml: read error: %v", dirName, err)
		return
	}
	var parsed struct {
		DartClass  string `yaml:"dart_class"`
		OutputPath string `yaml:"output_path"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("%s/schema.yaml: parse error: %v", dirName, err)
		return
	}
	if strings.TrimSpace(parsed.DartClass) == "" {
		v.errorf("%s/schema.yaml: dart_class is required", dirName)
	}
	if strings.TrimSpace(parsed.OutputPath) == "" {
		v.errorf("%s/schema.yaml: output_path is required", dirName)
	}
}

func (v *validator) parseAggRoot(dir, dirName string) string {
	data, err := os.ReadFile(filepath.Join(dir, "aggregate.yaml"))
	if err != nil {
		return ""
	}
	var parsed struct {
		AggregateRoot string `yaml:"aggregate_root"`
		Members       []struct {
			Entity string `yaml:"entity"`
		} `yaml:"members"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("%s/aggregate.yaml: parse error: %v", dirName, err)
		return ""
	}
	if parsed.AggregateRoot == "" {
		v.errorf("%s/aggregate.yaml: aggregate_root is empty", dirName)
	}
	return parsed.AggregateRoot
}

func (v *validator) parseEntityRoot(dir, dirName string) string {
	data, err := os.ReadFile(filepath.Join(dir, "entity.yaml"))
	if err != nil {
		return ""
	}
	var parsed struct {
		EntityName string `yaml:"entity_name"`
		Entity     string `yaml:"entity"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("%s/entity.yaml: parse error: %v", dirName, err)
		return ""
	}
	name := parsed.EntityName
	if name == "" {
		name = parsed.Entity
	}
	if name == "" {
		v.errorf("%s/entity.yaml: entity/entity_name is empty", dirName)
	}
	return name
}

func (v *validator) parseFieldsEntities(dir, dirName string) map[string]bool {
	entities := make(map[string]bool)
	data, err := os.ReadFile(filepath.Join(dir, "fields.yaml"))
	if err != nil {
		return entities
	}

	// Try nested format (aggregates): entities: { Name: { fields: [...] } }
	var nested struct {
		Entities map[string]any `yaml:"entities"`
	}
	if err := yaml.Unmarshal(data, &nested); err != nil {
		v.errorf("%s/fields.yaml: parse error: %v", dirName, err)
		return entities
	}

	if len(nested.Entities) > 0 {
		for name := range nested.Entities {
			entities[name] = true
		}
		return entities
	}

	// Flat format (standalone entities): entity: Name, fields: [...]
	var flat struct {
		Entity string `yaml:"entity"`
	}
	if err := yaml.Unmarshal(data, &flat); err == nil && flat.Entity != "" {
		entities[flat.Entity] = true
	}

	return entities
}

func (v *validator) validateEnumRefs(dir, dirName string, _ map[string]bool) {
	data, err := os.ReadFile(filepath.Join(dir, "fields.yaml"))
	if err != nil {
		return
	}

	var parsed struct {
		Entities map[string]struct {
			Fields []struct {
				Name    string `yaml:"name"`
				Type    string `yaml:"type"`
				EnumRef string `yaml:"enum_ref"`
			} `yaml:"fields"`
		} `yaml:"entities"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}

	for entityName, entity := range parsed.Entities {
		for _, field := range entity.Fields {
			if field.EnumRef != "" && !v.enums[field.EnumRef] {
				v.errorf("%s/fields.yaml: %s.%s references enum %q not defined in _shared/types.yaml",
					dirName, entityName, field.Name, field.EnumRef)
			}
		}
	}
}

func (v *validator) validateEventsPayload(dir, dirName string, fieldsEntities map[string]bool) {
	data, err := os.ReadFile(filepath.Join(dir, "events.yaml"))
	if err != nil {
		return
	}
	var parsed struct {
		Events []struct {
			Name          string `yaml:"name"`
			PayloadEntity string `yaml:"payload_entity"`
		} `yaml:"events"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}

	for _, event := range parsed.Events {
		if event.PayloadEntity != "" && !fieldsEntities[event.PayloadEntity] {
			v.errorf("%s/events.yaml: event %q references payload_entity %q not in fields.yaml",
				dirName, event.Name, event.PayloadEntity)
		}
	}
}

func (v *validator) validateStorageEntities(dir, dirName string, fieldsEntities map[string]bool) {
	data, err := os.ReadFile(filepath.Join(dir, "storage.yaml"))
	if err != nil {
		return
	}
	var parsed struct {
		Tables map[string]struct {
			Entity string `yaml:"entity"`
		} `yaml:"tables"`
		Collections map[string]struct {
			Entity string `yaml:"entity"`
		} `yaml:"collections"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}

	for tableName, table := range parsed.Tables {
		if table.Entity != "" && !fieldsEntities[table.Entity] {
			v.errorf("%s/storage.yaml: table %q references entity %q not in fields.yaml",
				dirName, tableName, table.Entity)
		}
	}
	for collName, coll := range parsed.Collections {
		if coll.Entity != "" && !fieldsEntities[coll.Entity] {
			v.errorf("%s/storage.yaml: collection %q references entity %q not in fields.yaml",
				dirName, collName, coll.Entity)
		}
	}
}

func (v *validator) validateServiceEntities(dir, dirName string, fieldsEntities map[string]bool) {
	data, err := os.ReadFile(filepath.Join(dir, "service.yaml"))
	if err != nil {
		return
	}
	var parsed struct {
		Routes []struct {
			Operations []struct {
				ResponseEntity string `yaml:"response_entity"`
				RequestEntity  string `yaml:"request_entity"`
			} `yaml:"operations"`
		} `yaml:"routes"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}

	for _, route := range parsed.Routes {
		for _, op := range route.Operations {
			if op.ResponseEntity != "" && !fieldsEntities[op.ResponseEntity] {
				v.warnf("%s/service.yaml: operation references response_entity %q not in fields.yaml (may be a list/special type)",
					dirName, op.ResponseEntity)
			}
		}
	}
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
