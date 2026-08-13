package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

func renderRequestModel(
	output *strings.Builder,
	model requestModelSpec,
	enumValues map[string][]string,
) error {
	if model.DerivedSource != "" {
		fmt.Fprintf(
			output,
			"// Derived from %s; source SHA256: %s.\n",
			model.DerivedSource,
			model.DerivedSHA256,
		)
	}
	fmt.Fprintf(output, "final class %s {\n", model.Name)
	if len(model.Fields) == 0 {
		fmt.Fprintf(output, "  const %s();\n", model.Name)
		output.WriteString("}\n\n")
		return nil
	}
	if model.Pagination != nil {
		if strings.TrimSpace(model.Pagination.Field) == "" ||
			model.Pagination.DefaultItems <= 0 ||
			model.Pagination.MaximumItems < model.Pagination.DefaultItems {
			return fmt.Errorf("%s has invalid generated pagination constants", model.Name)
		}
		paginationFieldFound := false
		for _, field := range model.Fields {
			if strings.TrimSpace(field.Name) != model.Pagination.Field {
				continue
			}
			if !isRequestNumericField(field) {
				return fmt.Errorf(
					"%s pagination field %s must be numeric",
					model.Name,
					model.Pagination.Field,
				)
			}
			paginationFieldFound = true
			break
		}
		if !paginationFieldFound {
			return fmt.Errorf(
				"%s pagination field %s is absent from generated request model",
				model.Name,
				model.Pagination.Field,
			)
		}
		fmt.Fprintf(
			output,
			"  static const int defaultLimit = %d;\n"+
				"  static const int maximumLimit = %d;\n\n",
			model.Pagination.DefaultItems,
			model.Pagination.MaximumItems,
		)
	}
	initializers := make([]string, 0, len(model.Fields))
	allInitializersAreConstSafe := true
	var validation strings.Builder
	for _, field := range model.Fields {
		initializer, err := requestFieldInitializer(field)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
		}
		dartName := requestFieldDartName(field)
		initializers = append(initializers, fmt.Sprintf("%s = %s", dartName, initializer))
		allInitializersAreConstSafe = allInitializersAreConstSafe && initializer == dartName
		if err := renderRequestFieldValidation(
			&validation,
			model.Name,
			field,
			enumValues,
		); err != nil {
			return err
		}
	}
	if err := renderRequestConditionalValidations(
		&validation,
		model,
		enumValues,
	); err != nil {
		return err
	}
	if err := renderDerivedRequestModelValidation(&validation, model); err != nil {
		return err
	}
	constSafe := allInitializersAreConstSafe && validation.Len() == 0
	constructorPrefix := ""
	if constSafe {
		constructorPrefix = "const "
	}
	fmt.Fprintf(output, "  %s%s({\n", constructorPrefix, model.Name)
	for _, field := range model.Fields {
		dartType, nullable, err := requestFieldDartType(field)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
		}
		parameterType := requestFieldParameterType(field, dartType)
		dartName := requestFieldDartName(field)
		defaultValue := requestFieldDefault(field)
		switch {
		case defaultValue != "":
			fmt.Fprintf(
				output,
				"    %s %s = %s,\n",
				parameterType,
				dartName,
				defaultValue,
			)
		case nullable:
			fmt.Fprintf(output, "    %s %s,\n", parameterType, dartName)
		default:
			fmt.Fprintf(output, "    required %s %s,\n", parameterType, dartName)
		}
	}
	output.WriteString("  })")
	output.WriteString(" : ")
	output.WriteString(strings.Join(initializers, ",\n       "))
	if constSafe {
		output.WriteString(";\n\n")
	} else {
		output.WriteString(" {\n")
		output.WriteString(validation.String())
		output.WriteString("  }\n\n")
	}
	for _, field := range model.Fields {
		dartType, _, err := requestFieldDartType(field)
		if err != nil {
			return err
		}
		fmt.Fprintf(
			output,
			"  final %s %s;\n",
			dartType,
			requestFieldDartName(field),
		)
		recordEnumFieldBinding(enumFieldBinding{
			DartClass:      model.Name,
			DartField:      requestFieldDartName(field),
			DartType:       dartType,
			EnumRef:        field.EnumRef,
			ContractType:   field.Type,
			ContractSource: model.DerivedSource,
			ClientDartType: field.ClientDartType,
		})
	}
	if requestModelSupportsWireDecoder(model) {
		fmt.Fprintf(
			output,
			"\n  factory %s.fromWire(Map<String, Object?> map, [String path = %q]) {\n",
			model.Name,
			model.Name,
		)
		output.WriteString("    _generatedRequestRejectUnknownFields(map, const <String>{")
		for index, field := range model.Fields {
			if index > 0 {
				output.WriteString(", ")
			}
			fmt.Fprintf(output, "%q", requestFieldWireName(field))
		}
		output.WriteString("}, path);\n")
		fmt.Fprintf(output, "    return %s(\n", model.Name)
		for _, field := range model.Fields {
			expression, err := requestFieldFromWireExpression(
				fmt.Sprintf("map[%q]", requestFieldWireName(field)),
				fmt.Sprintf("'$path.%s'", requestFieldWireName(field)),
				field,
				enumValues,
			)
			if err != nil {
				return fmt.Errorf("%s.%s decoder: %w", model.Name, field.Name, err)
			}
			if defaultValue := requestFieldDefault(field); defaultValue != "" {
				expression = fmt.Sprintf(
					"map.containsKey(%q) ? %s : %s",
					requestFieldWireName(field),
					expression,
					defaultValue,
				)
			}
			fmt.Fprintf(
				output,
				"      %s: %s,\n",
				requestFieldDartName(field),
				expression,
			)
		}
		output.WriteString("    );\n")
		output.WriteString("  }\n")
	}
	output.WriteString("\n  Map<String, Object?> toWire() => <String, Object?>{\n")
	for _, field := range model.Fields {
		dartName := requestFieldDartName(field)
		value, err := requestFieldWireExpression(
			"this."+dartName,
			field,
			false,
			enumValues,
		)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
		}
		if isRequestFieldNullable(field) || field.ClientOmitEmpty {
			condition := "this." + dartName + " != null"
			if field.ClientOmitEmpty {
				if isRequestFieldNullable(field) {
					condition = "this." + dartName + "?.isNotEmpty == true"
				} else {
					condition = "this." + dartName + ".isNotEmpty"
				}
			}
			fmt.Fprintf(
				output,
				"    if (%s) %q: %s,\n",
				condition,
				requestFieldWireName(field),
				value,
			)
		} else {
			fmt.Fprintf(
				output,
				"    %q: %s,\n",
				requestFieldWireName(field),
				value,
			)
		}
	}
	output.WriteString("  };\n")
	output.WriteString("}\n\n")
	return nil
}

