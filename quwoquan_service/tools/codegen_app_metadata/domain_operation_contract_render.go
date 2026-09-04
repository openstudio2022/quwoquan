package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

func renderDomainOperationContract(
	spec domainOperationContractSpec,
) (string, error) {
	var output strings.Builder
	output.WriteString("// Code generated from canonical domain contracts. DO NOT EDIT.\n")
	output.WriteString("// ContractGraph SHA256: ")
	output.WriteString(activeContractSHA256)
	output.WriteString("\n\nlibrary;\n\n")
	if spec.HasRequestPart {
		output.WriteString("import '../operation_request_payload.dart';\n")
	}
	externalImports := make([]string, 0, len(spec.ExternalImports)+1)
	for path := range spec.ExternalImports {
		externalImports = append(externalImports, path)
	}
	if modelsUseCanonicalSHA256Format(spec.Models) {
		externalImports = append(
			externalImports,
			canonicalSHA256DigestImportFor(spec.OwnerImport),
		)
	}
	sort.Strings(externalImports)
	for _, path := range externalImports {
		fmt.Fprintf(&output, "import %q;\n", path)
	}
	output.WriteString("\n")
	externalExports := make([]string, 0, len(spec.ExternalExports))
	for path := range spec.ExternalExports {
		externalExports = append(externalExports, path)
	}
	sort.Strings(externalExports)
	for _, path := range externalExports {
		fmt.Fprintf(&output, "export %q;\n", path)
	}
	if len(externalExports) > 0 {
		output.WriteString("\n")
	}
	if spec.HasRequestPart {
		output.WriteString("part '../generated/requests/")
		output.WriteString(spec.Domain)
		output.WriteString("/")
		output.WriteString(spec.Domain)
		output.WriteString("_operation_contracts.g.requests.g.dart';\n\n")
	}

	enumNames := make([]string, 0, len(spec.EnumMembers))
	for name := range spec.EnumMembers {
		enumNames = append(enumNames, name)
	}
	sort.Strings(enumNames)
	for _, name := range enumNames {
		renderDomainWireEnum(
			&output,
			name,
			spec.EnumMembers[name],
			spec.EnumUnknownMembers[name],
		)
	}

	modelNames := make([]string, 0, len(spec.Models))
	for name := range spec.Models {
		modelNames = append(modelNames, name)
	}
	sort.Strings(modelNames)
	for _, name := range modelNames {
		if err := renderDomainResponseModel(&output, spec.Models[name]); err != nil {
			return "", err
		}
	}

	responseNames := make([]string, 0, len(spec.ResponseEntities))
	for name := range spec.ResponseEntities {
		responseNames = append(responseNames, name)
	}
	sort.Strings(responseNames)
	for _, name := range responseNames {
		if _, external := spec.ExternalResponseEntities[name]; external {
			continue
		}
		fmt.Fprintf(
			&output,
			"%s decode%s(Object? response) =>\n    %s.fromWire(_requiredObject(response, %q), %q);\n\n",
			name,
			name,
			name,
			name,
			name,
		)
	}
	if spec.HasEmptyResponse {
		output.WriteString("void decodeEmptyResponse(Object? response) {\n")
		output.WriteString("  if (response != null) {\n")
		output.WriteString("    throw const FormatException('empty response must not contain a body');\n")
		output.WriteString("  }\n")
		output.WriteString("}\n\n")
	}
	renderDomainDecoderHelpers(&output, spec.Models, len(responseNames) > 0)
	return output.String(), nil
}

func modelsUseCanonicalSHA256Format(
	models map[string]requestModelSpec,
) bool {
	for _, model := range models {
		for _, field := range model.Fields {
			if strings.TrimSpace(field.Format) == canonicalSHA256Format {
				return true
			}
		}
	}
	return false
}

// canonicalSHA256DigestImportFor resolves the relative import of the canonical
// digest identity module for one generated domain library. The digest form has
// exactly one owner in quwoquan_cloud_contracts; generated decoders reference it
// instead of restating the pattern.
func canonicalSHA256DigestImportFor(ownerImport string) string {
	relative := strings.TrimPrefix(strings.TrimSpace(ownerImport), "../")
	depth := len(strings.Split(filepath.ToSlash(relative), "/")) - 1
	if depth < 1 {
		depth = 1
	}
	return strings.Repeat("../", depth) + "canonical_sha256_digest.dart"
}

