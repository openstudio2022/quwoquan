package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

// generateAssistantCloudApiWireDart emits strongly-typed AssistantRepository wire views from
// every assistant aggregate and projection consumed by the App.
func generateAssistantCloudApiWireDart(metadataDir, appDir string) error {
	path := filepath.Join(metadataDir, "assistant", "assistant", "assistant_run", "fields.yaml")
	ff, err := readFields(path)
	if err != nil {
		return err
	}
	enumCatalog, err := readAssistantEnumCatalog(filepath.Join(
		metadataDir,
		"assistant",
		"_shared",
		"enums.yaml",
	))
	if err != nil {
		return err
	}
	svc, err := readService(filepath.Join(metadataDir, "assistant", "assistant", "assistant_run", "operations.yaml"))
	if err != nil {
		return err
	}
	for _, relativePath := range []string{
		"assistant/assistant/assistant_learning_fact/fields.yaml",
		"assistant/assistant/assistant_preference_fact/fields.yaml",
	} {
		additional, readErr := readFields(filepath.Join(metadataDir, relativePath))
		if readErr != nil {
			return readErr
		}
		for name, entity := range additional.Entities {
			if _, exists := ff.Entities[name]; exists {
				return fmt.Errorf("assistant wire entity %q declared more than once", name)
			}
			ff.Entities[name] = entity
		}
	}
	conversationFields, err := readFields(filepath.Join(
		metadataDir,
		"assistant",
		"assistant",
		"assistant_conversation",
		"fields.yaml",
	))
	if err != nil {
		return err
	}
	const createConversationRequest = "AssistantCreateConversationRequest"
	requestEntity, exists := conversationFields.Entities[createConversationRequest]
	if !exists {
		return fmt.Errorf(
			"assistant conversation metadata is missing %s",
			createConversationRequest,
		)
	}
	if _, exists := ff.Entities[createConversationRequest]; exists {
		return fmt.Errorf(
			"assistant wire entity %q declared more than once",
			createConversationRequest,
		)
	}
	ff.Entities[createConversationRequest] = requestEntity
	preferenceService, err := readService(filepath.Join(
		metadataDir,
		"assistant",
		"assistant",
		"assistant_preference_fact",
		"operations.yaml",
	))
	if err != nil {
		return err
	}
	svc.APIRoutes = append(svc.APIRoutes, preferenceService.APIRoutes...)
	learningService, err := readService(filepath.Join(
		metadataDir,
		"assistant",
		"assistant",
		"assistant_learning_fact",
		"operations.yaml",
	))
	if err != nil {
		return err
	}
	svc.APIRoutes = append(svc.APIRoutes, learningService.APIRoutes...)
	conversationService, err := readService(filepath.Join(
		metadataDir,
		"assistant",
		"assistant",
		"assistant_conversation",
		"operations.yaml",
	))
	if err != nil {
		return err
	}
	foundCreateConversation := false
	for _, route := range conversationService.APIRoutes {
		if route.Operation != "CreateAssistantConversation" {
			continue
		}
		svc.APIRoutes = append(svc.APIRoutes, route)
		foundCreateConversation = true
		break
	}
	if !foundCreateConversation {
		return fmt.Errorf(
			"assistant conversation metadata is missing CreateAssistantConversation route",
		)
	}
	names := collectAssistantWireEntities(ff, svc)
	out := renderAssistantCloudApiWireDart(ff, names, enumCatalog)
	outPath := filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "assistant", "assistant_cloud_api_wire.g.dart")
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}
	writeFile(outPath, out)
	return nil
}

func collectAssistantWireEntities(ff *fieldsFile, svc *serviceFile) []string {
	seen := map[string]bool{}
	var names []string
	add := func(name string) {
		name = strings.TrimSpace(name)
		if name == "" {
			return
		}
		if !seen[name] {
			seen[name] = true
			names = append(names, name)
		}
	}
	for _, route := range svc.APIRoutes {
		add(route.RequestEntity)
		add(route.ResponseEntity)
	}
	expanded := map[string]bool{}
	var visit func(string)
	visit = func(name string) {
		name = strings.TrimSpace(name)
		if name == "" || expanded[name] {
			return
		}
		ent, ok := ff.Entities[name]
		if !ok {
			return
		}
		expanded[name] = true
		for _, field := range ent.Fields {
			inner, ok := assistantWireListElementType(field.Type)
			if ok {
				if _, exists := ff.Entities[inner]; exists {
					add(inner)
					visit(inner)
				}
				continue
			}
			fieldType := strings.TrimSpace(field.Type)
			if _, exists := ff.Entities[fieldType]; exists {
				add(fieldType)
				visit(fieldType)
			}
		}
	}
	for _, name := range append([]string(nil), names...) {
		visit(name)
	}
	sort.Strings(names)
	return names
}

