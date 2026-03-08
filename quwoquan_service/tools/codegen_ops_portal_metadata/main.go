package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

type portalShellFile struct {
	Version               int                        `yaml:"version,omitempty" json:"version,omitempty"`
	PortalID              string                     `yaml:"portal_id" json:"portal_id"`
	Title                 string                     `yaml:"title" json:"title"`
	DefaultEnvironment    string                     `yaml:"default_environment" json:"default_environment"`
	SupportedEnvironments []string                   `yaml:"supported_environments" json:"supported_environments"`
	DefaultDomain         string                     `yaml:"default_domain" json:"default_domain"`
	Domains               []namedIconItem            `yaml:"domains" json:"domains"`
	GlobalSearch          globalSearch               `yaml:"global_search" json:"global_search"`
	NotificationChannels  []string                   `yaml:"notification_channels" json:"notification_channels"`
	WorkbenchViews        []namedLabelItem           `yaml:"workbench_views" json:"workbench_views"`
	ContextSwitchers      []string                   `yaml:"context_switchers" json:"context_switchers"`
	DashboardDefaults     map[string]dashboardConfig `yaml:"dashboard_defaults" json:"dashboard_defaults"`
}

type namedIconItem struct {
	ID    string `yaml:"id" json:"id"`
	Label string `yaml:"label" json:"label"`
	Icon  string `yaml:"icon" json:"icon"`
}

type namedLabelItem struct {
	ID    string `yaml:"id" json:"id"`
	Label string `yaml:"label" json:"label"`
}

type globalSearch struct {
	Enabled     bool     `yaml:"enabled" json:"enabled"`
	Placeholder string   `yaml:"placeholder" json:"placeholder"`
	ObjectTypes []string `yaml:"object_types" json:"object_types"`
}

type dashboardConfig struct {
	KPIs   []string `yaml:"kpis" json:"kpis"`
	Charts []string `yaml:"charts" json:"charts"`
}

type portalMenuFile struct {
	Version int              `yaml:"version,omitempty" json:"version,omitempty"`
	Menus   []portalMenuItem `yaml:"menus" json:"menus"`
}

type portalMenuItem struct {
	MenuID          string   `yaml:"menu_id" json:"menu_id"`
	ParentMenuID    string   `yaml:"parent_menu_id,omitempty" json:"parent_menu_id,omitempty"`
	Label           string   `yaml:"label" json:"label"`
	Domain          string   `yaml:"domain" json:"domain"`
	RoutePath       string   `yaml:"route_path" json:"route_path"`
	Icon            string   `yaml:"icon" json:"icon"`
	Order           int      `yaml:"order" json:"order"`
	PermissionScope string   `yaml:"permission_scope" json:"permission_scope"`
	ObjectTypes     []string `yaml:"object_types" json:"object_types"`
}

type controlPlaneFile struct {
	Version     int                `yaml:"version,omitempty" json:"version,omitempty"`
	Plane       string             `yaml:"plane" json:"plane"`
	Domain      string             `yaml:"domain" json:"domain"`
	Dashboard   controlDashboard   `yaml:"dashboard" json:"dashboard"`
	ObjectTypes []controlPlaneType `yaml:"object_types" json:"object_types"`
}

type controlDashboard struct {
	PrimaryRoute string   `yaml:"primary_route" json:"primary_route"`
	Widgets      []string `yaml:"widgets" json:"widgets"`
}

type controlPlaneType struct {
	ObjectKind        string             `yaml:"object_kind,omitempty" json:"object_kind,omitempty"`
	ObjectType        string             `yaml:"object_type" json:"object_type"`
	Label             string             `yaml:"label" json:"label"`
	SourceEntity      string             `yaml:"source_entity" json:"source_entity"`
	ViewModel         string             `yaml:"view_model" json:"view_model"`
	RiskLevel         string             `yaml:"risk_level" json:"risk_level"`
	DeploymentProfile string             `yaml:"deployment_profile" json:"deployment_profile"`
	Operations        []controlOperation `yaml:"operations" json:"operations"`
	AnalyticsViews    []analyticsView    `yaml:"analytics_views,omitempty" json:"analytics_views,omitempty"`
}

type analyticsView struct {
	ViewID           string   `yaml:"view_id" json:"view_id"`
	WidgetTypes      []string `yaml:"widget_types" json:"widget_types"`
	DrilldownRouteID string   `yaml:"drilldown_route_id" json:"drilldown_route_id"`
}