func renderDerivedRequestModelValidation(
	output *strings.Builder,
	model requestModelSpec,
) error {
	switch model.ValidationKind {
	case "":
		return nil
	case requestValidationProductOpsEventRecord:
		var catalog telemetryEventCatalogFile
		path := filepath.Join(
			activeMetadataRoot,
			"ops",
			"product_ops",
			"event_record",
			"event_catalog.yaml",
		)
		if err := decodeMetadataDocument(path, &catalog); err != nil {
			return fmt.Errorf("%s load event catalog validation: %w", model.Name, err)
		}
		renderProductOpsEventRecordValidation(output, catalog)
		return nil
	case requestValidationRuntimeLogRecord:
		var catalog runtimeObservabilityContract
		path := filepath.Join(activeMetadataRoot, "_shared", "runtime_observability.yaml")
		if err := decodeMetadataDocument(path, &catalog); err != nil {
			return fmt.Errorf("%s load runtime observability validation: %w", model.Name, err)
		}
		renderRuntimeLogRecordValidation(output, catalog)
		return nil
	default:
		return fmt.Errorf("%s has unknown derived request validation %q", model.Name, model.ValidationKind)
	}
}

func renderProductOpsEventRecordValidation(
	output *strings.Builder,
	catalog telemetryEventCatalogFile,
) {
	output.WriteString("    final definition = switch (this.eventType) {\n")
	for _, event := range catalog.Events {
		allowed := append([]string(nil), event.RequiredExtensions...)
		allowed = append(allowed, event.OptionalExtensions...)
		allowed = append(allowed, catalog.ContextExtensions...)
		allowed = sortedUniqueStrings(allowed)
		required := sortedUniqueStrings(event.RequiredExtensions)
		fmt.Fprintf(
			output,
			"      %q => (logType: %q, required: const <String>{%s}, allowed: const <String>{%s}),\n",
			event.EventType,
			event.LogType,
			quotedDartValues(required),
			quotedDartValues(allowed),
		)
	}
	output.WriteString("      _ => throw ArgumentError.value(this.eventType, 'eventType', 'unknown canonical event'),\n")
	output.WriteString("    };\n")
	output.WriteString("    if (this.logType != definition.logType) {\n")
	output.WriteString("      throw ArgumentError.value(this.logType, 'logType', 'does not match eventType');\n")
	output.WriteString("    }\n")
	output.WriteString("    final presentExtensions = <String>{\n")
	extensionNames := make([]string, 0, len(catalog.ExtensionFields))
	for name := range catalog.ExtensionFields {
		extensionNames = append(extensionNames, name)
	}
	sort.Strings(extensionNames)
	for _, name := range extensionNames {
		fmt.Fprintf(output, "      if (this.%s != null) %q,\n", name, name)
	}
	output.WriteString("    };\n")
	output.WriteString("    if (!definition.required.every(presentExtensions.contains)) {\n")
	output.WriteString("      throw ArgumentError.value(presentExtensions, 'extensions', 'missing required event extension');\n")
	output.WriteString("    }\n")
	output.WriteString("    if (!presentExtensions.every(definition.allowed.contains)) {\n")
	output.WriteString("      throw ArgumentError.value(presentExtensions, 'extensions', 'event contains forbidden extension');\n")
	output.WriteString("    }\n")
	for _, name := range extensionNames {
		extension := catalog.ExtensionFields[name]
		if len(extension.Enum) > 0 {
			fmt.Fprintf(
				output,
				"    if (this.%s != null && !const <String>{%s}.contains(this.%s)) {\n",
				name,
				quotedDartValues(extension.Enum),
				name,
			)
			fmt.Fprintf(
				output,
				"      throw ArgumentError.value(this.%s, %q, 'unsupported event extension value');\n",
				name,
				name,
			)
			output.WriteString("    }\n")
		}
		if extension.Type == "string_list" && extension.ItemMaxLength > 0 {
			fmt.Fprintf(
				output,
				"    if (this.%s?.any((value) => value.length > %d) == true) {\n",
				name,
				extension.ItemMaxLength,
			)
			fmt.Fprintf(
				output,
				"      throw ArgumentError.value(this.%s, %q, 'event extension item is too long');\n",
				name,
				name,
			)
			output.WriteString("    }\n")
		}
	}
}