func renderAssistantCloudApiWireDart(
	ff *fieldsFile,
	entityNames []string,
	enumCatalog *assistantEnumCatalog,
) string {
	deps := map[string]map[string]bool{}
	for _, n := range entityNames {
		deps[n] = map[string]bool{}
		ent, ok := ff.Entities[n]
		if !ok {
			continue
		}
		for _, f := range ent.Fields {
			if _, isEnt := ff.Entities[strings.TrimSpace(f.Type)]; isEnt {
				deps[n][strings.TrimSpace(f.Type)] = true
			}
			inner, ok := assistantWireListElementType(f.Type)
			if ok && containsString(entityNames, inner) {
				deps[n][inner] = true
			}
		}
	}
	order := assistantWireTopoEntityOrder(entityNames, deps)

	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from assistant metadata fields. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors, unnecessary_null_in_if_null_operators\n\n")
	b.WriteString(renderAssistantCloudWireEnumsDart(enumCatalog))

	for _, name := range order {
		ent, ok := ff.Entities[name]
		if !ok {
			continue
		}
		assistantWireEmitEntityDart(&b, ff, enumCatalog, name, ent)
		b.WriteString("\n")
	}

	return b.String()
}

func renderAssistantCloudWireEnumsDart(catalog *assistantEnumCatalog) string {
	if catalog == nil || len(catalog.Enums) == 0 {
		return ""
	}
	return "import 'assistant_runtime_enums.g.dart';\n\n"
}

func assistantWireHasEnum(catalog *assistantEnumCatalog, name string) bool {
	if catalog == nil {
		return false
	}
	for _, enum := range catalog.Enums {
		if enum.Name == strings.TrimSpace(name) {
			return true
		}
	}
	return false
}

func containsString(slice []string, s string) bool {
	for _, x := range slice {
		if x == s {
			return true
		}
	}
	return false
}

var assistantWireListTypeRe = regexp.MustCompile(`^\[\](.+)$`)

func assistantWireListElementType(t string) (string, bool) {
	t = strings.TrimSpace(t)
	m := assistantWireListTypeRe.FindStringSubmatch(t)
	if m == nil {
		return "", false
	}
	return strings.TrimSpace(m[1]), true
}

func assistantWireTopoEntityOrder(names []string, deps map[string]map[string]bool) []string {
	seen := map[string]bool{}
	var order []string
	var visit func(n string)
	visit = func(n string) {
		if seen[n] {
			return
		}
		seen[n] = true
		dependencyNames := make([]string, 0, len(deps[n]))
		for d := range deps[n] {
			dependencyNames = append(dependencyNames, d)
		}
		sort.Strings(dependencyNames)
		for _, d := range dependencyNames {
			if containsString(names, d) {
				visit(d)
			}
		}
		order = append(order, n)
	}
	for _, n := range names {
		visit(n)
	}
	return order
}

func assistantWireFieldNullable(f fieldDef) bool {
	for _, c := range f.Constraints {
		if c == "NOT_NULL" || c == "PK" {
			return false
		}
	}
	for _, c := range f.Constraints {
		if c == "NULLABLE" {
			return true
		}
	}
	return true
}

func assistantWireDartType(
	ff *fieldsFile,
	enumCatalog *assistantEnumCatalog,
	f fieldDef,
	nullable bool,
) string {
	t := strings.TrimSpace(f.Type)
	if t == "enum" && assistantWireHasEnum(enumCatalog, f.EnumRef) {
		if nullable {
			return f.EnumRef + "?"
		}
		return f.EnumRef
	}
	if _, isEnt := ff.Entities[t]; isEnt {
		if nullable {
			return t + "?"
		}
		return t
	}
	if inner, ok := assistantWireListElementType(t); ok {
		if _, isEnt := ff.Entities[inner]; isEnt {
			if nullable {
				return "List<" + inner + ">?"
			}
			return "List<" + inner + ">"
		}
		switch inner {
		case "string":
			if nullable {
				return "List<String>?"
			}
			return "List<String>"
		case "object":
			if nullable {
				return "List<Map<String, dynamic>>?"
			}
			return "List<Map<String, dynamic>>"
		default:
			if nullable {
				return "List<dynamic>?"
			}
			return "List<dynamic>"
		}
	}
	switch t {
	case "string":
		if nullable {
			return "String?"
		}
		return "String"
	case "bool":
		if nullable {
			return "bool?"
		}
		return "bool"
	case "int", "int64":
		if nullable {
			return "int?"
		}
		return "int"
	case "float":
		if nullable {
			return "double?"
		}
		return "double"
	case "datetime":
		if nullable {
			return "DateTime?"
		}
		return "DateTime"
	case "timestamp":
		return "String?"
	case "object", "jsonb":
		if nullable {
			return "Map<String, dynamic>?"
		}
		return "Map<String, dynamic>"
	case "enum":
		return "String?"
	default:
		return "dynamic"
	}
}

