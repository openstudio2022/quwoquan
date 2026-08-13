package main

import (
	"fmt"
	"path"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

type assistantContractSchema struct {
	DartClass     string                                `yaml:"dart_class"`
	LibraryPath   string                                `yaml:"library_path"`
	OutputPath    string                                `yaml:"output_path"`
	Contract      string                                `yaml:"contract"`
	Version       string                                `yaml:"version"`
	Kind          string                                `yaml:"kind"`
	Imports       []string                              `yaml:"imports"`
	RefImports    map[string]string                     `yaml:"ref_imports"`
	Fields        []assistantContractField              `yaml:"fields"`
	Subcontracts  map[string]assistantSubcontractSchema `yaml:"subcontracts"`
	MapStableKeys map[string][]string                   `yaml:"map_stable_keys,omitempty"`
}

type assistantSubcontractSchema struct {
	ClassName string                   `yaml:"class_name"`
	Fields    []assistantContractField `yaml:"fields"`
}

type assistantContractField struct {
	Name         string      `yaml:"name"`
	Type         string      `yaml:"type"`
	Required     bool        `yaml:"required"`
	Default      interface{} `yaml:"default"`
	Ref          string      `yaml:"ref"`
	EnumRef      string      `yaml:"enum_ref"`
	Strict       bool        `yaml:"strict"`
	AllowUnknown bool        `yaml:"allow_unknown"`
}

type assistantContractIndex struct {
	libraryByClass map[string]string
	// fieldsByClass maps Dart wire class name → fields (root fields + all subcontracts) for const default literals.
	fieldsByClass map[string][]assistantContractField
}

type assistantSchemaCodec struct {
	encodeMethod string
	decodeMethod string
	mapValueType string
	inputName    string
	pathAware    bool
}

// App-owned Assistant libraries the renderer must import by name. These mirror
// the `library_path` values in the Assistant contracts and follow the App object
// tree layout `service/assistant_service/assistant/<object>/domain/`.
const (
	assistantRuntimeEnumsLibrary = "service/assistant_service/assistant/assistant_run/domain/runtime_enums.dart"
	assistantTurnContractLibrary = "service/assistant_service/assistant/assistant_turn_view/domain/assistant_turn_contract.dart"
	assistantContextFillLibrary  = "service/assistant_service/assistant/assistant_run/domain/context_fill_contract.dart"
	assistantMapPartitionLibrary = "service/assistant_service/assistant/assistant_run/domain/run_artifacts_map_partition.dart"
)

var (
	assistantJSONSchemaCodec = assistantSchemaCodec{
		encodeMethod: "toJson",
		decodeMethod: "fromJson",
		mapValueType: "dynamic",
		inputName:    "json",
	}
	assistantWireSchemaCodec = assistantSchemaCodec{
		encodeMethod: "toWire",
		decodeMethod: "fromWire",
		mapValueType: "Object?",
		inputName:    "map",
		pathAware:    true,
	}
)

type assistantSchemaHeader struct {
	DartClass   string `yaml:"dart_class"`
	LibraryPath string `yaml:"library_path"`
}

func readAssistantContractSchema(path string) (*assistantContractSchema, error) {
	var parsed assistantContractSchema
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func loadAssistantContractIndex(_ string) (*assistantContractIndex, error) {
	index := &assistantContractIndex{
		libraryByClass: map[string]string{},
		fieldsByClass:  map[string][]assistantContractField{},
	}
	for _, schemaPath := range metadataDocumentPaths("assistant", "/schema.yaml") {
		relative, err := metadataDocumentPath(schemaPath)
		if err != nil {
			return nil, err
		}
		segments := strings.Split(relative, "/")
		if len(segments) != 3 || strings.HasPrefix(segments[1], "_") {
			continue
		}
		data, err := readMetadataDocument(schemaPath)
		if err != nil {
			return nil, err
		}
		var header assistantSchemaHeader
		if err := yaml.Unmarshal(data, &header); err != nil {
			return nil, err
		}
		if strings.TrimSpace(header.DartClass) == "" || strings.TrimSpace(header.LibraryPath) == "" {
			continue
		}
		dc := strings.TrimSpace(header.DartClass)
		index.libraryByClass[dc] = strings.TrimSpace(header.LibraryPath)

		var full assistantContractSchema
		if err := yaml.Unmarshal(data, &full); err == nil {
			if len(full.Fields) > 0 {
				index.fieldsByClass[dc] = full.Fields
			}
			for _, sub := range full.Subcontracts {
				cn := strings.TrimSpace(sub.ClassName)
				if cn != "" && len(sub.Fields) > 0 {
					index.fieldsByClass[cn] = sub.Fields
				}
			}
		}
	}
	return index, nil
}

func renderAssistantSchemaDrivenContract(schema *assistantContractSchema, index *assistantContractIndex, sourceMeta string) string {
	return renderAssistantSchemaDrivenContractWithCodec(
		schema,
		index,
		sourceMeta,
		assistantJSONSchemaCodec,
	)
}

func renderAssistantSchemaDrivenWireContract(
	schema *assistantContractSchema,
	index *assistantContractIndex,
	sourceMeta string,
) string {
	return renderAssistantSchemaDrivenContractWithCodec(
		schema,
		index,
		sourceMeta,
		assistantWireSchemaCodec,
	)
}

func renderAssistantSchemaDrivenContractWithCodec(
	schema *assistantContractSchema,
	index *assistantContractIndex,
	sourceMeta string,
	codec assistantSchemaCodec,
) string {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("// Code generated by tools/codegen_app_metadata from %s. DO NOT EDIT.\n\n", sourceMeta))
	b.WriteString("// ignore_for_file: avoid_classes_with_only_static_members\n\n")

	imports := assistantCollectContractImports(schema, index)
	if len(imports) > 0 {
		for _, imp := range imports {
			b.WriteString(fmt.Sprintf("import '%s';\n", imp))
		}
		b.WriteString("\n")
	}

	subcontractKeys := assistantReferencedLocalSubcontracts(schema)
	for _, key := range subcontractKeys {
		sub := schema.Subcontracts[key]
		b.WriteString(renderAssistantSchemaClass(
			sub.ClassName,
			sub.Fields,
			schema,
			index,
			codec,
		))
		b.WriteString("\n")
		b.WriteString(renderAssistantSchemaFieldConstants(sub.ClassName, sub.Fields))
		b.WriteString("\n")
	}

	if pw := renderPartitionedMapWrappers(schema); pw != "" {
		b.WriteString(pw)
		b.WriteString("\n")
	}

	b.WriteString(renderAssistantSchemaClass(
		schema.DartClass,
		schema.Fields,
		schema,
		index,
		codec,
	))
	b.WriteString("\n")
	b.WriteString(renderAssistantSchemaFieldConstants(schema.DartClass, schema.Fields))
	return b.String()
}

func assistantReferencedLocalSubcontracts(schema *assistantContractSchema) []string {
	seen := map[string]bool{}
	var keys []string
	var visitFields func([]assistantContractField)
	visitFields = func(fields []assistantContractField) {
		for _, field := range fields {
			if field.Ref == "" {
				continue
			}
			sub, ok := schema.Subcontracts[field.Ref]
			if !ok || seen[field.Ref] {
				continue
			}
			seen[field.Ref] = true
			keys = append(keys, field.Ref)
			visitFields(sub.Fields)
		}
	}
	visitFields(schema.Fields)
	sort.Strings(keys)
	return keys
}

func assistantCollectContractImports(schema *assistantContractSchema, index *assistantContractIndex) []string {
	importsSet := map[string]bool{}
	const packageOwner = "package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart"
	hasRuntimeEnumImport := false
	for _, imp := range schema.Imports {
		trimmed := strings.TrimSpace(imp)
		if trimmed != "" {
			importsSet[trimmed] = true
			hasRuntimeEnumImport = hasRuntimeEnumImport ||
				strings.HasSuffix(trimmed, "assistant_runtime_enums.g.dart") ||
				strings.HasSuffix(trimmed, assistantRuntimeEnumsLibrary)
		}
	}
	if assistantSchemaNeedsRuntimeEnums(schema) &&
		!hasRuntimeEnumImport &&
		!importsSet["package:quwoquan_app/"+assistantTurnContractLibrary] &&
		!importsSet["package:quwoquan_app/"+assistantContextFillLibrary] {
		importsSet["package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart"] = true
	}
	for _, field := range schema.Fields {
		ref := strings.TrimSpace(field.Ref)
		if ref == "" {
			continue
		}
		if _, ok := schema.Subcontracts[ref]; ok {
			continue
		}
		if override := strings.TrimSpace(schema.RefImports[ref]); override != "" {
			importsSet[override] = true
			continue
		}
		if assistantSchemaIsCloudPackageOwned(schema) &&
			assistantPackageOwnedContractType(ref) {
			continue
		}
		if importsSet[packageOwner] && assistantPackageOwnedContractType(ref) {
			continue
		}
		if libraryPath, ok := index.libraryByClass[ref]; ok && libraryPath != schema.LibraryPath {
			if importsSet[packageOwner] && strings.HasPrefix(
				libraryPath,
				"package:quwoquan_cloud_contracts/",
			) {
				continue
			}
			importsSet[assistantReferencedLibraryImport(schema, libraryPath)] = true
		}
	}
	if assistantSchemaUsesPartitionedMap(schema) {
		importsSet["package:quwoquan_app/"+assistantMapPartitionLibrary] = true
	}
	var imports []string
	for imp := range importsSet {
		imports = append(imports, imp)
	}
	sort.Strings(imports)
	return imports
}

func assistantSchemaIsCloudPackageOwned(schema *assistantContractSchema) bool {
	return schema != nil && strings.HasPrefix(
		strings.TrimSpace(schema.LibraryPath),
		"package:quwoquan_cloud_contracts/",
	)
}

func assistantReferencedLibraryImport(
	schema *assistantContractSchema,
	libraryPath string,
) string {
	target := strings.TrimSpace(libraryPath)
	if !strings.HasPrefix(target, "package:") {
		return "package:quwoquan_app/" + target
	}
	current := ""
	if schema != nil {
		current = strings.TrimSpace(schema.LibraryPath)
	}
	currentPackage, currentPath, currentOK := assistantPackageLibraryParts(current)
	targetPackage, targetPath, targetOK := assistantPackageLibraryParts(target)
	if currentOK && targetOK && currentPackage == targetPackage &&
		path.Dir(currentPath) == path.Dir(targetPath) {
		return path.Base(targetPath)
	}
	return target
}

func assistantPackageLibraryParts(value string) (string, string, bool) {
	trimmed := strings.TrimPrefix(strings.TrimSpace(value), "package:")
	if trimmed == value {
		return "", "", false
	}
	parts := strings.SplitN(trimmed, "/", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "", "", false
	}
	return parts[0], parts[1], true
}

func assistantPackageOwnedContractType(name string) bool {
	switch strings.TrimSpace(name) {
	case "RuntimeFailureWire",
		"AssistantRunEnvelopeWire",
		"AssistantStreamEventWire",
		"AssistantSessionWire",
		"SkillSubscriptionWire":
		return true
	default:
		return false
	}
}

func assistantSchemaNeedsRuntimeEnums(schema *assistantContractSchema) bool {
	for _, field := range schema.Fields {
		if strings.TrimSpace(field.EnumRef) != "" {
			return true
		}
	}
	for _, key := range assistantReferencedLocalSubcontracts(schema) {
		for _, field := range schema.Subcontracts[key].Fields {
			if strings.TrimSpace(field.EnumRef) != "" {
				return true
			}
		}
	}
	return false
}

func renderAssistantSchemaClass(
	className string,
	fields []assistantContractField,
	schema *assistantContractSchema,
	index *assistantContractIndex,
	codec assistantSchemaCodec,
) string {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("class %s {\n", className))
	b.WriteString(fmt.Sprintf("  const %s({\n", className))
	for _, field := range fields {
		decl := assistantRenderConstructorField(field, schema, index)
		b.WriteString("    " + decl + "\n")
	}
	b.WriteString("  });\n\n")
	for _, field := range fields {
		dartType := assistantResolveFieldDartType(field, schema, index)
		b.WriteString(fmt.Sprintf("  final %s %s;\n", dartType, field.Name))
		recordEnumFieldBinding(enumFieldBinding{
			DartClass:    className,
			DartField:    field.Name,
			DartType:     dartType,
			EnumRef:      field.EnumRef,
			ContractType: field.Type,
		})
	}
	b.WriteString("\n")
	b.WriteString(fmt.Sprintf(
		"  Map<String, %s> %s() => <String, %s>{\n",
		codec.mapValueType,
		codec.encodeMethod,
		codec.mapValueType,
	))
	for _, field := range fields {
		b.WriteString(fmt.Sprintf(
			"        '%s': %s,\n",
			field.Name,
			assistantRenderToMapValue(
				"        ",
				field,
				field.Name,
				schema,
				index,
				codec,
			),
		))
	}
	b.WriteString("      };\n\n")
	if codec.pathAware {
		b.WriteString(fmt.Sprintf(
			"  factory %s.%s(Map<String, %s> %s, [String path = %q]) {\n",
			className,
			codec.decodeMethod,
			codec.mapValueType,
			codec.inputName,
			className,
		))
	} else {
		b.WriteString(fmt.Sprintf(
			"  factory %s.%s(Map<String, %s> %s) {\n",
			className,
			codec.decodeMethod,
			codec.mapValueType,
			codec.inputName,
		))
	}
	b.WriteString(assistantRenderSchemaMapValidation(className, fields, codec))
	b.WriteString(fmt.Sprintf("    return %s(\n", className))
	for _, field := range fields {
		b.WriteString(fmt.Sprintf(
			"      %s: %s,\n",
			field.Name,
			assistantRenderFromMapValue(field, schema, index, codec),
		))
	}
	b.WriteString("    );\n")
	b.WriteString("  }\n")
	if assistantClassNeedsHelpers(fields) {
		b.WriteString("\n")
		b.WriteString(assistantRenderSchemaHelpers(fields, schema, index, codec))
	}
	b.WriteString("}\n")
	return b.String()
}