func renderRuntimeLogRecordValidation(
	output *strings.Builder,
	catalog runtimeObservabilityContract,
) {
	fmt.Fprintf(output, "    if (this.schema != %q) {\n", catalog.Schema)
	output.WriteString("      throw ArgumentError.value(this.schema, 'schema', 'unsupported runtime log schema');\n")
	output.WriteString("    }\n")
	fmt.Fprintf(
		output,
		"    if (!const <String>{%s}.contains(this.logKind)) {\n",
		quotedDartValues(catalog.LogKinds),
	)
	output.WriteString("      throw ArgumentError.value(this.logKind, 'logKind', 'unsupported runtime log kind');\n")
	output.WriteString("    }\n")
	fmt.Fprintf(
		output,
		"    if (!const <String>{%s}.contains(this.severity)) {\n",
		quotedDartValues(catalog.SeverityLevels),
	)
	output.WriteString("      throw ArgumentError.value(this.severity, 'severity', 'unsupported runtime log severity');\n")
	output.WriteString("    }\n")
	output.WriteString("    final signalPolicy = switch (this.signal) {\n")
	for _, signal := range catalog.Signals {
		fmt.Fprintf(
			output,
			"      %q => (logKind: %q, attributes: const <String>{%s}, correlation: const <String>{%s}),\n",
			signal.ID,
			signal.LogKind,
			quotedDartValues(sortedUniqueStrings(signal.AttributeAllowlist)),
			quotedDartValues(sortedUniqueStrings(signal.CorrelationKeys)),
		)
	}
	output.WriteString("      _ => throw ArgumentError.value(this.signal, 'signal', 'unknown runtime log signal'),\n")
	output.WriteString("    };\n")
	output.WriteString("    if (signalPolicy.logKind != this.logKind) {\n")
	output.WriteString("      throw ArgumentError.value(this.signal, 'signal', 'does not match logKind');\n")
	output.WriteString("    }\n")
	output.WriteString("    final attributeKeys = this.attributes?.toWire().keys ?? const <String>[];\n")
	output.WriteString("    if (!attributeKeys.every(signalPolicy.attributes.contains)) {\n")
	output.WriteString("      throw ArgumentError.value(attributeKeys, 'attributes', 'contains fields outside signal policy');\n")
	output.WriteString("    }\n")
	output.WriteString("    final correlationKeys = this.correlation?.toWire().keys ?? const <String>[];\n")
	output.WriteString("    if (!correlationKeys.every(signalPolicy.correlation.contains)) {\n")
	output.WriteString("      throw ArgumentError.value(correlationKeys, 'correlation', 'contains fields outside signal policy');\n")
	output.WriteString("    }\n")
	output.WriteString("    final presentKindFields = <String>{\n")
	optionalNames := []string{"step", "event", "result", "method", "route", "status", "durationMs", "action", "target", "errorCode"}
	for _, name := range optionalNames {
		fmt.Fprintf(output, "      if (this.%s != null) %q,\n", name, name)
	}
	output.WriteString("    };\n")
	output.WriteString("    final requiredKindFields = switch (this.logKind) {\n")
	for _, kind := range catalog.LogKinds {
		fmt.Fprintf(
			output,
			"      %q => const <String>{%s},\n",
			kind,
			quotedDartValues(sortedUniqueStrings(catalog.KindFields[kind].Required)),
		)
	}
	output.WriteString("      _ => const <String>{},\n")
	output.WriteString("    };\n")
	output.WriteString("    if (!requiredKindFields.every(presentKindFields.contains)) {\n")
	output.WriteString("      throw ArgumentError.value(presentKindFields, 'logKind', 'missing required runtime log fields');\n")
	output.WriteString("    }\n")
	if catalog.Limits.MaxAttributes > 0 {
		fmt.Fprintf(
			output,
			"    if (attributeKeys.length > %d) {\n",
			catalog.Limits.MaxAttributes,
		)
		output.WriteString("      throw ArgumentError.value(attributeKeys.length, 'attributes', 'too many runtime log attributes');\n")
		output.WriteString("    }\n")
	}
}

func sortedUniqueStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func requestModelSupportsWireDecoder(model requestModelSpec) bool {
	for _, field := range model.Fields {
		switch strings.TrimSpace(field.ClientWire) {
		case "", "quoted", "uri_csv", "wire", "wireValue", "wireName", "name", "toWire", "mapToWire", "canonicalEnum":
			continue
		default:
			return false
		}
	}
	return true
}

func requestFieldFromWireExpression(
	access string,
	pathExpression string,
	field fieldDef,
	enumValues map[string][]string,
) (string, error) {
	if isRequestFieldNullable(field) {
		required := field
		required.ClientDartType = strings.TrimSuffix(
			strings.TrimSpace(required.ClientDartType),
			"?",
		)
		required.ClientParameterType = strings.TrimSuffix(
			strings.TrimSpace(required.ClientParameterType),
			"?",
		)
		required.Constraints = make([]string, 0, len(field.Constraints))
		for _, constraint := range field.Constraints {
			if constraint != "NULLABLE" {
				required.Constraints = append(required.Constraints, constraint)
			}
		}
		expression, err := requestFieldFromWireExpression(
			access,
			pathExpression,
			required,
			enumValues,
		)
		if err != nil {
			return "", err
		}
		return access + " == null ? null : " + expression, nil
	}

	dartType, _, err := requestFieldDartType(field)
	if err != nil {
		return "", err
	}
	baseDartType := strings.TrimSuffix(dartType, "?")
	metaType := strings.TrimSpace(field.Type)
	mode := strings.TrimSpace(field.ClientWire)
	if strings.HasPrefix(metaType, "[]") {
		if mode == "uri_csv" {
			return "List<String>.unmodifiable(_generatedRequestString(" + access + ", " + pathExpression + ").split(',').where((value) => value.isNotEmpty).map(Uri.decodeQueryComponent))", nil
		}
		item := field
		item.Type = strings.TrimPrefix(metaType, "[]")
		item.ClientDartType = listItemDartType(baseDartType)
		item.ClientParameterType = ""
		item.ClientDefault = ""
		item.ClientOmitEmpty = false
		item.ClientSpreadBody = false
		item.Constraints = nil
		if mode == "mapToWire" {
			item.ClientWire = "toWire"
		}
		itemExpression, itemErr := requestFieldFromWireExpression(
			"entry.value",
			pathExpression+" + '[${entry.key}]'",
			item,
			enumValues,
		)
		if itemErr != nil {
			return "", itemErr
		}
		return "List<" + strings.TrimSuffix(item.ClientDartType, "?") + ">.unmodifiable(_generatedRequestList(" + access + ", " + pathExpression + ").asMap().entries.map((entry) => " + itemExpression + "))", nil
	}

	switch mode {
	case "quoted":
		if baseDartType == "int" {
			return "int.parse(_generatedRequestString(" + access + ", " + pathExpression + "))", nil
		}
		return "", fmt.Errorf("quoted decoder does not support %s", baseDartType)
	case "wire", "wireValue", "wireName", "name", "canonicalEnum":
		return requestEnumFromWireExpression(
			baseDartType,
			access,
			pathExpression,
			field,
			enumValues,
		)
	case "toWire":
		return baseDartType + ".fromWire(_generatedRequestObject(" + access + ", " + pathExpression + "), " + pathExpression + ")", nil
	}

	switch metaType {
	case "string", "tag_ref", "time", "ObjectId", "uuid", "identifier":
		if baseDartType != "String" {
			return baseDartType + ".fromWire(" + access + ", " + pathExpression + ")", nil
		}
		return "_generatedRequestString(" + access + ", " + pathExpression + ")", nil
	case "int", "int32", "int64", "long":
		return "_generatedRequestInt(" + access + ", " + pathExpression + ")", nil
	case "float", "float32", "float64", "double":
		return "_generatedRequestDouble(" + access + ", " + pathExpression + ")", nil
	case "bool", "boolean":
		return "_generatedRequestBool(" + access + ", " + pathExpression + ")", nil
	case "timestamp", "datetime", "date":
		return "_generatedRequestTimestamp(" + access + ", " + pathExpression + ")", nil
	case "enum":
		if baseDartType == "String" {
			return "_generatedRequestString(" + access + ", " + pathExpression + ")", nil
		}
		if len(enumValues[strings.TrimSpace(field.EnumRef)]) == 0 {
			return "", fmt.Errorf("enum_ref %s has no canonical values", field.EnumRef)
		}
		return requestEnumFromWireExpression(
			baseDartType,
			access,
			pathExpression,
			field,
			enumValues,
		)
	case "object", "json", "jsonb":
		if strings.HasPrefix(baseDartType, "Map<") {
			return "_generatedRequestObject(" + access + ", " + pathExpression + ")", nil
		}
	}
	if baseDartType == "String" {
		return "_generatedRequestString(" + access + ", " + pathExpression + ")", nil
	}
	return baseDartType + ".fromWire(_generatedRequestObject(" + access + ", " + pathExpression + "), " + pathExpression + ")", nil
}

