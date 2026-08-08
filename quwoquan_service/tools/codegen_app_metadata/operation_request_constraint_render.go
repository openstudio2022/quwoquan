package main

import (
	"fmt"
	"strconv"
	"strings"
)

type requestConditionalConstraint struct {
	requiredWhen    bool
	forbiddenWhen   bool
	forbiddenUnless bool
	referenceField  string
	expectedValue   string
}

func parseRequestConditionalConstraint(
	raw string,
) (requestConditionalConstraint, bool, error) {
	constraint := requestConditionalConstraint{}
	value := strings.TrimSpace(raw)
	var remainder string
	switch {
	case strings.HasPrefix(value, "REQUIRED_WHEN_"):
		constraint.requiredWhen = true
		remainder = strings.TrimPrefix(value, "REQUIRED_WHEN_")
	case strings.HasPrefix(value, "FORBIDDEN_UNLESS_"):
		constraint.forbiddenUnless = true
		remainder = strings.TrimPrefix(value, "FORBIDDEN_UNLESS_")
	case strings.HasPrefix(value, "FORBIDDEN_WHEN_"):
		constraint.forbiddenWhen = true
		remainder = strings.TrimPrefix(value, "FORBIDDEN_WHEN_")
	default:
		return requestConditionalConstraint{}, false, nil
	}
	parts := strings.SplitN(remainder, "_", 2)
	if len(parts) != 2 || strings.TrimSpace(parts[0]) == "" ||
		strings.TrimSpace(parts[1]) == "" {
		return requestConditionalConstraint{}, true, fmt.Errorf(
			"conditional request constraint %q must be <kind>_<field>_<canonical-value>",
			raw,
		)
	}
	constraint.referenceField = strings.TrimSpace(parts[0])
	constraint.expectedValue = strings.TrimSpace(parts[1])
	return constraint, true, nil
}

func renderRequestConditionalValidations(
	output *strings.Builder,
	model requestModelSpec,
	enumValues map[string][]string,
) error {
	fields := make(map[string]fieldDef, len(model.Fields))
	for _, field := range model.Fields {
		fields[field.Name] = field
	}
	for _, field := range model.Fields {
		if !isRequestFieldNullable(field) {
			for _, raw := range field.Constraints {
				if _, conditional, err := parseRequestConditionalConstraint(raw); err != nil {
					return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
				} else if conditional {
					return fmt.Errorf(
						"%s.%s conditional presence constraint requires a nullable field",
						model.Name,
						field.Name,
					)
				}
			}
		}
		for _, raw := range field.Constraints {
			constraint, conditional, err := parseRequestConditionalConstraint(raw)
			if err != nil {
				return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
			}
			if !conditional {
				continue
			}
			reference, exists := fields[constraint.referenceField]
			if !exists {
				return fmt.Errorf(
					"%s.%s conditional constraint references missing field %s",
					model.Name,
					field.Name,
					constraint.referenceField,
				)
			}
			expected, err := requestConditionExpectedExpression(
				reference,
				constraint.expectedValue,
				enumValues,
			)
			if err != nil {
				return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
			}
			referenceAccess := "this." + requestFieldDartName(reference)
			targetName := requestFieldDartName(field)
			targetAccess := "this." + targetName
			condition := ""
			message := ""
			switch {
			case constraint.requiredWhen:
				condition = referenceAccess + " == " + expected + " && " + targetAccess + " == null"
				message = "is required when " + constraint.referenceField + " is " + constraint.expectedValue
			case constraint.forbiddenWhen:
				condition = referenceAccess + " == " + expected + " && " + targetAccess + " != null"
				message = "is forbidden when " + constraint.referenceField + " is " + constraint.expectedValue
			case constraint.forbiddenUnless:
				condition = referenceAccess + " != " + expected + " && " + targetAccess + " != null"
				message = "is forbidden unless " + constraint.referenceField + " is " + constraint.expectedValue
			}
			fmt.Fprintf(output, "    if (%s) {\n", condition)
			fmt.Fprintf(
				output,
				"      throw ArgumentError.value(%s, %q, %q);\n",
				targetAccess,
				targetName,
				message,
			)
			output.WriteString("    }\n")
		}
	}
	return nil
}

