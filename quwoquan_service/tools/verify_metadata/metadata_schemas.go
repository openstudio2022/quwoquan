package main

type sharedControlPlaneDefinition struct {
	Planes []struct {
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
	ViewKinds []struct {
		ID string `yaml:"id"`
	} `yaml:"view_kinds"`
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
			AuthMode     string   `yaml:"auth_mode"`
			Principal    string   `yaml:"principal"`
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