func requestEnumFromWireExpression(
	dartType string,
	access string,
	pathExpression string,
	field fieldDef,
	enumValues map[string][]string,
) (string, error) {
	values := enumValues[strings.TrimSpace(field.EnumRef)]
	if len(values) == 0 {
		return "", fmt.Errorf("enum_ref %s has no canonical values", field.EnumRef)
	}
	members, err := canonicalRequestEnumMembers(field, values)
	if err != nil {
		return "", err
	}
	cases := make([]string, 0, len(members))
	for _, member := range members {
		cases = append(
			cases,
			strconv.Quote(member.WireValue)+" => "+dartType+"."+member.DartMember,
		)
	}
	return "switch (" + access + ") { " + strings.Join(cases, ", ") +
		", _ => throw FormatException(" + pathExpression +
		" + ' has an invalid enum value'), }", nil
}

func requestFieldDartType(field fieldDef) (string, bool, error) {
	nullable := hasRequestConstraint(field, "NULLABLE")
	dartType := strings.TrimSpace(field.ClientDartType)
	if dartType == "" {
		switch strings.TrimSpace(field.Type) {
		case "string", "tag_ref", "time", "ObjectId", "uuid", "identifier":
			dartType = "String"
		case "int", "int32", "int64", "long":
			dartType = "int"
		case "float", "float32", "float64", "double":
			dartType = "double"
		case "bool", "boolean":
			dartType = "bool"
		case "timestamp", "datetime", "date":
			dartType = "DateTime"
		case "enum":
			dartType = strings.TrimSpace(field.EnumRef)
			if dartType == "" {
				dartType = "String"
			}
		case "object", "json", "jsonb":
			dartType = "Map<String, Object?>"
		default:
			if strings.HasPrefix(field.Type, "[]") {
				item := field
				item.Type = strings.TrimPrefix(field.Type, "[]")
				item.ClientDartType = ""
				item.Constraints = nil
				itemType, _, err := requestFieldDartType(item)
				if err != nil {
					return "", false, err
				}
				dartType = "List<" + strings.TrimSuffix(itemType, "?") + ">"
			} else if strings.TrimSpace(field.Type) != "" {
				dartType = strings.TrimSpace(field.Type)
			} else {
				return "", false, fmt.Errorf("metadata type is empty")
			}
		}
	}
	if nullable && !strings.HasSuffix(dartType, "?") {
		dartType += "?"
	}
	return dartType, nullable, nil
}