func requestConditionExpectedExpression(
	field fieldDef,
	expected string,
	enumValues map[string][]string,
) (string, error) {
	dartType, _, err := requestFieldDartType(field)
	if err != nil {
		return "", err
	}
	baseType := strings.TrimSuffix(dartType, "?")
	values := enumValues[strings.TrimSpace(field.EnumRef)]
	if len(values) > 0 {
		members, err := canonicalRequestEnumMembers(field, values)
		if err != nil {
			return "", err
		}
		for _, member := range members {
			if member.WireValue == expected {
				return baseType + "." + member.DartMember, nil
			}
		}
		return "", fmt.Errorf(
			"conditional constraint references unknown %s value %q",
			field.EnumRef,
			expected,
		)
	}
	switch baseType {
	case "String":
		return strconv.Quote(expected), nil
	case "bool", "boolean":
		if expected == "true" || expected == "false" {
			return expected, nil
		}
	case "int", "double":
		if _, err := strconv.ParseFloat(expected, 64); err == nil {
			return expected, nil
		}
	}
	return "", fmt.Errorf(
		"conditional constraint cannot encode %s value %q",
		baseType,
		expected,
	)
}

func renderRequestEncoder(
	output *strings.Builder,
	operation requestOperationSpec,
	model requestModelSpec,
	enumValues map[string][]string,
) error {
	fields := make(map[string]fieldDef, len(model.Fields))
	for _, field := range model.Fields {
		fields[field.Name] = field
	}
	encoder := generatedOperationRequestEncoder(operation.CanonicalOperationID)
	fmt.Fprintf(
		output,
		"CloudOperationRequestPayload %s(%s request) {\n",
		encoder,
		operation.RequestType,
	)
	output.WriteString("  return CloudOperationRequestPayload(\n")
	for _, group := range []struct {
		property string
		values   []appRequestBinding
	}{
		{property: "pathParameters", values: operation.RequestBindings.Path},
		{property: "queryParameters", values: operation.RequestBindings.Query},
		{property: "headers", values: operation.RequestBindings.Header},
	} {
		if len(group.values) == 0 {
			continue
		}
		fmt.Fprintf(output, "    %s: <String, String>{\n", group.property)
		for _, binding := range group.values {
			field := fields[binding.Field]
			dartName := requestFieldDartName(field)
			value, err := requestFieldWireExpression(
				"request."+dartName,
				field,
				true,
				enumValues,
			)
			if err != nil {
				return err
			}
			if isRequestFieldNullable(field) || field.ClientOmitEmpty {
				condition := "request." + dartName + " != null"
				if field.ClientOmitEmpty {
					if isRequestFieldNullable(field) {
						condition = "request." + dartName + "?.isNotEmpty == true"
					} else {
						condition = "request." + dartName + ".isNotEmpty"
					}
				}
				fmt.Fprintf(
					output,
					"      if (%s) %q: %s,\n",
					condition,
					binding.Name,
					value,
				)
			} else {
				fmt.Fprintf(
					output,
					"      %q: %s,\n",
					binding.Name,
					value,
				)
			}
		}
		output.WriteString("    },\n")
	}
	if operation.RequestBodyKind == "object" {
		bound := map[string]struct{}{}
		for _, values := range [][]appRequestBinding{
			operation.RequestBindings.Path,
			operation.RequestBindings.Query,
			operation.RequestBindings.Header,
			operation.RequestBindings.Injected,
		} {
			for _, binding := range values {
				bound[binding.Field] = struct{}{}
			}
		}
		output.WriteString("    body: <String, Object?>{\n")
		for _, field := range model.Fields {
			if _, exists := bound[field.Name]; exists {
				continue
			}
			dartName := requestFieldDartName(field)
			value, err := requestFieldWireExpression(
				"request."+dartName,
				field,
				false,
				enumValues,
			)
			if err != nil {
				return err
			}
			if field.ClientSpreadBody {
				fmt.Fprintf(output, "      ...%s,\n", value)
				continue
			}
			if isRequestFieldNullable(field) ||
				field.ClientOmitEmpty {
				condition := "request." + dartName + " != null"
				if field.ClientOmitEmpty {
					if isRequestFieldNullable(field) {
						condition = "request." + dartName + "?.isNotEmpty == true"
					} else {
						condition = "request." + dartName + ".isNotEmpty"
					}
				}
				fmt.Fprintf(
					output,
					"      if (%s) %q: %s,\n",
					condition,
					requestFieldWireName(field),
					value,
				)
			} else {
				fmt.Fprintf(
					output,
					"      %q: %s,\n",
					requestFieldWireName(field),
					value,
				)
			}
		}
		for _, constant := range operation.RequestConstants.Body {
			value, err := dartRequestConstant(constant.Value)
			if err != nil {
				return err
			}
			fmt.Fprintf(output, "      %q: %s,\n", constant.Name, value)
		}
		output.WriteString("    },\n")
	}
	output.WriteString("  );\n")
	output.WriteString("}\n\n")
	return nil
}