func assistantRenderSchemaJsonValidation(
	className string,
	fields []assistantContractField,
) string {
	return assistantRenderSchemaMapValidation(
		className,
		fields,
		assistantJSONSchemaCodec,
	)
}

func assistantRenderSchemaMapValidation(
	className string,
	fields []assistantContractField,
	codec assistantSchemaCodec,
) string {
	var b strings.Builder
	b.WriteString("    const allowedFields = <String>{\n")
	for _, field := range fields {
		fmt.Fprintf(&b, "      '%s',\n", field.Name)
	}
	b.WriteString("    };\n")
	b.WriteString(fmt.Sprintf(
		"    final unknownFields = %s.keys\n",
		codec.inputName,
	))
	b.WriteString("        .where((key) => !allowedFields.contains(key))\n")
	b.WriteString("        .toList(growable: false);\n")
	b.WriteString("    if (unknownFields.isNotEmpty) {\n")
	if codec.pathAware {
		fmt.Fprintf(
			&b,
			"      throw FormatException('$path: %s response contains unknown fields: ${unknownFields.join(', ')}');\n",
			className,
		)
	} else {
		fmt.Fprintf(
			&b,
			"      throw FormatException('%s response contains unknown fields: ${unknownFields.join(', ')}');\n",
			className,
		)
	}
	b.WriteString("    }\n")
	for _, field := range fields {
		condition := assistantSchemaMapInvalidCondition(field, codec.inputName)
		if condition == "" {
			continue
		}
		required := field.Required && field.Default == nil
		if required {
			fmt.Fprintf(
				&b,
				"    if (!%s.containsKey('%s') || %s['%s'] == null || (%s)) {\n",
				codec.inputName,
				field.Name,
				codec.inputName,
				field.Name,
				condition,
			)
		} else {
			fmt.Fprintf(
				&b,
				"    if (%s.containsKey('%s') && %s['%s'] != null && (%s)) {\n",
				codec.inputName,
				field.Name,
				codec.inputName,
				field.Name,
				condition,
			)
		}
		if codec.pathAware {
			fmt.Fprintf(
				&b,
				"      throw FormatException('$path: %s field %s has an invalid wire value');\n",
				className,
				field.Name,
			)
		} else {
			fmt.Fprintf(
				&b,
				"      throw const FormatException('%s field %s has an invalid wire value');\n",
				className,
				field.Name,
			)
		}
		b.WriteString("    }\n")
	}
	return b.String()
}

