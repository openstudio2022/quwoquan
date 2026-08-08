package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	metacontrolplane "quwoquan_service/internal/metadata/controlplane"
	"quwoquan_service/internal/metadata/storagecontract"
	"quwoquan_service/internal/metadata/validate"
)

func main() {
	metadataDir := "contracts/metadata"
	if len(os.Args) > 1 {
		metadataDir = os.Args[1]
	}
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		fmt.Fprintf(os.Stderr, "✗ ContractGraph validation failed: %v\n", err)
		os.Exit(1)
	}

	v := &validator{
		metadataDir: metadataDir,
		source:      source,
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
	source      *contractcodegen.Source
	errors      []string
	warnings    []string
	enums       map[string]bool
	objectCount int
	enumCount   int
	// projectionReadModels 是全仓 projections/*.yaml 的 read_model 闭集（跨域），
	// 供 operations.yaml operation 的 response_body 指向性强校验消费。
	projectionReadModels map[string]bool
	// fieldEntities 是全仓 fields.yaml entity 闭集。response_entity 可以引用同一域
	// 其他对象拥有的 wire/read entity，但仍必须存在于 ContractGraph 文档中。
	fieldEntities map[string]bool
}

func (v *validator) errorf(format string, args ...any) {
	v.errors = append(v.errors, fmt.Sprintf(format, args...))
}

func (v *validator) warnf(format string, args ...any) {
	v.warnings = append(v.warnings, fmt.Sprintf(format, args...))
}

func (v *validator) run() {
	if v.source == nil {
		v.errorf("metadata source is required")
		return
	}
	v.loadSharedEnums()
	v.loadProjectionReadModels()
	v.loadFieldEntities()
	v.validateSharedControlPlaneBaseline()
	v.validateControlPlaneMetadata()
	v.validateBusinessObjects()
}

func (v *validator) loadFieldEntities() {
	v.fieldEntities = map[string]bool{}
	for _, documentPath := range v.source.Paths("", "/fields.yaml") {
		data, ok := v.readYAMLFile(filepath.Join(
			v.metadataDir,
			filepath.FromSlash(documentPath),
		))
		if !ok {
			continue
		}
		var parsed struct {
			Entity   string         `yaml:"entity"`
			Entities map[string]any `yaml:"entities"`
			Types    map[string]any `yaml:"types"`
		}
		if err := yaml.Unmarshal(data, &parsed); err != nil {
			v.errorf("%s: parse error: %v", documentPath, err)
			continue
		}
		if strings.TrimSpace(parsed.Entity) != "" {
			v.fieldEntities[strings.TrimSpace(parsed.Entity)] = true
		}
		for name := range parsed.Entities {
			if strings.TrimSpace(name) != "" {
				v.fieldEntities[strings.TrimSpace(name)] = true
			}
		}
		for name := range parsed.Types {
			if strings.TrimSpace(name) != "" {
				v.fieldEntities[strings.TrimSpace(name)] = true
			}
		}
		parts := strings.Split(filepath.ToSlash(documentPath), "/")
		if len(parts) >= 4 {
			v.fieldEntities[pascalCaseMetadataName(parts[len(parts)-2])] = true
		}
	}
	for _, documentPath := range v.source.Paths("", "/schema.yaml") {
		var parsed struct {
			Contract  string `yaml:"contract"`
			DartClass string `yaml:"dart_class"`
		}
		if v.source.Decode(documentPath, &parsed) != nil {
			continue
		}
		if name := strings.TrimSpace(parsed.Contract); name != "" {
			v.fieldEntities[pascalCaseMetadataName(name)] = true
		}
		if name := strings.TrimSpace(parsed.DartClass); name != "" {
			v.fieldEntities[name] = true
			v.fieldEntities[strings.TrimSuffix(name, "Wire")] = true
		}
	}
}

func pascalCaseMetadataName(value string) string {
	parts := strings.FieldsFunc(value, func(r rune) bool { return r == '_' || r == '-' })
	for index, part := range parts {
		if part == "" {
			continue
		}
		parts[index] = strings.ToUpper(part[:1]) + part[1:]
	}
	return strings.Join(parts, "")
}

