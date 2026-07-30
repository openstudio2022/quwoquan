package main

import (
	"fmt"
	"path/filepath"
	"strconv"
	"strings"
)

func rtcDartPublicFieldName(f fieldDef) string {
	if strings.TrimSpace(f.ClientDartName) != "" {
		return strings.TrimSpace(f.ClientDartName)
	}
	return f.Name
}

func rtcToJsonKey(f fieldDef) string {
	// Storage `_id` must never appear as a client wire key. Metadata must name the
	// canonical business identity explicitly; codegen does not invent an alias.
	if strings.TrimSpace(f.Source) == "_id" || strings.TrimSpace(f.Name) == "_id" {
		if name := strings.TrimSpace(f.ClientDartName); name != "" {
			return name
		}
		panic("rtc: storage _id requires client_dart_name")
	}
	if strings.TrimSpace(f.Source) != "" {
		return strings.TrimSpace(f.Source)
	}
	return f.Name
}

func rtcIdentityDartName(fields []fieldDef) string {
	for _, f := range fields {
		if rtcHasNotNull(f) {
			for _, constraint := range f.Constraints {
				if constraint == "PK" {
					return rtcDartPublicFieldName(f)
				}
			}
		}
	}
	panic("rtc: CallSession requires a PK field")
}

func rtcFieldNullable(f fieldDef) bool {
	if _, ok := rtcOwnedListItem(f); ok {
		return false
	}
	for _, c := range f.Constraints {
		if c == "NULLABLE" {
			return true
		}
	}
	return false
}

// RTC object fields use the repository-wide canonical `[]OwnedEntity` type
// syntax. The DTO generator must consume that contract directly; inventing a
// generator-only `embedded_list`/`item_entity` dialect creates a second truth
// source and can silently degrade the field to String.
func rtcOwnedListItem(f fieldDef) (string, bool) {
	raw := strings.TrimSpace(f.Type)
	if !strings.HasPrefix(raw, "[]") {
		return "", false
	}
	item := strings.TrimSpace(strings.TrimPrefix(raw, "[]"))
	if item == "" {
		panic("rtc: list field " + f.Name + " requires an item type")
	}
	return item, true
}

func rtcHasNotNull(f fieldDef) bool {
	for _, c := range f.Constraints {
		if c == "NOT_NULL" || c == "PK" {
			return true
		}
	}
	return false
}

func rtcDartScalarType(f fieldDef) string {
	switch f.Type {
	case "string", "ObjectId":
		if rtcFieldNullable(f) {
			return "String?"
		}
		return "String"
	case "enum":
		if strings.TrimSpace(f.EnumRef) == "" {
			panic("rtc: enum field " + f.Name + " requires enum_ref")
		}
		if rtcFieldNullable(f) {
			return f.EnumRef + "?"
		}
		return f.EnumRef
	case "int", "long":
		if rtcFieldNullable(f) {
			return "int?"
		}
		return "int"
	case "bool":
		if rtcFieldNullable(f) {
			return "bool?"
		}
		return "bool"
	case "datetime":
		if rtcFieldNullable(f) {
			return "DateTime?"
		}
		return "DateTime"
	default:
		return "String"
	}
}

func rtcItemDtoClass(entity string) string {
	return entity + "Dto"
}

func rtcEmbeddedListDartType(f fieldDef) string {
	item, ok := rtcOwnedListItem(f)
	if !ok {
		panic("rtc: field " + f.Name + " is not an owned list")
	}
	return "List<" + rtcItemDtoClass(item) + ">"
}

func rtcDartFieldType(f fieldDef) string {
	if _, ok := rtcOwnedListItem(f); ok {
		return rtcEmbeddedListDartType(f)
	}
	return rtcDartScalarType(f)
}

// copyWith 覆盖参数：字段已为 T? 时不再追加 ?（避免 String??）。
func rtcDartCopyWithParamType(f fieldDef) string {
	t := rtcDartFieldType(f)
	if strings.HasSuffix(t, "?") {
		return t
	}
	return t + "?"
}