func dartRequestConstant(value any) (string, error) {
	switch typed := value.(type) {
	case nil:
		return "null", nil
	case string:
		return strconv.Quote(typed), nil
	case bool:
		return strconv.FormatBool(typed), nil
	case int:
		return strconv.Itoa(typed), nil
	case int8:
		return strconv.FormatInt(int64(typed), 10), nil
	case int16:
		return strconv.FormatInt(int64(typed), 10), nil
	case int32:
		return strconv.FormatInt(int64(typed), 10), nil
	case int64:
		return strconv.FormatInt(typed, 10), nil
	case uint:
		return strconv.FormatUint(uint64(typed), 10), nil
	case uint8:
		return strconv.FormatUint(uint64(typed), 10), nil
	case uint16:
		return strconv.FormatUint(uint64(typed), 10), nil
	case uint32:
		return strconv.FormatUint(uint64(typed), 10), nil
	case uint64:
		return strconv.FormatUint(typed, 10), nil
	case float32:
		return strconv.FormatFloat(float64(typed), 'g', -1, 32), nil
	case float64:
		return strconv.FormatFloat(typed, 'g', -1, 64), nil
	default:
		return "", fmt.Errorf("unsupported non-scalar %T", value)
	}
}

func requestFieldWireExpression(
	access string,
	field fieldDef,
	stringPosition bool,
	enumValues map[string][]string,
) (string, error) {
	nullable := isRequestFieldNullable(field)
	nonNullAccess := access
	if nullable {
		nonNullAccess += "!"
	}
	mode := strings.TrimSpace(field.ClientWire)
	metaType := strings.TrimSpace(field.Type)
	if stringPosition && strings.HasPrefix(metaType, "[]") && mode != "uri_csv" {
		return "", fmt.Errorf(
			"field %s requires canonical client_wire uri_csv in a string wire position",
			field.Name,
		)
	}
	if mode == "quoted" {
		return `'"${` + nonNullAccess + `}"'`, nil
	}
	if mode == "uri_csv" {
		return nonNullAccess +
			".map(Uri.encodeQueryComponent).join(',')", nil
	}
	dartType, _, err := requestFieldDartType(field)
	if err != nil {
		return "", err
	}
	baseDartType := strings.TrimSuffix(dartType, "?")
	var result string
	switch {
	case strings.HasPrefix(metaType, "[]"):
		if mode == "mapToWire" {
			result = nonNullAccess +
				".map((value) => value.toWire()).toList(growable: false)"
			break
		}
		item := field
		item.Type = strings.TrimPrefix(metaType, "[]")
		item.ClientDartType = listItemDartType(baseDartType)
		item.Constraints = nil
		item.ClientDefault = ""
		item.ClientOmitEmpty = false
		item.ClientSpreadBody = false
		itemExpression, itemErr := requestFieldWireExpression(
			"value",
			item,
			false,
			enumValues,
		)
		if itemErr != nil {
			return "", itemErr
		}
		result = nonNullAccess +
			".map((value) => " + itemExpression +
			").toList(growable: false)"
	case mode == "wire":
		result = nonNullAccess + ".wire"
	case mode == "wireValue":
		result = nonNullAccess + ".wireValue"
	case mode == "wireName":
		result = nonNullAccess + ".wireName"
	case mode == "name":
		result = nonNullAccess + ".name"
	case mode == "toWire":
		result = nonNullAccess + ".toWire()"
	case mode == "toMap":
		result, err = requestInlineObjectWireExpression(
			nonNullAccess,
			baseDartType,
		)
		if err != nil {
			return "", err
		}
	case mode == "toWireMap":
		result = nonNullAccess + ".toWireMap()"
	case mode == "toJson":
		result = nonNullAccess + ".toJson()"
	case mode == "toApiString":
		result = nonNullAccess + ".toApiString()"
	case mode == "canonicalEnum":
		if baseDartType == "String" {
			return "", fmt.Errorf(
				"field %s canonicalEnum requires a typed Dart enum",
				field.Name,
			)
		}
		enumRef := strings.TrimSpace(field.EnumRef)
		if enumRef == "" {
			enumRef = strings.TrimSpace(field.Type)
		}
		values := enumValues[enumRef]
		if len(values) == 0 {
			return "", fmt.Errorf(
				"field %s canonicalEnum enum_ref %s has no canonical values",
				field.Name,
				enumRef,
			)
		}
		members, err := canonicalRequestEnumMembers(field, values)
		if err != nil {
			return "", err
		}
		cases := make([]string, 0, len(members))
		for _, member := range members {
			cases = append(
				cases,
				baseDartType+"."+member.DartMember+" => "+
					strconv.Quote(member.WireValue),
			)
		}
		result = "switch (" + nonNullAccess + ") { " +
			strings.Join(cases, ", ") + ", }"
	case mode == "nullableMutationWireValue":
		result = "_encodeGeneratedNullableMutation(" + nonNullAccess +
			", (value) => value.wireValue)"
	case mode == "structuredValue":
		result = "_encodeGeneratedStructuredValue(" + nonNullAccess + ")"
	case metaType == "timestamp" || metaType == "datetime" || metaType == "date":
		result = nonNullAccess + ".toUtc().toIso8601String()"
	case metaType == "enum" && baseDartType == "String":
		result = nonNullAccess
	case metaType == "enum":
		values := enumValues[strings.TrimSpace(field.EnumRef)]
		if len(values) == 0 {
			return "", fmt.Errorf(
				"enum_ref %s has no canonical values",
				field.EnumRef,
			)
		}
		result = nonNullAccess + "." + canonicalEnumWireGetter(field.EnumRef)
	case baseDartType == "String" || baseDartType == "int" ||
		baseDartType == "double" || baseDartType == "bool" ||
		strings.HasPrefix(baseDartType, "Map<"):
		result = nonNullAccess
	default:
		// Non-scalar request dependencies either remain in this generated
		// library or are package-owned value objects selected by client_dart_type.
		// Both own one canonical toWire encoder, so a per-field marker would
		// duplicate type information already carried by the request graph.
		result = nonNullAccess + ".toWire()"
	}
	if stringPosition &&
		baseDartType != "String" &&
		mode != "uri_csv" &&
		mode != "quoted" {
		result = "(" + result + ").toString()"
	}
	return result, nil
}