func assistantSchemaJsonInvalidCondition(field assistantContractField) string {
	return assistantSchemaMapInvalidCondition(field, "json")
}

func assistantSchemaMapInvalidCondition(
	field assistantContractField,
	inputName string,
) string {
	accessor := inputName + "['" + field.Name + "']"
	switch field.Type {
	case "string", "enum":
		return accessor + " is! String"
	case "int", "double":
		return accessor + " is! num"
	case "bool":
		return accessor + " is! bool"
	case "datetime":
		return accessor + " is! String || DateTime.tryParse(" + accessor + " as String) == null"
	case "map", "object", "map<object>", "partitioned_map":
		return accessor + " is! Map"
	case "list<string>":
		return accessor + " is! List || (" + accessor +
			" as List).any((item) => item is! String)"
	case "list<map>", "list<object>":
		return accessor + " is! List || (" + accessor +
			" as List).any((item) => item is! Map)"
	case "any":
		if field.Required && field.Default == nil {
			return "false"
		}
		return ""
	default:
		return ""
	}
}

func renderAssistantSchemaFieldConstants(
	className string,
	fields []assistantContractField,
) string {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("class %sFields {\n", className))
	for _, field := range fields {
		b.WriteString(fmt.Sprintf("  static const String %s = '%s';\n", field.Name, field.Name))
	}
	b.WriteString("}\n")
	return b.String()
}