func rtcDartDefaultLiteral(f fieldDef) (string, bool) {
	d := strings.TrimSpace(f.ClientDefault)
	if d == "" {
		return "", false
	}
	switch f.Type {
	case "int", "long":
		if _, err := strconv.Atoi(d); err == nil {
			return d, true
		}
	case "bool":
		if d == "true" || d == "false" {
			return d, true
		}
	case "string", "ObjectId":
		if d == "" {
			return "''", true
		}
		return fmt.Sprintf("'%s'", strings.ReplaceAll(d, "'", "\\'")), true
	case "enum":
		if strings.TrimSpace(f.EnumRef) == "" {
			panic("rtc: enum field " + f.Name + " requires enum_ref")
		}
		return f.EnumRef + "." + toDartValueName(d), true
	}
	if d == "true" || d == "false" {
		return d, true
	}
	if _, err := strconv.Atoi(d); err == nil {
		return d, true
	}
	return fmt.Sprintf("'%s'", strings.ReplaceAll(d, "'", "\\'")), true
}

func rtcFromMapReadKey(f fieldDef) string {
	// Single-track: metadata source is the wire key; client_dart_name only names
	// the public Dart property.
	return fmt.Sprintf("map['%s']", rtcToJsonKey(f))
}

func rtcFromMapExpr(f fieldDef) string {
	dart := rtcDartPublicFieldName(f)
	read := rtcFromMapReadKey(f)
	if _, ok := rtcOwnedListItem(f); ok {
		return "" // block generated separately
	}
	defLit, hasDef := rtcDartDefaultLiteral(f)

	switch f.Type {
	case "string", "ObjectId":
		if rtcFieldNullable(f) {
			return fmt.Sprintf("      %s: _rtcOptionalString(map, '%s'),\n", dart, rtcToJsonKey(f))
		}
		if hasDef {
			return fmt.Sprintf(
				"      %s: %s == null ? %s : _rtcRequiredString(map, '%s'),\n",
				dart,
				read,
				defLit,
				rtcToJsonKey(f),
			)
		}
		return fmt.Sprintf("      %s: _rtcRequiredString(map, '%s'),\n", dart, rtcToJsonKey(f))
	case "enum":
		if rtcFieldNullable(f) {
			return fmt.Sprintf(
				"      %s: %s == null ? null : %s.fromString(_rtcRequiredString(map, '%s')),\n",
				dart,
				read,
				f.EnumRef,
				rtcToJsonKey(f),
			)
		}
		if !hasDef {
			return fmt.Sprintf(
				"      %s: %s.fromString(_rtcRequiredString(map, '%s')),\n",
				dart,
				f.EnumRef,
				rtcToJsonKey(f),
			)
		}
		return fmt.Sprintf(
			"      %s: %s == null ? %s : %s.fromString(_rtcRequiredString(map, '%s')),\n",
			dart,
			read,
			defLit,
			f.EnumRef,
			rtcToJsonKey(f),
		)
	case "int", "long":
		if rtcFieldNullable(f) {
			return fmt.Sprintf("      %s: _rtcOptionalInt(map, '%s'),\n", dart, rtcToJsonKey(f))
		}
		if hasDef {
			return fmt.Sprintf(
				"      %s: %s == null ? %s : _rtcRequiredInt(map, '%s'),\n",
				dart,
				read,
				strings.Trim(defLit, "'"),
				rtcToJsonKey(f),
			)
		}
		return fmt.Sprintf("      %s: _rtcRequiredInt(map, '%s'),\n", dart, rtcToJsonKey(f))
	case "bool":
		if rtcFieldNullable(f) {
			return fmt.Sprintf("      %s: _rtcOptionalBool(map, '%s'),\n", dart, rtcToJsonKey(f))
		}
		if hasDef {
			return fmt.Sprintf(
				"      %s: %s == null ? %s : _rtcRequiredBool(map, '%s'),\n",
				dart,
				read,
				defLit,
				rtcToJsonKey(f),
			)
		}
		return fmt.Sprintf("      %s: _rtcRequiredBool(map, '%s'),\n", dart, rtcToJsonKey(f))
	case "datetime":
		if rtcFieldNullable(f) {
			return fmt.Sprintf("      %s: _rtcOptionalDateTime(map, '%s'),\n", dart, rtcToJsonKey(f))
		}
		return fmt.Sprintf("      %s: _rtcRequiredDateTime(map, '%s'),\n", dart, rtcToJsonKey(f))
	default:
		return fmt.Sprintf("      %s: _rtcRequiredString(map, '%s'),\n", dart, rtcToJsonKey(f))
	}
}