func canonicalEnumWireGetter(enumRef string) string {
	switch strings.TrimSpace(enumRef) {
	case "CanonicalSearchMode", "SearchFeedbackEventType":
		return "wireValue"
	default:
		return "wireName"
	}
}

func requestInlineObjectWireExpression(
	access string,
	dartType string,
) (string, error) {
	switch dartType {
	case "CircleSectionConfigInput":
		return "<String, Object?>{" +
			"'sectionType': " + access + ".sectionType, " +
			"'visible': " + access + ".visible, " +
			"'order': " + access + ".order, " +
			"if (" + access + ".customTitle != null) " +
			"'customTitle': " + access + ".customTitle" +
			"}", nil
	case "ContentCommentMention":
		return "<String, Object?>{" +
			"'subjectType': " + access + ".subjectType, " +
			"'subjectId': " + access + ".subjectId, " +
			"if (" + access + ".displayName != null) " +
			"'displayName': " + access + ".displayName" +
			"}", nil
	case "ChatMessageCardCommand":
		return "<String, Object?>{" +
			"'kind': " + access + ".kind, " +
			"'title': " + access + ".title, " +
			"if (" + access + ".objectRef != null) 'objectRef': " + access + ".objectRef!.toWire(), " +
			"if (" + access + ".subtitle != null) 'subtitle': " + access + ".subtitle, " +
			"if (" + access + ".thumbnailUrl != null) 'thumbnailUrl': " + access + ".thumbnailUrl, " +
			"if (" + access + ".deeplink != null) 'deeplink': " + access + ".deeplink, " +
			"if (" + access + ".landingUrl != null) 'landingUrl': " + access + ".landingUrl, " +
			"if (" + access + ".shareText != null) 'shareText': " + access + ".shareText, " +
			"if (" + access + ".message != null) 'message': " + access + ".message, " +
			"'attributes': <Map<String, String>>[" +
			"for (final attribute in " + access + ".attributes) " +
			"<String, String>{'name': attribute.name, 'value': attribute.value}" +
			"]" +
			"}", nil
	default:
		return "", fmt.Errorf(
			"client_wire=toMap has no ContractGraph-owned field projection for %s",
			dartType,
		)
	}
}