func assistantRenderConstructorField(field assistantContractField, schema *assistantContractSchema, index *assistantContractIndex) string {
	if field.Required && field.Default == nil {
		return fmt.Sprintf("required this.%s,", field.Name)
	}
	if field.Default != nil {
		return fmt.Sprintf("this.%s = %s,", field.Name, assistantRenderDefaultValue(field, schema, index))
	}
	return fmt.Sprintf("this.%s,", field.Name)
}

func assistantResolveFieldDartType(field assistantContractField, schema *assistantContractSchema, index *assistantContractIndex) string {
	baseType := assistantResolveBaseDartType(field, schema, index)
	if field.Required || field.Default != nil || assistantFieldIsCollection(field) || assistantFieldIsPrimitive(field) || field.Type == "enum" {
		return baseType
	}
	if field.Type == "object" && field.Ref != "" {
		return baseType + "?"
	}
	if field.Type == "datetime" {
		return "DateTime?"
	}
	return baseType
}

func assistantResolveBaseDartType(field assistantContractField, schema *assistantContractSchema, index *assistantContractIndex) string {
	switch field.Type {
	case "string":
		return "String"
	case "int":
		return "int"
	case "double":
		return "double"
	case "bool":
		return "bool"
	case "datetime":
		return "DateTime"
	case "map":
		return "Map<String, dynamic>"
	case "list<string>":
		return "List<String>"
	case "list<map>":
		return "List<Map<String, dynamic>>"
	case "enum":
		return field.EnumRef
	case "object":
		if field.Ref != "" {
			return assistantResolveRefClassName(field.Ref, schema, index)
		}
		return "Map<String, dynamic>"
	case "list<object>":
		if field.Ref != "" {
			return "List<" + assistantResolveRefClassName(field.Ref, schema, index) + ">"
		}
		return "List<Map<String, dynamic>>"
	case "map<object>":
		if field.Ref != "" {
			return "Map<String, " + assistantResolveRefClassName(field.Ref, schema, index) + ">"
		}
		return "Map<String, Map<String, dynamic>>"
	case "partitioned_map":
		if strings.TrimSpace(field.Ref) == "" {
			return "dynamic"
		}
		return assistantPartitionedWrapperClassName(strings.TrimSpace(schema.DartClass), field.Name)
	case "any":
		return "dynamic"
	default:
		return "dynamic"
	}
}