func rtcHasNullableBool(entities ...entityDef) bool {
	for _, entity := range entities {
		for _, field := range entity.Fields {
			if field.Type == "bool" && rtcFieldNullable(field) {
				return true
			}
		}
	}
	return false
}

func rtcEmitWireDecodeHelpers(entities ...entityDef) string {
	var b strings.Builder
	b.WriteString(`String _rtcRequiredString(Map<Object?, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('RTC field "$key" must be a non-empty string');
  }
  return value;
}

String? _rtcOptionalString(Map<Object?, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('RTC field "$key" must be a string');
  }
  return value;
}

int _rtcRequiredInt(Map<Object?, Object?> map, String key) {
  final value = map[key];
  if (value is! num) {
    throw FormatException('RTC field "$key" must be a number');
  }
  return value.toInt();
}

int? _rtcOptionalInt(Map<Object?, Object?> map, String key) {
  if (map[key] == null) return null;
  return _rtcRequiredInt(map, key);
}

bool _rtcRequiredBool(Map<Object?, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) {
    throw FormatException('RTC field "$key" must be a bool');
  }
  return value;
}
`)
	if rtcHasNullableBool(entities...) {
		b.WriteString(`
bool? _rtcOptionalBool(Map<Object?, Object?> map, String key) {
  if (map[key] == null) return null;
  return _rtcRequiredBool(map, key);
}
`)
	}
	b.WriteString(`
DateTime _rtcRequiredDateTime(Map<Object?, Object?> map, String key) {
  final raw = _rtcRequiredString(map, key);
  final value = DateTime.tryParse(raw);
  if (value == null) {
    throw FormatException('RTC field "$key" must be an ISO-8601 timestamp');
  }
  return value.toUtc();
}

DateTime? _rtcOptionalDateTime(Map<Object?, Object?> map, String key) {
  if (map[key] == null) return null;
  return _rtcRequiredDateTime(map, key);
}
`)
	return b.String()
}

func rtcParticipantsFromMapBlock(itemEntity string) string {
	cls := rtcItemDtoClass(itemEntity)
	return fmt.Sprintf(`    final rawParticipants = map['participants'];
    final participants = <%s>[];
    if (rawParticipants is List<Object?>) {
      for (final p in rawParticipants) {
        if (p is Map<Object?, Object?>) {
          participants.add(%s.fromMap(p));
        }
      }
    }
`, cls, cls)
}

func rtcToMapEntry(f fieldDef) string {
	key := rtcToJsonKey(f)
	dart := rtcDartPublicFieldName(f)
	if _, ok := rtcOwnedListItem(f); ok {
		return fmt.Sprintf("      '%s': %s.map((p) => p.toMap()).toList(),\n", key, dart)
	}
	if f.Type == "datetime" && rtcFieldNullable(f) {
		return fmt.Sprintf("      if (%s != null) '%s': %s!.toIso8601String(),\n", dart, key, dart)
	}
	if rtcFieldNullable(f) && f.Type != "datetime" {
		switch f.Type {
		case "string", "ObjectId":
			return fmt.Sprintf("      if (%s != null) '%s': %s,\n", dart, key, dart)
		case "enum":
			return fmt.Sprintf("      if (%s != null) '%s': %s!.toApiString(),\n", dart, key, dart)
		case "int", "long":
			return fmt.Sprintf("      if (%s != null) '%s': %s,\n", dart, key, dart)
		case "bool":
			return fmt.Sprintf("      if (%s != null) '%s': %s,\n", dart, key, dart)
		}
	}
	if f.Type == "datetime" && !rtcFieldNullable(f) {
		return fmt.Sprintf("      '%s': %s.toIso8601String(),\n", key, dart)
	}
	if f.Type == "enum" {
		return fmt.Sprintf("      '%s': %s.toApiString(),\n", key, dart)
	}
	return fmt.Sprintf("      '%s': %s,\n", key, dart)
}

