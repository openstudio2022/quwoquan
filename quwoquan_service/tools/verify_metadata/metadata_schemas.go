package main

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
			Current    string `yaml:"current"`
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
		PlaneBindingDomain   string `yaml:"plane_binding_domain"`
		PlaneBindingSource   string `yaml:"plane_binding_source"`
		CurrentBindingSource string `yaml:"current_binding_source"`
	} `yaml:"deployment"`
	Replication struct {
		SourceTemplate  string   `yaml:"source_template"`
		NextCopyTargets []string `yaml:"next_copy_targets"`
		CopyNotes       []string `yaml:"copy_notes"`
	} `yaml:"replication"`
	BlockingGaps []string `yaml:"blocking_gaps"`
}