func assistantResolveRefClassName(ref string, schema *assistantContractSchema, index *assistantContractIndex) string {
	if sub, ok := schema.Subcontracts[ref]; ok && strings.TrimSpace(sub.ClassName) != "" {
		return strings.TrimSpace(sub.ClassName)
	}
	return strings.TrimSpace(ref)
}

// assistantFindSubcontract resolves subcontract by YAML key or by exported class_name.
func assistantFindSubcontract(schema *assistantContractSchema, ref string) (*assistantSubcontractSchema, string, bool) {
	ref = strings.TrimSpace(ref)
	if ref == "" || schema.Subcontracts == nil {
		return nil, "", false
	}
	if sub, ok := schema.Subcontracts[ref]; ok && strings.TrimSpace(sub.ClassName) != "" {
		return &sub, strings.TrimSpace(sub.ClassName), true
	}
	for _, sub := range schema.Subcontracts {
		if strings.TrimSpace(sub.ClassName) == ref {
			return &sub, strings.TrimSpace(sub.ClassName), true
		}
	}
	return nil, "", false
}

func assistantRenderConstRequiredWireLiteral(className string, fields []assistantContractField, schema *assistantContractSchema, index *assistantContractIndex) string {
	var parts []string
	for _, f := range fields {
		if !f.Required || f.Default != nil {
			continue
		}
		parts = append(parts, fmt.Sprintf("%s: %s", f.Name, assistantRenderConstRequiredFieldSeed(f, schema, index)))
	}
	if len(parts) == 0 {
		return fmt.Sprintf("const %s()", className)
	}
	return fmt.Sprintf("const %s(%s)", className, strings.Join(parts, ", "))
}