func rtcEmitDtoClass(
	entityName string,
	fields []fieldDef,
	classSuffix string,
	docLine string,
) string {
	dtoName := entityName + classSuffix
	var b strings.Builder
	b.WriteString(fmt.Sprintf("/// %s\n", docLine))
	b.WriteString(fmt.Sprintf("class %s {\n", dtoName))
	b.WriteString(fmt.Sprintf("  const %s({\n", dtoName))

	for _, f := range fields {
		if _, ok := rtcOwnedListItem(f); ok {
			b.WriteString(fmt.Sprintf("    this.%s = const [],\n", rtcDartPublicFieldName(f)))
			continue
		}
		dart := rtcDartPublicFieldName(f)
		defLit, hasDef := rtcDartDefaultLiteral(f)
		req := rtcHasNotNull(f) && !rtcFieldNullable(f) && !hasDef
		if req {
			b.WriteString(fmt.Sprintf("    required this.%s,\n", dart))
		} else if hasDef {
			b.WriteString(fmt.Sprintf("    this.%s = %s,\n", dart, defLit))
		} else {
			b.WriteString(fmt.Sprintf("    this.%s,\n", dart))
		}
	}

	b.WriteString("  });\n\n")

	for _, f := range fields {
		b.WriteString(fmt.Sprintf("  final %s %s;\n", rtcDartFieldType(f), rtcDartPublicFieldName(f)))
	}
	b.WriteString("\n")

	b.WriteString(fmt.Sprintf("  factory %s.fromMap(Map<Object?, Object?> map) {\n", dtoName))
	// participants block first if present
	for _, f := range fields {
		if item, ok := rtcOwnedListItem(f); ok {
			b.WriteString(rtcParticipantsFromMapBlock(item))
			break
		}
	}
	b.WriteString("    return " + dtoName + "(\n")
	for _, f := range fields {
		if _, ok := rtcOwnedListItem(f); ok {
			b.WriteString("      participants: participants,\n")
			continue
		}
		b.WriteString(rtcFromMapExpr(f))
	}
	b.WriteString("    );\n")
	b.WriteString("  }\n\n")

	b.WriteString("  Map<String, dynamic> toMap() {\n")
	b.WriteString("    return {\n")
	for _, f := range fields {
		b.WriteString(rtcToMapEntry(f))
	}
	b.WriteString("    };\n")
	b.WriteString("  }\n\n")

	// copyWith
	b.WriteString("  " + dtoName + " copyWith({\n")
	for _, f := range fields {
		b.WriteString(fmt.Sprintf("    %s %s,\n", rtcDartCopyWithParamType(f), rtcDartPublicFieldName(f)))
	}
	b.WriteString("  }) {\n")
	b.WriteString("    return " + dtoName + "(\n")
	for _, f := range fields {
		d := rtcDartPublicFieldName(f)
		b.WriteString(fmt.Sprintf("      %s: %s ?? this.%s,\n", d, d, d))
	}
	b.WriteString("    );\n")
	b.WriteString("  }\n\n")

	if entityName == "CallSession" {
		// CallSession 相等性只取关键状态字段；候选清单按 fields.yaml 实际存在字段
		// 过滤（如 isRecording 随录制能力退役后不再出现），禁止硬编码已删字段。
		identity := rtcIdentityDartName(fields)
		present := make(map[string]bool, len(fields))
		for _, f := range fields {
			present[rtcDartPublicFieldName(f)] = true
		}
		keyFields := []string{identity}
		for _, candidate := range []string{"status", "participantCount", "isRecording", "isScreenSharing", "updatedAt"} {
			if present[candidate] {
				keyFields = append(keyFields, candidate)
			}
		}
		b.WriteString("  @override\n")
		b.WriteString("  bool operator ==(Object other) =>\n")
		b.WriteString("      identical(this, other) ||\n")
		b.WriteString("      other is " + dtoName + " &&\n")
		b.WriteString("          runtimeType == other.runtimeType &&\n")
		for i, d := range keyFields {
			if i == len(keyFields)-1 {
				b.WriteString(fmt.Sprintf("          %s == other.%s;\n\n", d, d))
			} else {
				b.WriteString(fmt.Sprintf("          %s == other.%s &&\n", d, d))
			}
		}
		b.WriteString("  @override\n")
		b.WriteString("  int get hashCode => Object.hash(\n")
		for _, d := range keyFields {
			b.WriteString("        " + d + ",\n")
		}
		b.WriteString("      );\n")
	} else {
		b.WriteString("  @override\n")
		b.WriteString("  bool operator ==(Object other) =>\n")
		b.WriteString("      identical(this, other) ||\n")
		b.WriteString("      other is " + dtoName + " &&\n")
		b.WriteString("          runtimeType == other.runtimeType &&\n")
		for i, f := range fields {
			d := rtcDartPublicFieldName(f)
			if i == len(fields)-1 {
				b.WriteString(fmt.Sprintf("          %s == other.%s;\n\n", d, d))
			} else {
				b.WriteString(fmt.Sprintf("          %s == other.%s &&\n", d, d))
			}
		}
		b.WriteString("  @override\n")
		b.WriteString("  int get hashCode => Object.hash(\n")
		for _, f := range fields {
			b.WriteString("        " + rtcDartPublicFieldName(f) + ",\n")
		}
		b.WriteString("      );\n")
	}

	b.WriteString("}\n")
	return b.String()
}