func assistantWireEmitEntityDart(
	b *strings.Builder,
	ff *fieldsFile,
	enumCatalog *assistantEnumCatalog,
	name string,
	ent entityDef,
) {
	fmt.Fprintf(b, "class %s {\n", name)
	fmt.Fprintf(b, "  const %s({\n", name)
	for _, f := range ent.Fields {
		nul := assistantWireFieldNullable(f)
		if nul {
			if inner, ok := assistantWireListElementType(f.Type); ok {
				if _, isEnt := ff.Entities[inner]; isEnt {
					fmt.Fprintf(b, "    this.%s = const [],\n", f.Name)
					continue
				}
				if inner == "string" {
					fmt.Fprintf(b, "    this.%s = const [],\n", f.Name)
					continue
				}
				if inner == "object" {
					if !nul {
						fmt.Fprintf(b, "    this.%s = const [],\n", f.Name)
					} else {
						fmt.Fprintf(b, "    this.%s,\n", f.Name)
					}
					continue
				}
			}
			fmt.Fprintf(b, "    this.%s,\n", f.Name)
		} else {
			fmt.Fprintf(b, "    required this.%s,\n", f.Name)
		}
	}
	b.WriteString("  });\n\n")
	for _, f := range ent.Fields {
		nul := assistantWireFieldNullable(f)
		dt := assistantWireDartType(ff, enumCatalog, f, nul)
		fmt.Fprintf(b, "  final %s %s;\n", dt, f.Name)
	}
	b.WriteString("\n")
	fmt.Fprintf(b, "  factory %s.fromJson(Map<String, dynamic> json) {\n", name)
	fmt.Fprintf(b, "    return %s(\n", name)
	for _, f := range ent.Fields {
		fmt.Fprintf(
			b,
			"      %s: %s,\n",
			f.Name,
			assistantWireFromJsonExpr(ff, enumCatalog, name, f),
		)
	}
	b.WriteString("    );\n  }\n\n")
	fmt.Fprintf(b, "  Map<String, dynamic> toJson() => <String, dynamic>{\n")
	for _, f := range ent.Fields {
		fmt.Fprintf(
			b,
			"        '%s': %s,\n",
			f.Name,
			assistantWireToJsonExpr(ff, enumCatalog, f),
		)
	}
	b.WriteString("      };\n")

	if name == "AssistantUserTaskView" {
		b.WriteString(`
  /// 兼容旧 UI 使用的 ` + "`title` / `desc`" + ` Map。
  Map<String, dynamic> toScheduleRowMap() => <String, dynamic>{
        'title': title,
        'desc': description ?? '',
      };
`)
	}
	b.WriteString("}\n")
}