func assistantRenderConstRequiredFieldSeed(field assistantContractField, schema *assistantContractSchema, index *assistantContractIndex) string {
	switch field.Type {
	case "string":
		return `""`
	case "int":
		return "0"
	case "double":
		return "0.0"
	case "bool":
		return "false"
	case "object":
		if field.Ref == "" {
			return "const <String, dynamic>{}"
		}
		nestedClass := assistantResolveRefClassName(field.Ref, schema, index)
		if index != nil && index.fieldsByClass != nil {
			if nf, ok := index.fieldsByClass[nestedClass]; ok {
				return assistantRenderConstRequiredWireLiteral(nestedClass, nf, schema, index)
			}
		}
		if sub, _, ok := assistantFindSubcontract(schema, field.Ref); ok {
			return assistantRenderConstRequiredWireLiteral(nestedClass, sub.Fields, schema, index)
		}
		return fmt.Sprintf("const %s()", nestedClass)
	case "enum":
		return assistantRenderEnumDefaultValue(field)
	case "list<string>", "list<map>", "list<object>", "map", "map<object>", "partitioned_map", "datetime", "any":
		return assistantRenderDefaultValue(field, schema, index)
	default:
		return assistantRenderDefaultValue(field, schema, index)
	}
}

func assistantRenderDefaultValue(field assistantContractField, schema *assistantContractSchema, index *assistantContractIndex) string {
	switch field.Type {
	case "string":
		return fmt.Sprintf("%q", assistantDefaultString(field.Default))
	case "int":
		return fmt.Sprintf("%d", assistantDefaultInt(field.Default))
	case "double":
		return assistantFormatFloat(assistantDefaultFloat(field.Default))
	case "bool":
		if assistantDefaultBool(field.Default) {
			return "true"
		}
		return "false"
	case "datetime":
		return "null"
	case "map":
		return "const <String, dynamic>{}"
	case "list<string>":
		return "const <String>[]"
	case "list<map>":
		return "const <Map<String, dynamic>>[]"
	case "enum":
		return assistantRenderEnumDefaultValue(field)
	case "object":
		if field.Ref != "" {
			className := assistantResolveRefClassName(field.Ref, schema, index)
			if index != nil && index.fieldsByClass != nil {
				if extFields, ok := index.fieldsByClass[className]; ok {
					return assistantRenderConstRequiredWireLiteral(className, extFields, schema, index)
				}
			}
			if sub, _, ok := assistantFindSubcontract(schema, field.Ref); ok {
				return assistantRenderConstRequiredWireLiteral(className, sub.Fields, schema, index)
			}
			return fmt.Sprintf("const %s()", className)
		}
		return "const <String, dynamic>{}"
	case "list<object>":
		if field.Ref != "" {
			return fmt.Sprintf("const <%s>[]", assistantResolveRefClassName(field.Ref, schema, index))
		}
		return "const <Map<String, dynamic>>[]"
	case "map<object>":
		if field.Ref != "" {
			return fmt.Sprintf("const <String, %s>{}", assistantResolveRefClassName(field.Ref, schema, index))
		}
		return "const <String, Map<String, dynamic>>{}"
	case "partitioned_map":
		return fmt.Sprintf("const %s()", assistantPartitionedWrapperClassName(strings.TrimSpace(schema.DartClass), field.Name))
	case "any":
		return "null"
	default:
		return "null"
	}
}