func renderDomainWireEnum(
	output *strings.Builder,
	name string,
	members []canonicalRequestEnumMember,
	unknownMember string,
) {
	fmt.Fprintf(output, "enum %s {\n", name)
	for index, member := range members {
		terminator := ","
		if index == len(members)-1 && unknownMember == "" {
			terminator = ";"
		}
		fmt.Fprintf(
			output,
			"  %s(%q)%s\n",
			member.DartMember,
			member.WireValue,
			terminator,
		)
	}
	if unknownMember != "" {
		fmt.Fprintf(output, "  %s(\"\");\n", unknownMember)
		fmt.Fprintf(output, "\n  const %s(this._wireName);\n\n", name)
		output.WriteString("  final String _wireName;\n\n")
		output.WriteString("  String get wireName => switch (this) {\n")
		fmt.Fprintf(
			output,
			"    %s.%s => throw StateError('%s.%s cannot be encoded'),\n",
			name,
			unknownMember,
			name,
			unknownMember,
		)
		output.WriteString("    _ => _wireName,\n  };\n\n")
	} else {
		fmt.Fprintf(output, "\n  const %s(this.wireName);\n\n", name)
		output.WriteString("  final String wireName;\n\n")
	}
	fmt.Fprintf(output, "  static %s fromWire(Object? value, String path) {\n", name)
	output.WriteString("    return switch (value) {\n")
	for _, member := range members {
		fmt.Fprintf(
			output,
			"      %q => %s.%s,\n",
			member.WireValue,
			name,
			member.DartMember,
		)
	}
	if unknownMember != "" {
		fmt.Fprintf(output, "      String() => %s.%s,\n", name, unknownMember)
	}
	output.WriteString("      _ => throw FormatException('$path has an invalid enum value'),\n")
	output.WriteString("    };\n  }\n}\n\n")
}

func renderDomainResponseModel(
	output *strings.Builder,
	model requestModelSpec,
) error {
	for _, field := range model.Fields {
		if err := validateResponseFieldAdmission(field); err != nil {
			return fmt.Errorf("%s: %w", model.Name, err)
		}
	}
	coPresentGroups, err := responseCoPresentFieldGroups(model)
	if err != nil {
		return fmt.Errorf("%s: %w", model.Name, err)
	}
	fmt.Fprintf(output, "final class %s {\n", model.Name)
	fmt.Fprintf(output, "  const %s({\n", model.Name)
	for _, field := range model.Fields {
		typeName, nullable, err := responseFieldDartType(field)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
		}
		name := responseFieldDartName(field)
		if nullable {
			fmt.Fprintf(output, "    this.%s,\n", name)
		} else {
			fmt.Fprintf(output, "    required this.%s,\n", name)
		}
		_ = typeName
	}
	output.WriteString("  });\n\n")
	for _, field := range model.Fields {
		typeName, _, err := responseFieldDartType(field)
		if err != nil {
			return err
		}
		fmt.Fprintf(
			output,
			"  final %s %s;\n",
			typeName,
			responseFieldDartName(field),
		)
		recordEnumFieldBinding(enumFieldBinding{
			DartClass:      model.Name,
			DartField:      responseFieldDartName(field),
			DartType:       typeName,
			EnumRef:        field.EnumRef,
			ContractType:   field.Type,
			ClientDartType: field.ClientDartType,
		})
	}
	output.WriteString("\n  factory ")
	output.WriteString(model.Name)
	output.WriteString(".fromWire(Map<String, Object?> map, [String path = ")
	output.WriteString(strconv.Quote(model.Name))
	output.WriteString("]) {\n")
	output.WriteString("    _rejectUnknown")
	output.WriteString("Fields(map, const <String>{")
	for index, field := range model.Fields {
		if index > 0 {
			output.WriteString(", ")
		}
		output.WriteString(strconv.Quote(responseFieldWireName(field)))
	}
	output.WriteString("}, path);\n")
	for _, group := range coPresentGroups {
		output.WriteString("    _requireCoPresentFields(map, const <String>{")
		for index, wireName := range group {
			if index > 0 {
				output.WriteString(", ")
			}
			output.WriteString(strconv.Quote(wireName))
		}
		output.WriteString("}, path);\n")
	}
	fmt.Fprintf(output, "    return %s(\n", model.Name)
	for _, field := range model.Fields {
		expression, err := responseFieldDecodeExpression(
			field,
			"map["+strconv.Quote(responseFieldWireName(field))+"]",
			"'$path."+responseFieldWireName(field)+"'",
		)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
		}
		fmt.Fprintf(
			output,
			"      %s: %s,\n",
			responseFieldDartName(field),
			expression,
		)
	}
	output.WriteString("    );\n  }\n\n")
	output.WriteString("  Map<String, Object?> toWire() => <String, Object?>{\n")
	for _, field := range model.Fields {
		name := responseFieldDartName(field)
		wire := responseFieldWireName(field)
		expression, err := responseFieldEncodeExpression(field, name)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
		}
		if isResponseFieldNullable(field) {
			fmt.Fprintf(
				output,
				"    if (%s != null) %q: %s,\n",
				name,
				wire,
				expression,
			)
		} else {
			fmt.Fprintf(output, "    %q: %s,\n", wire, expression)
		}
	}
	output.WriteString("  };\n}\n\n")
	return nil
}