func rtcUsedEnumRefs(entities ...entityDef) []string {
	seen := map[string]bool{}
	refs := make([]string, 0)
	for _, entity := range entities {
		for _, field := range entity.Fields {
			ref := strings.TrimSpace(field.EnumRef)
			if field.Type != "enum" || ref == "" || seen[ref] {
				continue
			}
			seen[ref] = true
			refs = append(refs, ref)
		}
	}
	return refs
}

func rtcEmitEnum(enumName string, values []string) string {
	if len(values) == 0 {
		panic("rtc: shared enum " + enumName + " has no values")
	}
	var b strings.Builder
	b.WriteString("enum " + enumName + " {\n")
	for index, value := range values {
		terminator := ","
		if index == len(values)-1 {
			terminator = ";"
		}
		b.WriteString(fmt.Sprintf("  %s('%s')%s\n", toDartValueName(value), value, terminator))
	}
	b.WriteString("\n")
	b.WriteString(fmt.Sprintf("  const %s(this.wireValue);\n\n", enumName))
	b.WriteString("  final String wireValue;\n\n")
	b.WriteString(fmt.Sprintf("  static %s fromString(String raw) {\n", enumName))
	b.WriteString("    return switch (raw.trim()) {\n")
	for _, value := range values {
		b.WriteString(fmt.Sprintf("      '%s' => %s.%s,\n", value, enumName, toDartValueName(value)))
	}
	b.WriteString(fmt.Sprintf(
		"      _ => throw FormatException('Unknown %s wire value: $raw'),\n",
		enumName,
	))
	b.WriteString("    };\n  }\n\n")
	b.WriteString("  String toApiString() => wireValue;\n")
	b.WriteString("}\n")
	return b.String()
}

func renderRtcCallSessionDtosDartFromFields(
	sourcePath string,
	ff *fieldsFile,
	sharedEnums map[string][]string,
) string {
	cp, okP := ff.Entities["CallParticipant"]
	cs, okS := ff.Entities["CallSession"]
	if !okP || !okS {
		panic("rtc: missing entities")
	}
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from rtc/rtc/call_session/fields.yaml. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n// ignore_for_file: prefer_const_constructors\n\n")

	for _, enumRef := range rtcUsedEnumRefs(cp, cs) {
		values, ok := sharedEnums[enumRef]
		if !ok {
			panic("rtc: enum_ref " + enumRef + " is absent from _shared/types.yaml")
		}
		b.WriteString(rtcEmitEnum(enumRef, values))
		b.WriteString("\n")
	}
	b.WriteString(rtcEmitWireDecodeHelpers(cp, cs))
	b.WriteString("\n")

	b.WriteString(rtcEmitDtoClass("CallParticipant", cp.Fields, "Dto",
		"通话参与者（与 metadata `CallParticipant` 和 shared enum 对齐）。"))
	b.WriteString("\n")
	identity := rtcIdentityDartName(cs.Fields)
	b.WriteString(rtcEmitDtoClass("CallSession", cs.Fields, "Dto",
		fmt.Sprintf("通话会话（与 metadata `CallSession` 对齐；`%s` 为唯一 wire 键）。", identity)))
	return b.String()
}