func assistantRenderToJsonValue(indent string, field assistantContractField, accessor string, schema *assistantContractSchema, index *assistantContractIndex) string {
	return assistantRenderToMapValue(
		indent,
		field,
		accessor,
		schema,
		index,
		assistantJSONSchemaCodec,
	)
}

func assistantRenderToMapValue(
	indent string,
	field assistantContractField,
	accessor string,
	schema *assistantContractSchema,
	index *assistantContractIndex,
	codec assistantSchemaCodec,
) string {
	switch field.Type {
	case "enum":
		return accessor + ".wireName"
	case "object":
		if field.Ref != "" {
			if strings.HasSuffix(assistantResolveFieldDartType(field, schema, index), "?") {
				return accessor + "?." + codec.encodeMethod + "()"
			}
			return accessor + "." + codec.encodeMethod + "()"
		}
		return accessor
	case "list<object>":
		if field.Ref != "" {
			return accessor + ".map((item) => item." + codec.encodeMethod + "()).toList(growable: false)"
		}
		return accessor
	case "map<object>":
		if field.Ref != "" {
			return fmt.Sprintf(
				"<String, %s>{\n%s  for (final entry in %s.entries) entry.key: entry.value.%s(),\n%s}",
				codec.mapValueType,
				indent,
				accessor,
				codec.encodeMethod,
				indent,
			)
		}
		return accessor
	case "datetime":
		return accessor + "?.toIso8601String()"
	case "partitioned_map":
		return accessor + ".toWireMap()"
	default:
		return accessor
	}
}

func assistantRenderFromJsonValue(field assistantContractField, schema *assistantContractSchema, index *assistantContractIndex) string {
	return assistantRenderFromMapValue(
		field,
		schema,
		index,
		assistantJSONSchemaCodec,
	)
}

