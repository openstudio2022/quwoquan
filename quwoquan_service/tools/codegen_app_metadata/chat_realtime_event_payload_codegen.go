package main

import (
	"encoding/json"
	"fmt"
	"path/filepath"
	"sort"
	"strings"
)

type chatRealtimeEventsYAML struct {
	Events []chatRealtimeEventYAML `yaml:"events"`
}

type chatRealtimeEventYAML struct {
	Name          string   `yaml:"name"`
	ClientWsType  string   `yaml:"client_ws_type"`
	PayloadEntity string   `yaml:"payload_entity"`
	PayloadFields []string `yaml:"payload_fields"`
}

func readChatRealtimeEvents(path string) (*chatRealtimeEventsYAML, error) {
	var out chatRealtimeEventsYAML
	if err := decodeMetadataDocument(path, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func writeChatRealtimeEventPayloads(appDir, metadataDir string) error {
	fields, events, err := collectChatRealtimeEventSources(metadataDir)
	if err != nil {
		return err
	}
	providedEnums, err := chatOperationProvidedEnumRefs()
	if err != nil {
		return err
	}
	operationImports, sharedEnumImports, err := classifyChatRealtimeImports(
		fields,
		events,
		providedEnums,
	)
	if err != nil {
		return err
	}
	sharedEnums, err := renderSharedRealtimeEventEnumsDart(sharedEnumImports)
	if err != nil {
		return err
	}
	writeFile(
		filepath.Join(
			appDir,
			"packages",
			"quwoquan_cloud_contracts",
			"lib",
			"src",
			"generated",
			"realtime",
			"shared_realtime_event_enums.g.dart",
		),
		sharedEnums,
	)
	out, err := renderChatRealtimeEventPayloadsDart(
		"chat/chat/*/events.yaml",
		fields,
		events,
		operationImports,
		sharedEnumImports,
	)
	if err != nil {
		return err
	}
	writeFile(
		filepath.Join(
			appDir,
			"packages",
			"quwoquan_cloud_contracts",
			"lib",
			"src",
			"generated",
			"realtime",
			"chat_realtime_events.g.dart",
		),
		out,
	)
	return nil
}

func chatOperationProvidedEnumRefs() (map[string]struct{}, error) {
	if activeMetadataSource == nil {
		return nil, fmt.Errorf("ContractGraph is not initialized")
	}
	payload, err := json.Marshal(activeMetadataSource.Graph().Operations)
	if err != nil {
		return nil, fmt.Errorf("marshal Chat operations: %w", err)
	}
	var operations []appExposedOperation
	if err := json.Unmarshal(payload, &operations); err != nil {
		return nil, fmt.Errorf("decode Chat operations: %w", err)
	}
	selected := make([]appExposedOperation, 0)
	for index, operation := range operations {
		operation.CanonicalOperationID = activeMetadataSource.Graph().Operations[index].ID
		operation.LocalOperationID = activeMetadataSource.Graph().Operations[index].LocalID
		if operation.Domain != "chat" || operation.ClientContract == nil ||
			operation.ClientContract.DartImport != generatedDomainOperationOwnerImport("chat") {
			continue
		}
		selected = append(selected, operation)
	}
	if len(selected) == 0 {
		return nil, fmt.Errorf("Chat has no generated operation ABI for realtime payload dependencies")
	}
	spec, err := loadDomainOperationContractSpec(
		generatedDomainOperationOwnerImport("chat"),
		selected,
	)
	if err != nil {
		return nil, fmt.Errorf("load Chat operation enum owners: %w", err)
	}
	if err := finalizeDomainOperationContractSpec(&spec); err != nil {
		return nil, fmt.Errorf("finalize Chat operation enum owners: %w", err)
	}
	result := make(map[string]struct{}, len(spec.EnumMembers))
	for name := range spec.EnumMembers {
		result[name] = struct{}{}
	}
	return result, nil
}

func classifyChatRealtimeImports(
	fields *fieldsFile,
	events *chatRealtimeEventsYAML,
	operationEnums map[string]struct{},
) (map[string]struct{}, map[string]struct{}, error) {
	operationImports := map[string]struct{}{}
	sharedEnumImports := map[string]struct{}{}
	sharedEnumValues, err := loadCanonicalSharedEnumValues()
	if err != nil {
		return nil, nil, err
	}
	for _, event := range events.Events {
		if strings.TrimSpace(event.ClientWsType) == "" {
			continue
		}
		definition, exists := fields.Types[event.PayloadEntity]
		if !exists {
			return nil, nil, fmt.Errorf("Chat realtime payload %s has no canonical fields owner", event.PayloadEntity)
		}
		for _, field := range definition.Fields {
			if field.Type == "enum" {
				enumRef := strings.TrimSpace(field.EnumRef)
				if _, provided := operationEnums[enumRef]; provided {
					operationImports[enumRef] = struct{}{}
					continue
				}
				if len(sharedEnumValues[enumRef]) == 0 {
					return nil, nil, fmt.Errorf("Chat realtime enum %s has no generated operation or canonical shared owner", enumRef)
				}
				sharedEnumImports[enumRef] = struct{}{}
				continue
			}
			if chatRealtimeNamedType(field.Type) {
				operationImports[field.Type] = struct{}{}
			}
		}
	}
	return operationImports, sharedEnumImports, nil
}

func renderSharedRealtimeEventEnumsDart(names map[string]struct{}) (string, error) {
	values, err := loadCanonicalSharedEnumValues()
	if err != nil {
		return "", err
	}
	sorted := make([]string, 0, len(names))
	for name := range names {
		sorted = append(sorted, name)
	}
	sort.Strings(sorted)
	var output strings.Builder
	output.WriteString("// Code generated from canonical _shared/types.yaml enums required by realtime payloads. DO NOT EDIT.\n\n")
	for _, name := range sorted {
		members, memberErr := canonicalRequestEnumMembers(fieldDef{
			Name:    name,
			Type:    "enum",
			EnumRef: name,
		}, values[name])
		if memberErr != nil {
			return "", memberErr
		}
		renderDomainWireEnum(&output, name, members)
	}
	return output.String(), nil
}

func collectChatRealtimeEventSources(
	metadataDir string,
) (*fieldsFile, *chatRealtimeEventsYAML, error) {
	eventPaths, err := filepath.Glob(
		filepath.Join(metadataDir, "chat", "chat", "*", "events.yaml"),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("glob Chat realtime event metadata: %w", err)
	}
	sort.Strings(eventPaths)
	combinedFields := &fieldsFile{Types: map[string]entityDef{}}
	combinedEvents := &chatRealtimeEventsYAML{}
	for _, eventsPath := range eventPaths {
		events, readErr := readChatRealtimeEvents(eventsPath)
		if readErr != nil {
			return nil, nil, fmt.Errorf("read Chat realtime events %s: %w", eventsPath, readErr)
		}
		var objectFields *fieldsFile
		for _, event := range events.Events {
			if strings.TrimSpace(event.ClientWsType) == "" {
				continue
			}
			if objectFields == nil {
				objectFields, readErr = readFields(
					filepath.Join(filepath.Dir(eventsPath), "fields.yaml"),
				)
				if readErr != nil {
					return nil, nil, fmt.Errorf(
						"read Chat realtime fields for %s: %w",
						eventsPath,
						readErr,
					)
				}
			}
			entityName := strings.TrimSpace(event.PayloadEntity)
			definition, exists := objectFields.Types[entityName]
			if !exists {
				return nil, nil, fmt.Errorf(
					"Chat realtime event %s payload_entity %s is not an object-local type",
					event.Name,
					entityName,
				)
			}
			if _, duplicate := combinedFields.Types[entityName]; duplicate {
				return nil, nil, fmt.Errorf(
					"Chat realtime payload type %s has multiple object owners",
					entityName,
				)
			}
			combinedFields.Types[entityName] = definition
			combinedEvents.Events = append(combinedEvents.Events, event)
		}
	}
	if len(combinedEvents.Events) == 0 {
		return nil, nil, fmt.Errorf("Chat contracts declare no client_ws_type payload owner")
	}
	sort.Slice(combinedEvents.Events, func(i, j int) bool {
		return combinedEvents.Events[i].ClientWsType < combinedEvents.Events[j].ClientWsType
	})
	return combinedFields, combinedEvents, nil
}

func renderChatRealtimeEventPayloadsDart(
	sourcePath string,
	fields *fieldsFile,
	events *chatRealtimeEventsYAML,
	operationImports map[string]struct{},
	sharedEnumImports map[string]struct{},
) (string, error) {
	selected := make([]chatRealtimeEventYAML, 0, len(events.Events))
	for _, event := range events.Events {
		if strings.TrimSpace(event.ClientWsType) == "" {
			continue
		}
		entityName := strings.TrimSpace(event.PayloadEntity)
		definition, exists := fields.Types[entityName]
		if !exists {
			return "", fmt.Errorf(
				"Chat realtime event %s payload_entity %s is not an object-local type",
				event.Name,
				entityName,
			)
		}
		declared := make([]string, 0, len(definition.Fields))
		for _, field := range definition.Fields {
			declared = append(declared, strings.TrimSpace(field.Name))
		}
		if strings.Join(declared, "\x00") != strings.Join(event.PayloadFields, "\x00") {
			return "", fmt.Errorf(
				"Chat realtime event %s payload_fields must exactly match %s",
				event.Name,
				entityName,
			)
		}
		selected = append(selected, event)
	}
	if len(selected) == 0 {
		return "", fmt.Errorf("Chat events declare no client_ws_type payload owner")
	}

	for _, event := range selected {
		for _, field := range fields.Types[event.PayloadEntity].Fields {
			if _, err := chatRealtimeDartType(field); err != nil {
				return "", fmt.Errorf(
					"chat realtime event %s field %s: %w",
					event.Name,
					field.Name,
					err,
				)
			}
		}
	}
	importNames := make([]string, 0, len(operationImports))
	for name := range operationImports {
		importNames = append(importNames, name)
	}
	sort.Strings(importNames)
	sharedEnumNames := make([]string, 0, len(sharedEnumImports))
	for name := range sharedEnumImports {
		sharedEnumNames = append(sharedEnumNames, name)
	}
	sort.Strings(sharedEnumNames)

	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from explicit Chat client_ws_type metadata. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n\n")
	if len(importNames) > 0 {
		b.WriteString("import '../../chat/chat_operation_contracts.g.dart' show ")
		b.WriteString(strings.Join(importNames, ", "))
		b.WriteString(";\n\n")
	}
	if len(sharedEnumNames) > 0 {
		b.WriteString("import 'shared_realtime_event_enums.g.dart' show ")
		b.WriteString(strings.Join(sharedEnumNames, ", "))
		b.WriteString(";\n\n")
	}
	b.WriteString("sealed class ChatRealtimeEventPayload {\n")
	b.WriteString("  const ChatRealtimeEventPayload();\n")
	b.WriteString("  Map<String, Object?> toWire();\n")
	b.WriteString("}\n\n")

	for _, event := range selected {
		b.WriteString(fmt.Sprintf(
			"const chatRealtimeType%s = '%s';\n\n",
			toDartExportedName(event.Name),
			strings.ReplaceAll(event.ClientWsType, "'", "\\'"),
		))
		if err := emitChatRealtimePayloadClass(
			&b,
			event,
			fields.Types[event.PayloadEntity],
		); err != nil {
			return "", err
		}
	}

	b.WriteString("ChatRealtimeEventPayload decodeChatRealtimeEventPayload({\n")
	b.WriteString("  required String eventType,\n")
	b.WriteString("  required Map<String, dynamic> payload,\n")
	b.WriteString("}) {\n")
	b.WriteString("  switch (eventType) {\n")
	for _, event := range selected {
		name := toDartExportedName(event.Name)
		b.WriteString(fmt.Sprintf("    case chatRealtimeType%s:\n", name))
		b.WriteString(fmt.Sprintf("      return %s.fromWire(payload);\n", event.PayloadEntity))
	}
	b.WriteString("    default:\n")
	b.WriteString("      throw FormatException('Unsupported chat realtime event type: $eventType');\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")
	needsOptionalBool := false
	needsOptionalTimestamp := false
	for _, event := range selected {
		for _, field := range fields.Types[event.PayloadEntity].Fields {
			if !hasConstraint(field.Constraints, "NULLABLE") {
				continue
			}
			switch field.Type {
			case "bool":
				needsOptionalBool = true
			case "timestamp", "datetime":
				needsOptionalTimestamp = true
			}
		}
	}
	emitChatRealtimeDecodeHelpers(&b, needsOptionalBool, needsOptionalTimestamp)
	return b.String(), nil
}

func emitChatRealtimePayloadClass(
	b *strings.Builder,
	event chatRealtimeEventYAML,
	definition entityDef,
) error {
	className := strings.TrimSpace(event.PayloadEntity)
	b.WriteString(fmt.Sprintf("final class %s extends ChatRealtimeEventPayload {\n", className))
	b.WriteString(fmt.Sprintf("  const %s({\n", className))
	for _, field := range definition.Fields {
		if hasConstraint(field.Constraints, "NULLABLE") {
			b.WriteString(fmt.Sprintf("    this.%s,\n", field.Name))
		} else {
			b.WriteString(fmt.Sprintf("    required this.%s,\n", field.Name))
		}
	}
	b.WriteString("  });\n\n")
	for _, field := range definition.Fields {
		dartType, err := chatRealtimeDartType(field)
		if err != nil {
			return err
		}
		if hasConstraint(field.Constraints, "NULLABLE") {
			dartType += "?"
		}
		b.WriteString(fmt.Sprintf("  final %s %s;\n", dartType, field.Name))
	}
	b.WriteString(fmt.Sprintf("\n  factory %s.fromWire(Map<String, dynamic> wire) {\n", className))
	b.WriteString("    _chatEventRequireExactFields(\n")
	b.WriteString("      wire,\n")
	b.WriteString("      const <String>{\n")
	for _, field := range definition.Fields {
		b.WriteString(fmt.Sprintf("        '%s',\n", field.Name))
	}
	b.WriteString("      },\n")
	b.WriteString(fmt.Sprintf("      '%s',\n", className))
	b.WriteString("    );\n")
	b.WriteString(fmt.Sprintf("    return %s(\n", className))
	for _, field := range definition.Fields {
		expression, err := chatRealtimeDecodeExpression(className, field)
		if err != nil {
			return err
		}
		b.WriteString(fmt.Sprintf("      %s: %s,\n", field.Name, expression))
	}
	b.WriteString("    );\n")
	b.WriteString("  }\n")
	b.WriteString("\n  @override\n")
	b.WriteString("  Map<String, Object?> toWire() => <String, Object?>{\n")
	for _, field := range definition.Fields {
		expression, err := chatRealtimeEncodeExpression(field)
		if err != nil {
			return err
		}
		if hasConstraint(field.Constraints, "NULLABLE") {
			b.WriteString(fmt.Sprintf("    if (%s != null) '%s': %s,\n", field.Name, field.Name, expression))
		} else {
			b.WriteString(fmt.Sprintf("    '%s': %s,\n", field.Name, expression))
		}
	}
	b.WriteString("  };\n")
	b.WriteString("}\n\n")
	return nil
}

func chatRealtimeEncodeExpression(field fieldDef) (string, error) {
	access := field.Name
	if hasConstraint(field.Constraints, "NULLABLE") {
		access += "!"
	}
	switch field.Type {
	case "string", "int", "int64", "long", "bool":
		return access, nil
	case "timestamp", "datetime":
		return access + ".toUtc().toIso8601String()", nil
	case "[]string":
		return access + ".toList(growable: false)", nil
	case "enum":
		return access + ".wireName", nil
	default:
		if chatRealtimeNamedType(field.Type) {
			return access + ".toWire()", nil
		}
		return "", fmt.Errorf("unsupported field type %q", field.Type)
	}
}

func chatRealtimeDartType(field fieldDef) (string, error) {
	switch field.Type {
	case "string":
		return "String", nil
	case "int", "int64", "long":
		return "int", nil
	case "bool":
		return "bool", nil
	case "timestamp", "datetime":
		return "DateTime", nil
	case "[]string":
		return "List<String>", nil
	case "enum":
		if strings.TrimSpace(field.EnumRef) == "" {
			return "", fmt.Errorf("enum_ref is required")
		}
		return field.EnumRef, nil
	default:
		if chatRealtimeNamedType(field.Type) {
			return field.Type, nil
		}
		return "", fmt.Errorf("unsupported field type %q", field.Type)
	}
}

func chatRealtimeNamedType(fieldType string) bool {
	trimmed := strings.TrimSpace(fieldType)
	return trimmed != "" && trimmed[0] >= 'A' && trimmed[0] <= 'Z'
}

func chatRealtimeDecodeExpression(className string, field fieldDef) (string, error) {
	path := fmt.Sprintf("'%s.%s'", className, field.Name)
	nullable := hasConstraint(field.Constraints, "NULLABLE")
	positive := hasConstraint(field.Constraints, "POSITIVE") ||
		hasConstraint(field.Constraints, "MIN_1")
	switch field.Type {
	case "string":
		if nullable {
			return fmt.Sprintf("_chatEventOptionalString(wire, '%s', %s)", field.Name, path), nil
		}
		return fmt.Sprintf("_chatEventRequiredString(wire, '%s', %s)", field.Name, path), nil
	case "int", "int64", "long":
		if nullable {
			return fmt.Sprintf("_chatEventOptionalInt(wire, '%s', %s, positive: %t)", field.Name, path, positive), nil
		}
		return fmt.Sprintf("_chatEventRequiredInt(wire, '%s', %s, positive: %t)", field.Name, path, positive), nil
	case "bool":
		if nullable {
			return fmt.Sprintf("_chatEventOptionalBool(wire, '%s', %s)", field.Name, path), nil
		}
		return fmt.Sprintf("_chatEventRequiredBool(wire, '%s', %s)", field.Name, path), nil
	case "timestamp", "datetime":
		if nullable {
			return fmt.Sprintf("_chatEventOptionalTimestamp(wire, '%s', %s)", field.Name, path), nil
		}
		return fmt.Sprintf("_chatEventRequiredTimestamp(wire, '%s', %s)", field.Name, path), nil
	case "[]string":
		if nullable {
			return fmt.Sprintf("_chatEventOptionalStringList(wire, '%s', %s)", field.Name, path), nil
		}
		return fmt.Sprintf("_chatEventRequiredStringList(wire, '%s', %s)", field.Name, path), nil
	case "enum":
		value := fmt.Sprintf("_chatEventRequiredValue(wire, '%s', %s)", field.Name, path)
		if nullable {
			return fmt.Sprintf(
				"wire['%s'] == null ? null : %s.fromWire(%s, %s)",
				field.Name,
				field.EnumRef,
				value,
				path,
			), nil
		}
		return fmt.Sprintf("%s.fromWire(%s, %s)", field.EnumRef, value, path), nil
	default:
		if !chatRealtimeNamedType(field.Type) {
			return "", fmt.Errorf("unsupported field type %q", field.Type)
		}
		object := fmt.Sprintf("_chatEventRequiredObject(wire, '%s', %s)", field.Name, path)
		if nullable {
			return fmt.Sprintf("wire['%s'] == null ? null : %s.fromWire(%s, %s)", field.Name, field.Type, object, path), nil
		}
		return fmt.Sprintf("%s.fromWire(%s, %s)", field.Type, object, path), nil
	}
}

func emitChatRealtimeDecodeHelpers(
	b *strings.Builder,
	needsOptionalBool bool,
	needsOptionalTimestamp bool,
) {
	b.WriteString(`void _chatEventRequireExactFields(Map<String, dynamic> wire, Set<String> allowed, String path) {
  final unknown = wire.keys.where((key) => !allowed.contains(key)).toList(growable: false);
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(',')}');
  }
}

Object? _chatEventRequiredValue(Map<String, dynamic> wire, String field, String path) {
  if (!wire.containsKey(field) || wire[field] == null) {
    throw FormatException('$path is required');
  }
  return wire[field];
}

String _chatEventRequiredString(Map<String, dynamic> wire, String field, String path) {
  final value = _chatEventRequiredValue(wire, field, path);
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$path must be a non-empty string');
  }
  return value.trim();
}

String? _chatEventOptionalString(Map<String, dynamic> wire, String field, String path) {
  final value = wire[field];
  if (value == null) return null;
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

int _chatEventRequiredInt(Map<String, dynamic> wire, String field, String path, {required bool positive}) {
  final value = _chatEventRequiredValue(wire, field, path);
  if (value is! int || (positive && value <= 0)) {
    throw FormatException('$path must be ${positive ? 'a positive integer' : 'an integer'}');
  }
  return value;
}

int? _chatEventOptionalInt(Map<String, dynamic> wire, String field, String path, {required bool positive}) {
  if (wire[field] == null) return null;
  return _chatEventRequiredInt(wire, field, path, positive: positive);
}

bool _chatEventRequiredBool(Map<String, dynamic> wire, String field, String path) {
  final value = _chatEventRequiredValue(wire, field, path);
  if (value is! bool) throw FormatException('$path must be a boolean');
  return value;
}
`)

	if needsOptionalBool {
		b.WriteString(`
bool? _chatEventOptionalBool(Map<String, dynamic> wire, String field, String path) {
  if (wire[field] == null) return null;
  return _chatEventRequiredBool(wire, field, path);
}
`)
	}

	b.WriteString(`
DateTime _chatEventRequiredTimestamp(Map<String, dynamic> wire, String field, String path) {
  final value = _chatEventRequiredString(wire, field, path);
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$path must be ISO-8601');
  return parsed;
}
`)

	if needsOptionalTimestamp {
		b.WriteString(`
DateTime? _chatEventOptionalTimestamp(Map<String, dynamic> wire, String field, String path) {
  if (wire[field] == null) return null;
  return _chatEventRequiredTimestamp(wire, field, path);
}
`)
	}

	b.WriteString(`
List<String> _chatEventRequiredStringList(Map<String, dynamic> wire, String field, String path) {
  final value = _chatEventRequiredValue(wire, field, path);
  if (value is! List || value.any((item) => item is! String)) {
    throw FormatException('$path must be string[]');
  }
  return List<String>.unmodifiable(value.cast<String>());
}

List<String>? _chatEventOptionalStringList(Map<String, dynamic> wire, String field, String path) {
  if (wire[field] == null) return null;
  return _chatEventRequiredStringList(wire, field, path);
}

Map<String, Object?> _chatEventRequiredObject(Map<String, dynamic> wire, String field, String path) {
  final value = _chatEventRequiredValue(wire, field, path);
  if (value is! Map || value.keys.any((key) => key is! String)) {
    throw FormatException('$path must be an object');
  }
  return Map<String, Object?>.from(value);
}
`)
}