func requestFieldDartName(field fieldDef) string {
	if value := strings.TrimSpace(field.ClientDartName); value != "" {
		return value
	}
	return field.Name
}

func requestFieldParameterType(field fieldDef, storageType string) string {
	if value := strings.TrimSpace(field.ClientParameterType); value != "" {
		return value
	}
	return storageType
}

func requestFieldWireName(field fieldDef) string {
	if value := strings.TrimSpace(field.ClientWireName); value != "" {
		return value
	}
	return field.Name
}

func requestFieldDefault(field fieldDef) string {
	if value := strings.TrimSpace(field.ClientDefault); value != "" {
		return value
	}
	for _, constraint := range field.Constraints {
		if !strings.HasPrefix(constraint, "DEFAULT_") {
			continue
		}
		value := strings.TrimPrefix(constraint, "DEFAULT_")
		switch value {
		case "TRUE":
			return "true"
		case "FALSE":
			return "false"
		case "EMPTY":
			if strings.HasPrefix(strings.TrimSuffix(field.ClientDartType, "?"), "List<") ||
				strings.HasPrefix(field.Type, "[]") {
				return "const []"
			}
			return "''"
		}
		if _, err := strconv.ParseFloat(value, 64); err == nil {
			return value
		}
		return strconv.Quote(value)
	}
	return ""
}