func assistantRenderFromMapValue(
	field assistantContractField,
	schema *assistantContractSchema,
	index *assistantContractIndex,
	codec assistantSchemaCodec,
) string {
	accessor := fmt.Sprintf("%s['%s']", codec.inputName, field.Name)
	fieldPath := fmt.Sprintf("'$path.%s'", field.Name)
	decodeRef := func(
		className string,
		mapExpression string,
		pathExpression string,
	) string {
		if codec.pathAware {
			return fmt.Sprintf(
				"%s.%s(%s, %s)",
				className,
				codec.decodeMethod,
				mapExpression,
				pathExpression,
			)
		}
		return fmt.Sprintf(
			"%s.%s(%s)",
			className,
			codec.decodeMethod,
			mapExpression,
		)
	}
	switch field.Type {
	case "string":
		return fmt.Sprintf("(%s as String?)?.trim() ?? %s", accessor, assistantRenderDefaultValue(field, schema, index))
	case "int":
		return fmt.Sprintf("(%s as num?)?.toInt() ?? %d", accessor, assistantDefaultInt(field.Default))
	case "double":
		return fmt.Sprintf("(%s as num?)?.toDouble() ?? %s", accessor, assistantFormatFloat(assistantDefaultFloat(field.Default)))
	case "bool":
		if assistantDefaultBool(field.Default) {
			return accessor + " != false"
		}
		return accessor + " == true"
	case "datetime":
		return fmt.Sprintf("((%s as String?)?.trim().isNotEmpty == true) ? DateTime.tryParse((%s as String).trim()) : null", accessor, accessor)
	case "map":
		return fmt.Sprintf("(%s as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{}", accessor)
	case "list<string>":
		return fmt.Sprintf("_assistantStringList(%s)", accessor)
	case "list<map>":
		return fmt.Sprintf("_assistantMapList(%s)", accessor)
	case "enum":
		fallback := "''"
		if !field.Required && field.Default != nil {
			fallback = fmt.Sprintf("%q", assistantDefaultString(field.Default))
		}
		if field.AllowUnknown {
			return fmt.Sprintf("parse%s((%s as String?)?.trim() ?? %s)", field.EnumRef, accessor, fallback)
		}
		return fmt.Sprintf("parse%sStrict((%s as String?)?.trim() ?? %s)", field.EnumRef, accessor, fallback)
	case "object":
		if field.Ref != "" {
			className := assistantResolveRefClassName(field.Ref, schema, index)
			mapExpression := fmt.Sprintf(
				"(%s as Map).cast<String, %s>()",
				accessor,
				codec.mapValueType,
			)
			if field.Required && field.Default == nil {
				return fmt.Sprintf(
					"%s is Map ? %s : (throw FormatException(%s))",
					accessor,
					decodeRef(className, mapExpression, fieldPath),
					assistantMissingObjectError(field.Name, codec),
				)
			}
			if field.Default != nil {
				fallback := assistantRenderDefaultValue(field, schema, index)
				return fmt.Sprintf("%s is Map ? %s : %s", accessor, decodeRef(className, mapExpression, fieldPath), fallback)
			}
			return fmt.Sprintf("%s is Map ? %s : null", accessor, decodeRef(className, mapExpression, fieldPath))
		}
		return fmt.Sprintf("(%s as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{}", accessor)
	case "list<object>":
		if field.Ref != "" {
			className := assistantResolveRefClassName(field.Ref, schema, index)
			if codec.pathAware {
				mapExpression := fmt.Sprintf(
					"(entry.value as Map).cast<String, %s>()",
					codec.mapValueType,
				)
				return fmt.Sprintf(
					"(%s as List?)?.asMap().entries.map((entry) => %s).toList(growable: false) ?? %s",
					accessor,
					decodeRef(
						className,
						mapExpression,
						fmt.Sprintf("'$path.%s[${entry.key}]'", field.Name),
					),
					assistantRenderDefaultValue(field, schema, index),
				)
			}
			mapExpression := fmt.Sprintf(
				"item.cast<String, %s>()",
				codec.mapValueType,
			)
			return fmt.Sprintf(
				"(%s as List?)?.whereType<Map>().map((item) => %s).toList(growable: false) ?? %s",
				accessor,
				decodeRef(className, mapExpression, fieldPath),
				assistantRenderDefaultValue(field, schema, index),
			)
		}
		return fmt.Sprintf("_assistantMapList(%s)", accessor)
	case "map<object>":
		className := assistantResolveRefClassName(field.Ref, schema, index)
		return fmt.Sprintf(
			"_assistantObjectMap(%s, (key, value) => %s)",
			accessor,
			decodeRef(
				className,
				"value",
				fmt.Sprintf("'$path.%s.$key'", field.Name),
			),
		)
	case "any":
		return accessor
	case "partitioned_map":
		wrapper := assistantPartitionedWrapperClassName(strings.TrimSpace(schema.DartClass), field.Name)
		return fmt.Sprintf("%s is Map ? %s.fromWireMap((%s as Map).cast<String, dynamic>()) : %s", accessor, wrapper, accessor, assistantRenderDefaultValue(field, schema, index))
	default:
		return accessor
	}
}

func assistantMissingObjectError(
	fieldName string,
	codec assistantSchemaCodec,
) string {
	if codec.pathAware {
		return fmt.Sprintf("'$path.%s: required object field %s is missing'", fieldName, fieldName)
	}
	return fmt.Sprintf("'required object field %s is missing'", fieldName)
}
