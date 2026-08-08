package main

import (
	"fmt"
	"sort"
	"strings"
)

func assistantClassNeedsHelpers(fields []assistantContractField) bool {
	for _, field := range fields {
		switch field.Type {
		case "list<string>", "list<map>", "map<object>":
			return true
		case "object":
			return true
		}
	}
	return false
}

func assistantRenderSchemaHelpers(
	fields []assistantContractField,
	schema *assistantContractSchema,
	index *assistantContractIndex,
	codec assistantSchemaCodec,
) string {
	var b strings.Builder
	needsStringList := false
	needsMapList := false
	needsObjectMap := false
	for _, field := range fields {
		switch field.Type {
		case "list<string>":
			needsStringList = true
		case "list<map>":
			needsMapList = true
		case "map<object>":
			needsObjectMap = true
		case "object":
			if field.Ref != "" {
				_ = assistantResolveRefClassName(field.Ref, schema, index)
			}
		}
	}
	if needsStringList {
		b.WriteString("  static List<String> _assistantStringList(Object? value) {\n")
		b.WriteString("    if (value is List) {\n")
		b.WriteString("      return value.map((item) => item.toString().trim()).where((item) => item.isNotEmpty).toList(growable: false);\n")
		b.WriteString("    }\n")
		b.WriteString("    return const <String>[];\n")
		b.WriteString("  }\n")
		if needsMapList || needsObjectMap {
			b.WriteString("\n")
		}
	}
	if needsMapList {
		b.WriteString("  static List<Map<String, dynamic>> _assistantMapList(Object? value) {\n")
		b.WriteString("    if (value is List) {\n")
		b.WriteString("      return value.whereType<Map>().map((item) => item.cast<String, dynamic>()).toList(growable: false);\n")
		b.WriteString("    }\n")
		b.WriteString("    return const <Map<String, dynamic>>[];\n")
		b.WriteString("  }\n")
		if needsObjectMap {
			b.WriteString("\n")
		}
	}
	if needsObjectMap {
		b.WriteString("  static Map<String, T> _assistantObjectMap<T>(\n")
		b.WriteString("    Object? value,\n")
		b.WriteString(fmt.Sprintf(
			"    T Function(String key, Map<String, %s> value) parser,\n",
			codec.mapValueType,
		))
		b.WriteString("  ) {\n")
		b.WriteString("    if (value is! Map) return <String, T>{};\n")
		b.WriteString("    final typed = <String, T>{};\n")
		b.WriteString("    for (final entry in value.entries) {\n")
		b.WriteString("      final raw = entry.value;\n")
		b.WriteString("      if (raw is! Map) continue;\n")
		b.WriteString(fmt.Sprintf(
			"      typed[entry.key.toString()] = parser(entry.key.toString(), raw.cast<String, %s>());\n",
			codec.mapValueType,
		))
		b.WriteString("    }\n")
		b.WriteString("    return typed;\n")
		b.WriteString("  }\n")
	}
	return b.String()
}

func assistantFieldIsCollection(field assistantContractField) bool {
	return strings.HasPrefix(field.Type, "list<") || strings.HasPrefix(field.Type, "map")
}

func assistantFieldIsPrimitive(field assistantContractField) bool {
	switch field.Type {
	case "string", "int", "double", "bool", "any":
		return true
	default:
		return false
	}
}

func assistantDefaultString(value interface{}) string {
	if value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return typed
	default:
		return fmt.Sprint(typed)
	}
}

func assistantDefaultInt(value interface{}) int {
	if value == nil {
		return 0
	}
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	default:
		return 0
	}
}

func assistantDefaultFloat(value interface{}) float64 {
	if value == nil {
		return 0
	}
	switch typed := value.(type) {
	case float64:
		return typed
	case int:
		return float64(typed)
	case int64:
		return float64(typed)
	default:
		return 0
	}
}

func assistantDefaultBool(value interface{}) bool {
	if value == nil {
		return false
	}
	typed, ok := value.(bool)
	return ok && typed
}

func assistantFormatFloat(value float64) string {
	return strings.TrimRight(strings.TrimRight(fmt.Sprintf("%.6f", value), "0"), ".")
}

func assistantRenderEnumDefaultValue(field assistantContractField) string {
	return fmt.Sprintf("%s.%s", field.EnumRef, assistantEnumMemberNameFromDefault(field.EnumRef, assistantDefaultString(field.Default)))
}