func requestFieldInitializer(field fieldDef) (string, error) {
	dartType, nullable, err := requestFieldDartType(field)
	if err != nil {
		return "", err
	}
	name := requestFieldDartName(field)
	baseType := strings.TrimSuffix(dartType, "?")
	switch strings.TrimSpace(field.ClientNormalization) {
	case "trim":
		if baseType == "List<String>" {
			if nullable {
				return fmt.Sprintf(
					"%s == null ? null : _normalizeGeneratedTextList(%s, deduplicate: false)",
					name,
					name,
				), nil
			}
			return fmt.Sprintf(
				"_normalizeGeneratedTextList(%s, deduplicate: false)",
				name,
			), nil
		}
		if baseType != "String" {
			return "", fmt.Errorf(
				"client_normalization=trim requires String or List<String>, got %s",
				dartType,
			)
		}
		if nullable {
			return fmt.Sprintf("%s?.trim()", name), nil
		}
		return fmt.Sprintf("%s.trim()", name), nil
	case "trim_to_null":
		if baseType != "String" {
			return "", fmt.Errorf(
				"client_normalization=trim_to_null requires String, got %s",
				dartType,
			)
		}
		return fmt.Sprintf("_normalizeGeneratedOptionalText(%s)", name), nil
	case "trim_drop_empty":
		if baseType != "List<String>" {
			return "", fmt.Errorf(
				"client_normalization=trim_drop_empty requires List<String>, got %s",
				dartType,
			)
		}
		if nullable {
			return fmt.Sprintf(
				"%s == null ? null : _normalizeGeneratedTextList(%s, deduplicate: false)",
				name,
				name,
			), nil
		}
		return fmt.Sprintf(
			"_normalizeGeneratedTextList(%s, deduplicate: false)",
			name,
		), nil
	case "trim_dedupe_drop_empty":
		if baseType != "List<String>" {
			return "", fmt.Errorf(
				"client_normalization=trim_dedupe_drop_empty requires List<String>, got %s",
				dartType,
			)
		}
		if nullable {
			return fmt.Sprintf(
				"%s == null ? null : _normalizeGeneratedTextList(%s, deduplicate: true)",
				name,
				name,
			), nil
		}
		return fmt.Sprintf(
			"_normalizeGeneratedTextList(%s, deduplicate: true)",
			name,
		), nil
	case "utc":
		if baseType != "DateTime" {
			return "", fmt.Errorf(
				"client_normalization=utc requires DateTime, got %s",
				dartType,
			)
		}
		if nullable {
			return fmt.Sprintf("%s?.toUtc()", name), nil
		}
		return fmt.Sprintf("%s.toUtc()", name), nil
	case "sha256":
		if baseType != "String" {
			return "", fmt.Errorf(
				"client_normalization=sha256 requires String, got %s",
				dartType,
			)
		}
		if nullable {
			return fmt.Sprintf("%s?.trim().toLowerCase()", name), nil
		}
		return fmt.Sprintf("%s.trim().toLowerCase()", name), nil
	case "":
		// Continue with immutable collection ownership below.
	default:
		return "", fmt.Errorf(
			"unsupported client_normalization %q",
			field.ClientNormalization,
		)
	}
	switch {
	case strings.HasPrefix(baseType, "List<") && nullable:
		return fmt.Sprintf(
			"%s == null ? null : List.unmodifiable(%s)",
			name,
			name,
		), nil
	case strings.HasPrefix(baseType, "List<"):
		return fmt.Sprintf("List.unmodifiable(%s)", name), nil
	case strings.HasPrefix(baseType, "Map<") && nullable:
		return fmt.Sprintf(
			"%s == null ? null : Map.unmodifiable(%s)",
			name,
			name,
		), nil
	case strings.HasPrefix(baseType, "Map<"):
		return fmt.Sprintf("Map.unmodifiable(%s)", name), nil
	}
	return name, nil
}