func responseFieldDartType(field fieldDef) (string, bool, error) {
	nullable := isResponseFieldNullable(field)
	metaType := strings.TrimSpace(field.Type)
	var result string
	switch metaType {
	case "string", "tag_ref", "time", "ObjectId", "uuid", "identifier":
		result = "String"
	case "url":
		result = "Uri"
	case "timestamp", "datetime", "date":
		result = "DateTime"
	case "int", "int32", "int64", "long":
		result = "int"
	case "float", "float32", "float64", "double":
		result = "double"
	case "bool", "boolean":
		result = "bool"
	case "enum":
		result = strings.TrimSpace(field.EnumRef)
	case "object":
		result = strings.TrimSpace(field.ObjectRef)
		if result == "" {
			result = "Map<String, Object?>"
		}
	case "json", "jsonb":
		result = "Map<String, Object?>"
	default:
		if strings.HasPrefix(metaType, "[]") {
			itemType, _, err := responseFieldDartType(
				responseFieldListItem(field),
			)
			if err != nil {
				return "", false, err
			}
			result = "List<" + strings.TrimSuffix(itemType, "?") + ">"
		} else {
			result = metaType
		}
	}
	if result == "" {
		return "", false, fmt.Errorf("metadata type is empty")
	}
	if nullable {
		result += "?"
	}
	return result, nullable, nil
}

func isResponseFieldNullable(field fieldDef) bool {
	return hasRequestConstraint(field, "NULLABLE")
}

// canonicalSHA256Format 是 contracts 里唯一被承认的字符串 canonical 字形；
// 具体字形判定由 quwoquan_cloud_contracts 的 isCanonicalSha256Digest 拥有，
// 生成器只负责把该约束绑定到字段上。
const canonicalSHA256Format = "canonical_sha256"

// responseFieldListItem derives the element field of one list wire type. The
// envelope admission bits belong to the list itself, so they are cleared for
// the element to keep one constraint bound to exactly one wire position.
func responseFieldListItem(field fieldDef) fieldDef {
	item := field
	item.Type = strings.TrimPrefix(strings.TrimSpace(field.Type), "[]")
	item.Constraints = nil
	item.MaxItems = 0
	item.Format = ""
	item.CoPresentWith = nil
	return item
}

// validateResponseFieldAdmission rejects an admission bit bound to a wire
// position that cannot express it, so a mis-declared contract fails codegen
// instead of silently generating an unconstrained decoder.
func validateResponseFieldAdmission(field fieldDef) error {
	metaType := strings.TrimSpace(field.Type)
	if format := strings.TrimSpace(field.Format); format != "" {
		if format != canonicalSHA256Format {
			return fmt.Errorf(
				"field %s declares unsupported format %q",
				field.Name,
				format,
			)
		}
		switch metaType {
		case "string", "identifier":
		default:
			return fmt.Errorf(
				"field %s format %s requires a string wire type, got %q",
				field.Name,
				format,
				metaType,
			)
		}
	}
	if field.MaxItems > 0 && !strings.HasPrefix(metaType, "[]") {
		return fmt.Errorf(
			"field %s declares max_items on non-list wire type %q",
			field.Name,
			metaType,
		)
	}
	return nil
}