func assistantEnumMemberNameFromDefault(enumName, raw string) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return assistantEnumDefault(enumName)
	}
	parts := strings.FieldsFunc(trimmed, func(r rune) bool {
		return r == '_' || r == '-' || r == ' '
	})
	if len(parts) == 0 {
		return assistantEnumDefault(enumName)
	}
	var b strings.Builder
	for index, part := range parts {
		if part == "" {
			continue
		}
		lower := strings.ToLower(part[:1]) + part[1:]
		if index == 0 {
			b.WriteString(lower)
			continue
		}
		b.WriteString(strings.ToUpper(lower[:1]) + lower[1:])
	}
	result := b.String()
	if result == "" {
		return assistantEnumDefault(enumName)
	}
	return result
}

func assistantSchemaUsesPartitionedMap(schema *assistantContractSchema) bool {
	for _, f := range schema.Fields {
		if strings.TrimSpace(f.Type) == "partitioned_map" {
			return true
		}
	}
	return false
}

func assistantDartFieldToPascal(fieldName string) string {
	parts := strings.Split(fieldName, "_")
	var b strings.Builder
	for _, p := range parts {
		if p == "" {
			continue
		}
		if len(p) == 1 {
			b.WriteString(strings.ToUpper(p))
			continue
		}
		b.WriteString(strings.ToUpper(p[:1]) + p[1:])
	}
	return b.String()
}

func assistantPartitionedWrapperClassName(rootDartClass, fieldName string) string {
	return strings.TrimSpace(rootDartClass) + assistantDartFieldToPascal(strings.TrimSpace(fieldName)) + "Partitioned"
}

func renderPartitionedMapWrappers(schema *assistantContractSchema) string {
	var b strings.Builder
	for _, field := range schema.Fields {
		if strings.TrimSpace(field.Type) != "partitioned_map" {
			continue
		}
		ref := strings.TrimSpace(field.Ref)
		if ref == "" {
			continue
		}
		coreName := assistantResolveRefClassName(ref, schema, nil)
		if coreName == "" {
			continue
		}
		wrapperName := assistantPartitionedWrapperClassName(schema.DartClass, field.Name)
		b.WriteString(fmt.Sprintf("class %s {\n", wrapperName))
		b.WriteString(fmt.Sprintf("  const %s({\n", wrapperName))
		b.WriteString(fmt.Sprintf("    this.core = const %s(),\n", coreName))
		b.WriteString("    this.extensions = const <String, dynamic>{},\n")
		b.WriteString("  });\n\n")
		b.WriteString(fmt.Sprintf("  final %s core;\n", coreName))
		b.WriteString("  final Map<String, dynamic> extensions;\n\n")
		b.WriteString("  Map<String, dynamic> toWireMap() => RunArtifactsMapPartition.mergeSlices(core.toJson(), extensions);\n\n")
		b.WriteString(fmt.Sprintf("  factory %s.fromWireMap(Map<String, dynamic> map) {\n", wrapperName))
		b.WriteString(fmt.Sprintf("    return %s(\n", wrapperName))
		b.WriteString(fmt.Sprintf("      core: %s.fromJson(RunArtifactsMapPartition.%sStable(map)),\n", coreName, field.Name))
		b.WriteString(fmt.Sprintf("      extensions: RunArtifactsMapPartition.%sExtension(map),\n", field.Name))
		b.WriteString("    );\n")
		b.WriteString("  }\n")
		b.WriteString("}\n\n")
	}
	return b.String()
}

// renderRunArtifactsMapStableKeysDart emits `RunArtifactsMapStableKeys` for `map_stable_keys` in schema.yaml.
func renderRunArtifactsMapStableKeysDart(schema *assistantContractSchema, sourceMeta string) string {
	if len(schema.MapStableKeys) == 0 {
		return ""
	}
	var b strings.Builder
	b.WriteString(fmt.Sprintf("// Code generated by tools/codegen_app_metadata from %s map_stable_keys. DO NOT EDIT.\n\n", sourceMeta))
	b.WriteString("// ignore_for_file: avoid_classes_with_only_static_members\n\n")
	b.WriteString("/// 与 metadata `map_stable_keys` 同步：`RunArtifacts` 中 `type: map` 字段的稳定键集合。\n")
	b.WriteString("abstract final class RunArtifactsMapStableKeys {\n")
	b.WriteString("  RunArtifactsMapStableKeys._();\n\n")
	var names []string
	for k := range schema.MapStableKeys {
		names = append(names, k)
	}
	sort.Strings(names)
	for _, mapField := range names {
		keys := append([]string(nil), schema.MapStableKeys[mapField]...)
		sort.Strings(keys)
		b.WriteString(fmt.Sprintf("  /// `%s` 的稳定键（其余键视为扩展键）。\n", mapField))
		b.WriteString(fmt.Sprintf("  static const Set<String> %s = {\n", mapField))
		for _, key := range keys {
			b.WriteString(fmt.Sprintf("    %q,\n", key))
		}
		b.WriteString("  };\n\n")
	}
	b.WriteString("}\n")
	return b.String()
}