func renderRequestFieldValidation(
	output *strings.Builder,
	modelName string,
	field fieldDef,
	enumValues map[string][]string,
) error {
	name := requestFieldDartName(field)
	access := "this." + name
	nullable := hasRequestConstraint(field, "NULLABLE")
	validatedAccess := access
	if nullable {
		validatedAccess += "!"
	}
	if hasRequestConstraint(field, "NOT_BLANK") {
		condition := validatedAccess + ".isEmpty"
		if nullable {
			condition = access + " != null && " + condition
		}
		fmt.Fprintf(output, "    if (%s) {\n", condition)
		fmt.Fprintf(
			output,
			"      throw ArgumentError.value(%s, %q, 'must not be blank');\n",
			access,
			name,
		)
		output.WriteString("    }\n")
	}
	if strings.TrimSpace(field.Type) == "enum" {
		values := enumValues[strings.TrimSpace(field.EnumRef)]
		dartType, _, err := requestFieldDartType(field)
		if err != nil {
			return err
		}
		if strings.TrimSuffix(dartType, "?") == "String" {
			if len(values) == 0 {
				return fmt.Errorf(
					"%s.%s enum_ref %s has no canonical values",
					modelName,
					name,
					field.EnumRef,
				)
			}
			condition := fmt.Sprintf(
				"!const <String>{%s}.contains(%s)",
				quotedDartValues(values),
				validatedAccess,
			)
			if nullable {
				condition = access + " != null && " + condition
			}
			fmt.Fprintf(output, "    if (%s) {\n", condition)
			fmt.Fprintf(
				output,
				"      throw ArgumentError.value(%s, %q, 'unsupported canonical enum value');\n",
				access,
				name,
			)
			output.WriteString("    }\n")
		}
	}
	for _, constraint := range field.Constraints {
		var condition string
		var message string
		switch {
		case constraint == "POSITIVE":
			condition, message = validatedAccess+" <= 0", "must be positive"
		case strings.HasPrefix(constraint, "MAX_LENGTH_"):
			value := strings.TrimPrefix(constraint, "MAX_LENGTH_")
			condition, message = validatedAccess+".length > "+value, "length exceeds "+value
		case strings.HasPrefix(constraint, "MIN_LENGTH_"):
			value := strings.TrimPrefix(constraint, "MIN_LENGTH_")
			condition, message = validatedAccess+".length < "+value, "length is below "+value
		case strings.HasPrefix(constraint, "MAX_ITEMS_"):
			value := strings.TrimPrefix(constraint, "MAX_ITEMS_")
			condition, message = validatedAccess+".length > "+value, "item count exceeds "+value
		case strings.HasPrefix(constraint, "MIN_ITEMS_"):
			value := strings.TrimPrefix(constraint, "MIN_ITEMS_")
			condition, message = validatedAccess+".length < "+value, "item count is below "+value
		case strings.HasPrefix(constraint, "MIN_") &&
			isRequestNumericField(field):
			value := strings.TrimPrefix(constraint, "MIN_")
			condition, message = validatedAccess+" < "+value, "must be at least "+value
		case strings.HasPrefix(constraint, "MAX_") &&
			isRequestNumericField(field):
			value := strings.TrimPrefix(constraint, "MAX_")
			condition, message = validatedAccess+" > "+value, "must not exceed "+value
		}
		if condition == "" {
			continue
		}
		if nullable {
			condition = access + " != null && " + condition
		}
		fmt.Fprintf(output, "    if (%s) {\n", condition)
		fmt.Fprintf(
			output,
			"      throw ArgumentError.value(%s, %q, %q);\n",
			access,
			name,
			message,
		)
		output.WriteString("    }\n")
	}
	return nil
}