func (v *validator) validateControlPlaneMetadata() {
	root := filepath.Join(v.metadataDir, "_control_plane")
	if len(v.source.Paths("_control_plane/", ".yaml")) == 0 {
		v.warnf("_control_plane/: not found, skip control plane validation")
		return
	}

	v.validatePortalShell(root)
	routePaths := v.validatePortalMenu(root)
	v.validateControlPlaneDomain(root, "platform", routePaths, false)
	v.validateControlPlaneDomain(root, "product", routePaths, true)
}

func (v *validator) validateSharedControlPlaneBaseline() {
	path := filepath.Join(v.metadataDir, "_shared", "control_plane.yaml")
	data, ok := v.readYAMLFile(path)
	if !ok {
		return
	}

	var parsed sharedControlPlaneDefinition
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("_shared/control_plane.yaml: parse error: %v", err)
		return
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
	if len(parsed.ViewKinds) == 0 {
		v.errorf("_shared/control_plane.yaml: view_kinds cannot be empty")
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
	for _, item := range parsed.ViewKinds {
		if item.ID == "" {
			v.errorf("_shared/control_plane.yaml: view_kinds id is required")
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
	if len(v.source.Paths(pathRelative(v.metadataDir, baseDir)+"/", ".yaml")) == 0 {
		v.errorf("_control_plane/%s: directory is required", domain)
		return
	}

	v.validateControlPlaneFile(filepath.Join(baseDir, "control_plane.yaml"), domain, routePaths)
	configPath := filepath.Join(baseDir, "config.yaml")
	if domain == "platform" {
		configPath = filepath.Join(v.metadataDir, "platform", "config.yaml")
	}
	v.validateConfigSchemaFile(configPath, domain)
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

	var document map[string]any
	if err := yaml.Unmarshal(data, &document); err != nil {
		v.errorf("%s: parse error: %v", filepath.Base(filepath.Dir(path))+"/control_plane.yaml", err)
		return
	}
	if err := metacontrolplane.HydrateOperationReferences(document, v.source.Graph()); err != nil {
		v.errorf("%s: %v", pathRelative(v.metadataDir, path), err)
		return
	}
	resolved, err := yaml.Marshal(document)
	if err != nil {
		v.errorf("%s: resolve operation refs: %v", pathRelative(v.metadataDir, path), err)
		return
	}
	var parsed controlPlaneDefinition
	if err := yaml.Unmarshal(resolved, &parsed); err != nil {
		v.errorf("%s: parse resolved control plane: %v", filepath.Base(filepath.Dir(path))+"/control_plane.yaml", err)
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
			// Control-plane operation_refs may select a canonical authenticated
			// user-plane operation whose principal is public and whose authority is
			// expressed by actor + ownership policy rather than an operator scope.
			// All non-public principals remain scope-bound and fail closed.
			if controlPlaneOperationRequiresScopes(op.Principal) && len(op.Scopes) == 0 {
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

func controlPlaneOperationRequiresScopes(principal string) bool {
	return strings.TrimSpace(principal) != "public"
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
		if !isAllowed(cfg.Scope, "global", "environment", "workload", "service", "domain", "audience", "experiment") {
			v.errorf("%s: config %q scope %q is invalid", pathRelative(v.metadataDir, path), cfg.Key, cfg.Scope)
		}
		if !isAllowed(cfg.Reload, "hot", "warm", "restart") {
			v.errorf("%s: config %q reload %q is invalid", pathRelative(v.metadataDir, path), cfg.Key, cfg.Reload)
		}
		if !isAllowed(cfg.Rollout, "none", "progressive", "experiment", "package") {
			v.errorf("%s: config %q rollout %q is invalid", pathRelative(v.metadataDir, path), cfg.Key, cfg.Rollout)
		}
		if cfg.RiskLevel != "" && !isAllowed(cfg.RiskLevel, "low", "medium", "high", "critical") {
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
	relative, err := v.source.RelativePath(path)
	if err != nil {
		v.errorf("%s: %v", pathRelative(v.metadataDir, path), err)
		return nil, false
	}
	data, err := v.source.Content(relative)
	if err != nil {
		v.errorf("%s: %v", relative, err)
		return nil, false
	}
	return data, true
}

func (v *validator) hasMetadataFile(path string) bool {
	relative, err := v.source.RelativePath(path)
	return err == nil && v.source.Has(relative)
}

func (v *validator) hasMetadataPath(path string) bool {
	relative, err := v.source.RelativePath(path)
	if err != nil {
		return false
	}
	return v.source.Has(relative) ||
		len(v.source.Paths(strings.TrimSuffix(relative, "/")+"/", "")) > 0
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
	data, ok := v.readYAMLFile(typesPath)
	if !ok {
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
	objects := append([]ast.Object{}, v.source.Graph().Objects...)
	sort.Slice(objects, func(i, j int) bool { return objects[i].SourcePath < objects[j].SourcePath })
	for _, object := range objects {
		dirName := filepath.ToSlash(filepath.Dir(object.SourcePath))
		v.validateObjectAt(
			dirName,
			filepath.Join(v.metadataDir, filepath.FromSlash(dirName)),
			object.Name,
			string(object.Kind),
		)
		v.objectCount++
	}
}

func (v *validator) validateObjectAt(dirName, dir, rootName, objectKind string) {
	fmt.Printf("  checking %s/ ...\n", dirName)

	if !v.hasMetadataFile(filepath.Join(dir, "object.yaml")) {
		v.errorf("%s: object.yaml is required", dirName)
		return
	}
	requiredFiles := requiredFilesForObjectKind(objectKind)
	for _, f := range requiredFiles {
		if !v.hasMetadataFile(filepath.Join(dir, f)) {
			v.errorf("%s: missing required file %s", dirName, f)
		}
	}

	fieldsEntities := map[string]bool{}
	if v.hasMetadataFile(filepath.Join(dir, "fields.yaml")) {
		fieldsEntities = v.parseFieldsEntities(dir, dirName, rootName)
		v.validateEnumRefs(dir, dirName, fieldsEntities)
	}
	if v.hasMetadataFile(filepath.Join(dir, "operations.yaml")) {
		v.validateServiceEntities(dir, dirName, rootName, fieldsEntities)
	}
}

func requiredFilesForObjectKind(objectKind string) []string {
	switch objectKind {
	case "external_reference":
		return nil
	default:
		return []string{"fields.yaml", "storage.yaml"}
	}
}

func (v *validator) validateSchemaObject(dirName, schemaFile string) {
	data, ok := v.readYAMLFile(schemaFile)
	if !ok {
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

func (v *validator) parseFieldsEntities(dir, dirName, rootName string) map[string]bool {
	entities := make(map[string]bool)
	data, ok := v.readYAMLFile(filepath.Join(dir, "fields.yaml"))
	if !ok {
		return entities
	}

	// Try nested format (aggregates): entities: { Name: { fields: [...] } }
	var nested struct {
		Entities map[string]any `yaml:"entities"`
		Members  map[string]any `yaml:"members"`
		Types    map[string]any `yaml:"types"`
	}
	if err := yaml.Unmarshal(data, &nested); err != nil {
		v.errorf("%s/fields.yaml: parse error: %v", dirName, err)
		return entities
	}

	if len(nested.Entities) > 0 {
		for name := range nested.Entities {
			entities[name] = true
		}
	}
	for name := range nested.Members {
		entities[name] = true
	}
	for name := range nested.Types {
		entities[name] = true
	}
	if strings.TrimSpace(rootName) != "" {
		entities[rootName] = true
	}

	// Flat roots may legitimately own nested entities in the same fields packet.
	// Always register the top-level entity as well as the nested entity map.
	var flat struct {
		Entity string `yaml:"entity"`
	}
	if err := yaml.Unmarshal(data, &flat); err == nil && flat.Entity != "" {
		entities[flat.Entity] = true
	}

	return entities
}

func (v *validator) validateEnumRefs(dir, dirName string, _ map[string]bool) {
	data, ok := v.readYAMLFile(filepath.Join(dir, "fields.yaml"))
	if !ok {
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
	data, ok := v.readYAMLFile(filepath.Join(dir, "events.yaml"))
	if !ok {
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
	data, ok := v.readYAMLFile(filepath.Join(dir, "storage.yaml"))
	if !ok {
		return
	}
	parsed, err := storagecontract.DecodeYAML(data)
	if err != nil {
		v.errorf("%s/storage.yaml: decode canonical storage document: %v", dirName, err)
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

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
