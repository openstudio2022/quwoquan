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
	if strings.TrimSpace(f.ClientDartName) != "" {
		return strings.TrimSpace(f.ClientDartName)
	}
	return f.Name
}

func rtcFieldNullable(f fieldDef) bool {
	if f.Type == "embedded_list" {
		return false
	}
	for _, c := range f.Constraints {
		if c == "NULLABLE" {
			return true
		}
	}
	return false
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
	case "string", "enum", "ObjectId":
		if rtcFieldNullable(f) {
			return "String?"
		}
		return "String"
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
	return "List<" + rtcItemDtoClass(strings.TrimSpace(f.ItemEntity)) + ">"
}

func rtcDartFieldType(f fieldDef) string {
	if f.Type == "embedded_list" {
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
	case "string", "enum", "ObjectId":
		if d == "" {
			return "''", true
		}
		return fmt.Sprintf("'%s'", strings.ReplaceAll(d, "'", "\\'")), true
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
	if len(f.JsonKeys) > 0 {
		var parts []string
		for _, k := range f.JsonKeys {
			parts = append(parts, fmt.Sprintf("map['%s']", k))
		}
		s := strings.Join(parts, " ?? ")
		if f.Type == "string" || f.Type == "ObjectId" || f.Type == "enum" {
			if !rtcFieldNullable(f) {
				return s + " ?? ''"
			}
		}
		return s
	}
	return fmt.Sprintf("map['%s']", f.Name)
}

func rtcFromMapExpr(f fieldDef) string {
	dart := rtcDartPublicFieldName(f)
	read := rtcFromMapReadKey(f)
	if f.Type == "embedded_list" {
		return "" // block generated separately
	}
	defLit, hasDef := rtcDartDefaultLiteral(f)

	switch f.Type {
	case "string", "enum", "ObjectId":
		if rtcFieldNullable(f) {
			return fmt.Sprintf("      %s: %s as String?,\n", dart, read)
		}
		fallback := "''"
		if hasDef {
			fallback = defLit
		}
		return fmt.Sprintf("      %s: %s as String? ?? %s,\n", dart, read, fallback)
	case "int", "long":
		if rtcFieldNullable(f) {
			return fmt.Sprintf("      %s: (%s as num?)?.toInt(),\n", dart, read)
		}
		fb := "0"
		if hasDef {
			fb = strings.Trim(defLit, "'")
		}
		return fmt.Sprintf("      %s: (%s as num?)?.toInt() ?? %s,\n", dart, read, fb)
	case "bool":
		if rtcFieldNullable(f) {
			return fmt.Sprintf("      %s: %s as bool?,\n", dart, read)
		}
		fb := "false"
		if hasDef {
			fb = defLit
		}
		return fmt.Sprintf("      %s: %s as bool? ?? %s,\n", dart, read, fb)
	case "datetime":
		if rtcFieldNullable(f) {
			// read is single-key style; coalesce keys not typical for optional datetimes
			single := fmt.Sprintf("map['%s']", f.Name)
			return fmt.Sprintf("      %s: %s != null\n          ? DateTime.tryParse(%s as String)\n          : null,\n",
				dart, single, single)
		}
		if f.Name == "createdAt" || f.Name == "updatedAt" {
			return fmt.Sprintf("      %s: DateTime.tryParse((%s as String?) ?? '') ??\n          DateTime.now(),\n", dart, read)
		}
		return fmt.Sprintf("      %s: %s != null\n          ? DateTime.tryParse(%s as String)\n          : DateTime.now(),\n",
			dart, read, read)
	default:
		return fmt.Sprintf("      %s: %s as String? ?? '',\n", dart, read)
	}
}

func rtcParticipantsFromMapBlock(itemEntity string) string {
	cls := rtcItemDtoClass(itemEntity)
	return fmt.Sprintf(`    final rawParticipants = map['participants'];
    final participants = <%s>[];
    if (rawParticipants is List) {
      for (final p in rawParticipants) {
        if (p is Map<String, dynamic>) {
          participants.add(%s.fromMap(p));
        } else if (p is Map) {
          participants.add(
            %s.fromMap(Map<String, dynamic>.from(p)),
          );
        }
      }
    }
`, cls, cls, cls)
}

func rtcToMapEntry(f fieldDef) string {
	key := rtcToJsonKey(f)
	dart := rtcDartPublicFieldName(f)
	if f.Type == "embedded_list" {
		return fmt.Sprintf("      '%s': %s.map((p) => p.toMap()).toList(),\n", key, dart)
	}
	if f.Type == "datetime" && rtcFieldNullable(f) {
		return fmt.Sprintf("      if (%s != null) '%s': %s!.toIso8601String(),\n", dart, key, dart)
	}
	if rtcFieldNullable(f) && f.Type != "datetime" {
		switch f.Type {
		case "string", "enum", "ObjectId":
			return fmt.Sprintf("      if (%s != null) '%s': %s,\n", dart, key, dart)
		case "int", "long":
			return fmt.Sprintf("      if (%s != null) '%s': %s,\n", dart, key, dart)
		case "bool":
			return fmt.Sprintf("      if (%s != null) '%s': %s,\n", dart, key, dart)
		}
	}
	if f.Type == "datetime" && !rtcFieldNullable(f) {
		return fmt.Sprintf("      '%s': %s.toIso8601String(),\n", key, dart)
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
		if f.Type == "embedded_list" {
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

	b.WriteString(fmt.Sprintf("  factory %s.fromMap(Map<String, dynamic> map) {\n", dtoName))
	// participants block first if present
	for _, f := range fields {
		if f.Type == "embedded_list" {
			b.WriteString(rtcParticipantsFromMapBlock(f.ItemEntity))
			break
		}
	}
	b.WriteString("    return " + dtoName + "(\n")
	for _, f := range fields {
		if f.Type == "embedded_list" {
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
		b.WriteString("  @override\n")
		b.WriteString("  bool operator ==(Object other) =>\n")
		b.WriteString("      identical(this, other) ||\n")
		b.WriteString("      other is " + dtoName + " &&\n")
		b.WriteString("          runtimeType == other.runtimeType &&\n")
		b.WriteString("          id == other.id &&\n")
		b.WriteString("          status == other.status &&\n")
		b.WriteString("          participantCount == other.participantCount &&\n")
		b.WriteString("          isRecording == other.isRecording &&\n")
		b.WriteString("          isScreenSharing == other.isScreenSharing &&\n")
		b.WriteString("          updatedAt == other.updatedAt;\n\n")
		b.WriteString("  @override\n")
		b.WriteString("  int get hashCode => Object.hash(\n")
		b.WriteString("        id,\n")
		b.WriteString("        status,\n")
		b.WriteString("        participantCount,\n")
		b.WriteString("        isRecording,\n")
		b.WriteString("        isScreenSharing,\n")
		b.WriteString("        updatedAt,\n")
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

func renderRtcCallSessionDtosDartFromFields(sourcePath string, ff *fieldsFile) string {
	cp, okP := ff.Entities["CallParticipant"]
	cs, okS := ff.Entities["CallSession"]
	if !okP || !okS {
		panic("rtc: missing entities")
	}
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from rtc/call_session/fields.yaml. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n// ignore_for_file: prefer_const_constructors\n\n")

	b.WriteString(rtcEmitDtoClass("CallParticipant", cp.Fields, "Dto",
		"通话参与者（与 metadata `CallParticipant` 对齐，JSON 枚举值为 string）。"))
	b.WriteString("\n")
	b.WriteString(rtcEmitDtoClass("CallSession", cs.Fields, "Dto",
		"通话会话（与 metadata `CallSession` 对齐；`id` 对应存储 `_id`，并兼容 wire `id`/`callId`）。"))
	return b.String()
}
