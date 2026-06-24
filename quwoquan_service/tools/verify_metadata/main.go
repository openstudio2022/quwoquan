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
	// projectionReadModels 是全仓 projections/*.yaml 的 read_model 闭集（跨域），
	// 供 service.yaml operation 的 response_body 指向性强校验消费。
	projectionReadModels map[string]bool
}

func (v *validator) errorf(format string, args ...any) {
	v.errors = append(v.errors, fmt.Sprintf(format, args...))
}

func (v *validator) warnf(format string, args ...any) {
	v.warnings = append(v.warnings, fmt.Sprintf(format, args...))
}

func (v *validator) run() {
	v.loadSharedEnums()
	v.loadProjectionReadModels()
	v.validateSharedControlPlaneBaseline()
	v.validateControlPlaneMetadata()
	v.validateDomainOnboardingMetadata()
	v.validateBusinessObjects()
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

// responseBodyKinds 是 operation 响应体形态闭集：
//
//	object = 单读模型对象；page = 分页/列表（items 承载读模型）；ack = 仅状态确认（无读模型）。
var responseBodyKinds = map[string]bool{"object": true, "page": true, "ack": true}

func (v *validator) validateServiceEntities(dir, dirName string, fieldsEntities map[string]bool) {
	data, err := os.ReadFile(filepath.Join(dir, "service.yaml"))
	if err != nil {
		return
	}
	// service.yaml 真实结构是顶层扁平 api_routes（历史 routes/operations 嵌套从未落地，
	// 旧解析对现网文件恒为空转）；这里按真实结构解析并对响应契约做强校验。
	var parsed struct {
		APIRoutes []struct {
			Operation        string `yaml:"operation"`
			ResponseEntity   string `yaml:"response_entity"`
			RequestEntity    string `yaml:"request_entity"`
			ResponseBody     string `yaml:"response_body"`
			ResponseBodyKind string `yaml:"response_body_kind"`
		} `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}

	for _, op := range parsed.APIRoutes {
		opName := strings.TrimSpace(op.Operation)
		// response_entity 既可指向 fields.yaml entity，也可指向 projection read_model（如各类 *View/*Summary）。
		if op.ResponseEntity != "" && !fieldsEntities[op.ResponseEntity] && !v.projectionReadModels[op.ResponseEntity] {
			v.warnf("%s/service.yaml: operation %q references response_entity %q not in fields.yaml nor any projection read_model",
				dirName, opName, op.ResponseEntity)
		}

		body := strings.TrimSpace(op.ResponseBody)
		kind := strings.TrimSpace(op.ResponseBodyKind)
		// response_body / response_body_kind 为可选的框架级响应契约；一旦任一出现即强校验配对与指向。
		if body == "" && kind == "" {
			continue
		}
		if kind == "" {
			v.errorf("%s/service.yaml: operation %q declares response_body %q but missing response_body_kind (object|page|ack)",
				dirName, opName, body)
			continue
		}
		if !responseBodyKinds[kind] {
			v.errorf("%s/service.yaml: operation %q has invalid response_body_kind %q (allowed: object|page|ack)",
				dirName, opName, kind)
			continue
		}
		if kind == "ack" {
			if body != "" {
				v.errorf("%s/service.yaml: operation %q response_body_kind=ack must not declare response_body (got %q)",
					dirName, opName, body)
			}
			continue
		}
		// object | page 必须指向存在的 projection read_model（或 client_projection.dart_class）。
		if body == "" {
			v.errorf("%s/service.yaml: operation %q response_body_kind=%s requires a response_body read model reference",
				dirName, opName, kind)
			continue
		}
		if !v.projectionReadModels[body] {
			v.errorf("%s/service.yaml: operation %q response_body %q is not a known projection read_model",
				dirName, opName, body)
		}
	}
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