func assistantWireFromJsonExpr(
	ff *fieldsFile,
	enumCatalog *assistantEnumCatalog,
	entityName string,
	f fieldDef,
) string {
	n := f.Name
	nul := assistantWireFieldNullable(f)
	t := strings.TrimSpace(f.Type)

	if t == "enum" && assistantWireHasEnum(enumCatalog, f.EnumRef) {
		if nul {
			return fmt.Sprintf(
				"json['%s'] == null ? null : parse%sStrict(json['%s'].toString())",
				n,
				f.EnumRef,
				n,
			)
		}
		return fmt.Sprintf("parse%sStrict((json['%s'] ?? '').toString())", f.EnumRef, n)
	}

	if _, isEnt := ff.Entities[t]; isEnt {
		if nul {
			return fmt.Sprintf(`(json['%s'] as Map?) == null
          ? null
          : %s.fromJson((json['%s'] as Map).cast<String, dynamic>())`, n, t, n)
		}
		return fmt.Sprintf(`%s.fromJson(((json['%s'] as Map?) ?? const <String, dynamic>{}).cast<String, dynamic>())`, t, n)
	}

	if inner, ok := assistantWireListElementType(t); ok {
		if _, isEnt := ff.Entities[inner]; isEnt {
			if entityName == "AssistantSearchResultView" && n == "citations" {
				return `((json['citations'] as List?) ?? const [])
            .whereType<Map>()
            .map((item) => AssistantSearchCitationView.fromJson(item.cast<String, dynamic>()))
            .where((item) => item.citationId.isNotEmpty || item.title.isNotEmpty)
            .toList(growable: false)`
			}
			return fmt.Sprintf(`((json['%s'] as List?) ?? const [])
            .whereType<Map>()
            .map((item) => %s.fromJson(item.cast<String, dynamic>()))
            .toList(growable: false)`, n, inner)
		}
		if inner == "string" {
			return fmt.Sprintf(`((json['%s'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(growable: false)`, n)
		}
		if inner == "object" {
			if nul {
				return fmt.Sprintf(`(json['%s'] as List?)
            ?.whereType<Map>()
            .map((m) => m.cast<String, dynamic>())
            .toList(growable: false)`, n)
			}
			return fmt.Sprintf(`((json['%s'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => m.cast<String, dynamic>())
            .toList(growable: false)`, n)
		}
	}

	switch n {
	case "queryEcho":
		return `(json['queryEcho'] ?? '').toString().trim()`
	case "taskId":
		return `(json['taskId'] ?? '').toString()`
	case "skillId":
		return `(json['skillId'] ?? '').toString()`
	case "displayName":
		return `(json['displayName'] ?? '').toString()`
	case "description":
		if entityName == "AssistantSkillCatalogItemView" {
			return `json['description']?.toString()`
		}
	case "requiresConsent":
		if entityName == "AssistantSkillCatalogItemView" {
			return `json['requiresConsent'] == true`
		}
	case "status":
		if entityName == "AssistantUserTaskView" {
			return `(json['status'] ?? 'pending').toString()`
		}
	case "updatedAt":
		if entityName == "AssistantUserTaskView" {
			return `json['updatedAt']?.toString()`
		}
	case "dueAt":
		if entityName == "AssistantUserTaskView" {
			return `json['dueAt']?.toString()`
		}
	case "sourceSkillId":
		if entityName == "AssistantUserTaskView" {
			return `json['sourceSkillId']?.toString()`
		}
	case "iconHint":
		if entityName == "AssistantSkillCatalogItemView" {
			return `json['iconHint']?.toString()`
		}
	}

	switch t {
	case "string":
		if nul {
			return `json['` + n + `']?.toString()`
		}
		return `(json['` + n + `'] ?? '').toString()`
	case "bool":
		if nul {
			return `(json['` + n + `'] as bool?)`
		}
		return `json['` + n + `'] == true`
	case "int", "int64":
		if nul {
			return `(json['` + n + `'] as num?)?.toInt()`
		}
		return `(json['` + n + `'] as num?)?.toInt() ?? 0`
	case "float":
		if nul {
			return `(json['` + n + `'] as num?)?.toDouble()`
		}
		return `(json['` + n + `'] as num?)?.toDouble() ?? 0.0`
	case "datetime":
		parsed := `DateTime.tryParse((json['` + n + `'] ?? '').toString().trim())`
		if nul {
			return parsed
		}
		return `(` + parsed + ` ?? (throw FormatException('required datetime field ` + n + ` is invalid')))`
	case "timestamp":
		// Single-track: only camelCase wire keys; no snake_case dual-read.
		return `json['` + n + `']?.toString()`
	case "object", "jsonb":
		if nul {
			return `(json['` + n + `'] as Map?)?.cast<String, dynamic>()`
		}
		return `(json['` + n + `'] as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{}`
	case "enum":
		return `json['` + n + `']?.toString()`
	default:
		return `json['` + n + `']`
	}
}

func assistantWireToJsonExpr(
	ff *fieldsFile,
	enumCatalog *assistantEnumCatalog,
	f fieldDef,
) string {
	t := strings.TrimSpace(f.Type)
	if t == "enum" && assistantWireHasEnum(enumCatalog, f.EnumRef) {
		if assistantWireFieldNullable(f) {
			return f.Name + "?.wireName"
		}
		return f.Name + ".wireName"
	}
	if _, isEnt := ff.Entities[t]; isEnt {
		if assistantWireFieldNullable(f) {
			return f.Name + "?.toJson()"
		}
		return f.Name + ".toJson()"
	}
	if inner, ok := assistantWireListElementType(t); ok {
		if _, isEnt := ff.Entities[inner]; isEnt {
			if assistantWireFieldNullable(f) {
				return f.Name + "?.map((item) => item.toJson()).toList(growable: false)"
			}
			return f.Name + ".map((item) => item.toJson()).toList(growable: false)"
		}
	}
	if t == "datetime" {
		if assistantWireFieldNullable(f) {
			return f.Name + "?.toUtc().toIso8601String()"
		}
		return f.Name + ".toUtc().toIso8601String()"
	}
	return f.Name
}