type controlOperation struct {
	Operation    string   `yaml:"operation" json:"operation"`
	Method       string   `yaml:"method" json:"method"`
	Path         string   `yaml:"path" json:"path"`
	Scopes       []string `yaml:"scopes" json:"scopes"`
	DangerLevel  string   `yaml:"danger_level,omitempty" json:"danger_level,omitempty"`
	ApprovalMode string   `yaml:"approval_mode,omitempty" json:"approval_mode,omitempty"`
}

type workflowFile struct {
	Version   int           `yaml:"version,omitempty" json:"version,omitempty"`
	Workflows []workflowDef `yaml:"workflows" json:"workflows"`
}

type workflowDef struct {
	WorkflowID           string               `yaml:"workflow_id" json:"workflow_id"`
	ObjectType           string               `yaml:"object_type" json:"object_type"`
	States               []string             `yaml:"states" json:"states"`
	Transitions          []workflowTransition `yaml:"transitions" json:"transitions"`
	ApprovalRequirements map[string]any       `yaml:"approval_requirements,omitempty" json:"approval_requirements,omitempty"`
	SLAPolicy            map[string]any       `yaml:"sla_policy,omitempty" json:"sla_policy,omitempty"`
	EvidenceRequirements map[string]any       `yaml:"evidence_requirements,omitempty" json:"evidence_requirements,omitempty"`
}

type workflowTransition struct {
	From string   `yaml:"from" json:"from"`
	To   []string `yaml:"to" json:"to"`
}

type auditSchemaFile struct {
	Version int          `yaml:"version,omitempty" json:"version,omitempty"`
	Events  []auditEvent `yaml:"events" json:"events"`
}

type auditEvent struct {
	AuditID        string   `yaml:"audit_id" json:"audit_id"`
	Label          string   `yaml:"label" json:"label"`
	ObjectType     string   `yaml:"object_type" json:"object_type"`
	DangerLevel    string   `yaml:"danger_level" json:"danger_level"`
	RequiredFields []string `yaml:"required_fields" json:"required_fields"`
}

type configSchemaFile struct {
	Version int          `yaml:"version,omitempty" json:"version,omitempty"`
	Configs []configItem `yaml:"configs" json:"configs"`
}

type configItem struct {
	Key        string      `yaml:"key" json:"key"`
	Type       string      `yaml:"type" json:"type"`
	Owner      string      `yaml:"owner" json:"owner"`
	Default    interface{} `yaml:"default" json:"default"`
	Scope      string      `yaml:"scope" json:"scope"`
	Reload     string      `yaml:"reload" json:"reload"`
	Rollout    string      `yaml:"rollout" json:"rollout"`
	RiskLevel  string      `yaml:"risk_level" json:"risk_level"`
	UIEditable bool        `yaml:"ui_editable" json:"ui_editable"`
}