// responseCoPresentFieldGroups resolves co_present_with into canonical
// all-present-or-all-absent wire name groups. Pairing is symmetric, so one
// declaration is enough and every member must be nullable — a required member
// can never be absent, which would make the group unsatisfiable.
func responseCoPresentFieldGroups(model requestModelSpec) ([][]string, error) {
	wireByName := make(map[string]string, len(model.Fields))
	nullableByName := make(map[string]bool, len(model.Fields))
	for _, field := range model.Fields {
		wireByName[field.Name] = responseFieldWireName(field)
		nullableByName[field.Name] = isResponseFieldNullable(field)
	}
	parent := map[string]string{}
	var find func(string) string
	find = func(name string) string {
		root, seen := parent[name]
		if !seen || root == name {
			parent[name] = name
			return name
		}
		resolved := find(root)
		parent[name] = resolved
		return resolved
	}
	for _, field := range model.Fields {
		if len(field.CoPresentWith) == 0 {
			continue
		}
		if !nullableByName[field.Name] {
			return nil, fmt.Errorf(
				"field %s declares co_present_with but is required",
				field.Name,
			)
		}
		for _, raw := range field.CoPresentWith {
			peer := strings.TrimSpace(raw)
			if peer == "" {
				return nil, fmt.Errorf(
					"field %s declares an empty co_present_with entry",
					field.Name,
				)
			}
			if peer == field.Name {
				return nil, fmt.Errorf(
					"field %s declares co_present_with on itself",
					field.Name,
				)
			}
			if _, exists := wireByName[peer]; !exists {
				return nil, fmt.Errorf(
					"field %s co_present_with references unknown field %s",
					field.Name,
					peer,
				)
			}
			if !nullableByName[peer] {
				return nil, fmt.Errorf(
					"field %s co_present_with references required field %s",
					field.Name,
					peer,
				)
			}
			if left, right := find(field.Name), find(peer); left != right {
				parent[right] = left
			}
		}
	}
	if len(parent) == 0 {
		return nil, nil
	}
	members := map[string][]string{}
	for name := range parent {
		root := find(name)
		members[root] = append(members[root], wireByName[name])
	}
	groups := make([][]string, 0, len(members))
	for _, group := range members {
		sort.Strings(group)
		groups = append(groups, group)
	}
	sort.Slice(groups, func(left, right int) bool {
		return strings.Join(groups[left], ",") < strings.Join(groups[right], ",")
	})
	return groups, nil
}

func responseFieldDartName(field fieldDef) string {
	if field.Name == "_id" {
		return "id"
	}
	return toDartFieldName(field.Name)
}

func responseFieldWireName(field fieldDef) string {
	if value := strings.TrimSpace(field.ClientWireName); value != "" {
		return value
	}
	if field.Name == "_id" {
		return "id"
	}
	return field.Name
}

func responseFieldDecodeExpression(
	field fieldDef,
	access string,
	path string,
) (string, error) {
	if isResponseFieldNullable(field) {
		nonNull := field
		nonNull.Constraints = responseConstraintsWithoutNullable(
			field.Constraints,
		)
		expression, err := responseFieldDecodeExpression(nonNull, access, path)
		if err != nil {
			return "", err
		}
		return access + " == null ? null : " + expression, nil
	}
	metaType := strings.TrimSpace(field.Type)
	switch metaType {
	case "string", "tag_ref", "ObjectId", "uuid", "identifier":
		if strings.TrimSpace(field.Format) == canonicalSHA256Format {
			return "_requiredCanonicalSha256Digest(" + access + ", " +
				path + ")", nil
		}
		if hasRequestConstraint(field, "NOT_BLANK") {
			return "_requiredNonBlankString(" + access + ", " + path + ")", nil
		}
		return "_requiredString(" + access + ", " + path + ")", nil
	case "time":
		return "_requiredTimeOfDay(" + access + ", " + path + ")", nil
	case "url":
		return "_requiredUri(" + access + ", " + path + ")", nil
	case "timestamp", "datetime", "date":
		return "_requiredTimestamp(" + access + ", " + path + ")", nil
	case "int", "int32", "int64", "long":
		minimum, maximum, err := responseIntegerBounds(field)
		if err != nil {
			return "", err
		}
		if maximum != nil || (minimum != nil && *minimum > 1) {
			arguments := ""
			if minimum != nil {
				arguments += fmt.Sprintf(", min: %d", *minimum)
			}
			if maximum != nil {
				arguments += fmt.Sprintf(", max: %d", *maximum)
			}
			return "_requiredBoundedInt(" + access + ", " + path +
				arguments + ")", nil
		}
		if hasRequestConstraint(field, "NON_NEGATIVE") {
			return "_requiredNonNegativeInt(" + access + ", " + path + ")", nil
		}
		if hasRequestConstraint(field, "MIN_1") {
			return "_requiredPositiveInt(" + access + ", " + path + ")", nil
		}
		return "_requiredInt(" + access + ", " + path + ")", nil
	case "float", "float32", "float64", "double":
		return "_requiredDouble(" + access + ", " + path + ")", nil
	case "bool", "boolean":
		return "_requiredBool(" + access + ", " + path + ")", nil
	case "enum":
		return strings.TrimSpace(field.EnumRef) +
			".fromWire(" + access + ", " + path + ")", nil
	case "object":
		if reference := strings.TrimSpace(field.ObjectRef); reference != "" {
			return reference + ".fromWire(_requiredObject(" + access + ", " +
				path + "), " + path + ")", nil
		}
		return "_requiredObject(" + access + ", " + path + ")", nil
	case "json", "jsonb":
		return "_requiredObject(" + access + ", " + path + ")", nil
	default:
		if strings.HasPrefix(metaType, "[]") {
			item := responseFieldListItem(field)
			itemExpression, err := responseFieldDecodeExpression(
				item,
				"entry.value",
				path+" + '[${entry.key}]'",
			)
			if err != nil {
				return "", err
			}
			itemType, _, err := responseFieldDartType(item)
			if err != nil {
				return "", err
			}
			listAccess := "_requiredList(" + access + ", " + path + ")"
			if field.MaxItems > 0 {
				listAccess = fmt.Sprintf(
					"_requiredBoundedList(%s, %s, max: %d)",
					access,
					path,
					field.MaxItems,
				)
			}
			return "List<" + strings.TrimSuffix(itemType, "?") +
				">.unmodifiable(" + listAccess +
				".asMap().entries.map((entry) => " + itemExpression + "))", nil
		}
		return metaType + ".fromWire(_requiredObject(" + access + ", " +
			path + "), " + path + ")", nil
	}
}