func listItemDartType(value string) string {
	if strings.HasPrefix(value, "List<") && strings.HasSuffix(value, ">") {
		return strings.TrimSuffix(strings.TrimPrefix(value, "List<"), ">")
	}
	return ""
}

func loadCanonicalRequestEnumValues() (map[string][]string, error) {
	if activeMetadataSource == nil {
		return nil, fmt.Errorf("ContractGraph is not initialized")
	}
	result := map[string][]string{}
	for _, relative := range activeMetadataSource.Paths("", ".yaml") {
		var document struct {
			Enums any `yaml:"enums"`
		}
		if err := activeMetadataSource.Decode(relative, &document); err != nil {
			return nil, fmt.Errorf("decode enum catalog %s: %w", relative, err)
		}
		for name, raw := range normalizeRequestEnumCatalog(document.Enums) {
			values := normalizeRequestEnumValues(raw)
			if len(values) == 0 {
				continue
			}
			if previous, exists := result[name]; exists &&
				strings.Join(previous, "\x00") != strings.Join(values, "\x00") {
				return nil, fmt.Errorf(
					"canonical enum %s has conflicting values",
					name,
				)
			}
			result[name] = values
		}
	}
	return result, nil
}

func normalizeRequestEnumCatalog(raw any) map[string]any {
	result := map[string]any{}
	switch values := raw.(type) {
	case map[string]any:
		for name, value := range values {
			result[name] = value
		}
	case []any:
		for _, item := range values {
			definition, ok := item.(map[string]any)
			if !ok {
				continue
			}
			name := strings.TrimSpace(fmt.Sprint(definition["name"]))
			if name != "" {
				result[name] = definition["values"]
			}
		}
	}
	return result
}

func normalizeRequestEnumValues(raw any) []string {
	switch value := raw.(type) {
	case []any:
		result := make([]string, 0, len(value))
		for _, item := range value {
			text := ""
			if definition, ok := item.(map[string]any); ok {
				text = strings.TrimSpace(fmt.Sprint(definition["wire"]))
				if text == "" {
					text = strings.TrimSpace(fmt.Sprint(definition["name"]))
				}
			} else {
				text = strings.TrimSpace(fmt.Sprint(item))
			}
			if text != "" {
				result = append(result, text)
			}
		}
		return result
	case map[string]any:
		return normalizeRequestEnumValues(value["values"])
	}
	return nil
}

func hasRequestConstraint(field fieldDef, expected string) bool {
	for _, value := range field.Constraints {
		if strings.TrimSpace(value) == expected {
			return true
		}
	}
	return false
}

func isRequestFieldNullable(field fieldDef) bool {
	return hasRequestConstraint(field, "NULLABLE") ||
		strings.HasSuffix(strings.TrimSpace(field.ClientDartType), "?")
}

func isRequestNumericField(field fieldDef) bool {
	switch strings.TrimSpace(field.Type) {
	case "int", "int32", "int64", "long", "float", "float32", "float64", "double":
		return true
	default:
		return false
	}
}

func quotedDartValues(values []string) string {
	quoted := make([]string, 0, len(values))
	for _, value := range values {
		quoted = append(quoted, strconv.Quote(value))
	}
	return strings.Join(quoted, ", ")
}