func main() {
	var metadataDir string
	var portalDir string

	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&portalDir, "portal-dir", "../apps/ops-portal", "ops portal root directory")
	flag.Parse()

	controlPlaneRoot := filepath.Join(metadataDir, "_control_plane")
	outDir := filepath.Join(portalDir, "src", "generated", "control-plane")
	must(os.MkdirAll(outDir, 0o755))

	shell := readYAML[portalShellFile](filepath.Join(controlPlaneRoot, "portal_shell.yaml"))
	menu := readYAML[portalMenuFile](filepath.Join(controlPlaneRoot, "portal_menu.yaml"))
	writeTSModule(filepath.Join(outDir, "portalShell.generated.ts"), "portalShell", shell)
	writeTSModule(filepath.Join(outDir, "portalMenu.generated.ts"), "portalMenu", menu)

	indexExports := []string{
		"export * from './portalShell.generated';",
		"export * from './portalMenu.generated';",
	}
	if fileExists(filepath.Join(controlPlaneRoot, "domain_onboarding_schema.yaml")) {
		schema := readYAML[map[string]any](filepath.Join(controlPlaneRoot, "domain_onboarding_schema.yaml"))
		writeTSModule(filepath.Join(outDir, "domainOnboardingSchema.generated.ts"), "domainOnboardingSchema", schema)
		indexExports = append(indexExports, "export * from './domainOnboardingSchema.generated';")
	}
	if fileExists(filepath.Join(controlPlaneRoot, "domains")) {
		domains := readOnboardingDomains(filepath.Join(controlPlaneRoot, "domains"))
		writeTSModule(filepath.Join(outDir, "domainOnboardingDomains.generated.ts"), "domainOnboardingDomains", domains)
		indexExports = append(indexExports, "export * from './domainOnboardingDomains.generated';")
	}

	for _, domain := range []string{"product", "platform"} {
		baseDir := filepath.Join(controlPlaneRoot, domain)
		if !fileExists(baseDir) {
			continue
		}

		if fileExists(filepath.Join(baseDir, "control_plane.yaml")) {
			data := readYAML[controlPlaneFile](filepath.Join(baseDir, "control_plane.yaml"))
			writeTSModule(filepath.Join(outDir, fmt.Sprintf("%sControlPlane.generated.ts", domain)), domain+"ControlPlane", data)
			indexExports = append(indexExports, fmt.Sprintf("export * from './%sControlPlane.generated';", domain))
		}

		if fileExists(filepath.Join(baseDir, "workflow.yaml")) {
			data := readYAML[workflowFile](filepath.Join(baseDir, "workflow.yaml"))
			writeTSModule(filepath.Join(outDir, fmt.Sprintf("%sWorkflow.generated.ts", domain)), domain+"Workflow", data)
			indexExports = append(indexExports, fmt.Sprintf("export * from './%sWorkflow.generated';", domain))
		}

		if fileExists(filepath.Join(baseDir, "audit_schema.yaml")) {
			data := readYAML[auditSchemaFile](filepath.Join(baseDir, "audit_schema.yaml"))
			writeTSModule(filepath.Join(outDir, fmt.Sprintf("%sAudit.generated.ts", domain)), domain+"AuditSchema", data)
			indexExports = append(indexExports, fmt.Sprintf("export * from './%sAudit.generated';", domain))
		}

		if fileExists(filepath.Join(baseDir, "config_schema.yaml")) {
			data := readYAML[configSchemaFile](filepath.Join(baseDir, "config_schema.yaml"))
			writeTSModule(filepath.Join(outDir, fmt.Sprintf("%sConfig.generated.ts", domain)), domain+"ConfigSchema", data)
			indexExports = append(indexExports, fmt.Sprintf("export * from './%sConfig.generated';", domain))
		}
	}

	sort.Strings(indexExports)
	writeFile(filepath.Join(outDir, "index.ts"), strings.Join(indexExports, "\n")+"\n")
}

func readYAML[T any](path string) T {
	data, err := os.ReadFile(path)
	must(err)

	var out T
	must(yaml.Unmarshal(data, &out))
	return out
}

func readOnboardingDomains(dir string) map[string]any {
	entries, err := os.ReadDir(dir)
	must(err)

	out := map[string]any{}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".yaml") {
			continue
		}
		path := filepath.Join(dir, entry.Name())
		data := readYAML[map[string]any](path)
		domain := fmt.Sprint(data["domain"])
		if strings.TrimSpace(domain) == "" {
			domain = strings.TrimSuffix(entry.Name(), filepath.Ext(entry.Name()))
		}
		out[domain] = data
	}
	return out
}

func writeTSModule(path, varName string, data interface{}) {
	payload, err := json.MarshalIndent(data, "", "  ")
	must(err)

	content := fmt.Sprintf("// Code generated by codegen_ops_portal_metadata. DO NOT EDIT.\n\nexport const %s = %s as const;\nexport type %s = typeof %s;\n",
		varName, string(payload), toPascalCase(varName), varName)
	writeFile(path, content)
}

func writeFile(path, content string) {
	must(os.MkdirAll(filepath.Dir(path), 0o755))
	must(os.WriteFile(path, []byte(content), 0o644))
	fmt.Printf("generated: %s\n", path)
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir() || err == nil
}

func toPascalCase(s string) string {
	parts := strings.FieldsFunc(s, func(r rune) bool {
		return r == '-' || r == '_' || r == '.'
	})
	if len(parts) == 0 {
		parts = []string{s}
	}
	var out strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		out.WriteString(strings.ToUpper(part[:1]))
		if len(part) > 1 {
			out.WriteString(part[1:])
		}
	}
	return out.String()
}

func must(err error) {
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}