func responseIntegerBounds(field fieldDef) (*int, *int, error) {
	var minimum *int
	var maximum *int
	for _, raw := range field.Constraints {
		constraint := strings.TrimSpace(raw)
		switch {
		case constraint == "NON_NEGATIVE":
			minimum = stricterMinimum(minimum, 0)
		case constraint == "POSITIVE" || constraint == "MIN_1":
			minimum = stricterMinimum(minimum, 1)
		case strings.HasPrefix(constraint, "MIN_"):
			value, err := strconv.Atoi(strings.TrimPrefix(constraint, "MIN_"))
			if err != nil {
				return nil, nil, fmt.Errorf(
					"field %s has invalid integer constraint %q",
					field.Name,
					constraint,
				)
			}
			minimum = stricterMinimum(minimum, value)
		case strings.HasPrefix(constraint, "MAX_"):
			value, err := strconv.Atoi(strings.TrimPrefix(constraint, "MAX_"))
			if err != nil {
				return nil, nil, fmt.Errorf(
					"field %s has invalid integer constraint %q",
					field.Name,
					constraint,
				)
			}
			maximum = stricterMaximum(maximum, value)
		}
	}
	if minimum != nil && maximum != nil && *minimum > *maximum {
		return nil, nil, fmt.Errorf(
			"field %s has impossible integer bounds %d..%d",
			field.Name,
			*minimum,
			*maximum,
		)
	}
	return minimum, maximum, nil
}

func stricterMinimum(current *int, candidate int) *int {
	if current != nil && *current >= candidate {
		return current
	}
	value := candidate
	return &value
}

func stricterMaximum(current *int, candidate int) *int {
	if current != nil && *current <= candidate {
		return current
	}
	value := candidate
	return &value
}

func responseIntegerUsesBoundedDecoder(field fieldDef) bool {
	minimum, maximum, err := responseIntegerBounds(field)
	if err != nil {
		return false
	}
	return maximum != nil || (minimum != nil && *minimum > 1)
}

func responseConstraintsWithoutNullable(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if strings.TrimSpace(value) == "NULLABLE" {
			continue
		}
		result = append(result, value)
	}
	return result
}

func responseFieldEncodeExpression(field fieldDef, access string) (string, error) {
	nonNullAccess := access
	if isResponseFieldNullable(field) {
		nonNullAccess += "!"
	}
	metaType := strings.TrimSpace(field.Type)
	switch metaType {
	case "string", "tag_ref", "time", "ObjectId", "uuid", "identifier",
		"int", "int32", "int64", "long",
		"float", "float32", "float64", "double", "bool", "boolean",
		"json", "jsonb":
		return nonNullAccess, nil
	case "url":
		return nonNullAccess + ".toString()", nil
	case "timestamp", "datetime", "date":
		return nonNullAccess + ".toUtc().toIso8601String()", nil
	case "enum":
		return nonNullAccess + ".wireName", nil
	case "object":
		if strings.TrimSpace(field.ObjectRef) == "" {
			return nonNullAccess, nil
		}
		return nonNullAccess + ".toWire()", nil
	default:
		if strings.HasPrefix(metaType, "[]") {
			item := field
			item.Type = strings.TrimPrefix(metaType, "[]")
			item.Constraints = nil
			itemExpression, err := responseFieldEncodeExpression(item, "value")
			if err != nil {
				return "", err
			}
			return nonNullAccess + ".map((value) => " + itemExpression +
				").toList(growable: false)", nil
		}
		return nonNullAccess + ".toWire()", nil
	}
}
