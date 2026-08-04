package main

import (
	"encoding/json"
	"fmt"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"unicode"
)

const previewTrackManifestSchemaPath = "content/media/media_asset/preview_track_manifest.schema.json"

type previewTrackSchemaDocument struct {
	Schema               string                            `json:"$schema"`
	ID                   string                            `json:"$id"`
	Title                string                            `json:"title"`
	Type                 string                            `json:"type"`
	AdditionalProperties bool                              `json:"additionalProperties"`
	Required             []string                          `json:"required"`
	Properties           map[string]previewTrackSchemaNode `json:"properties"`
	Definitions          map[string]previewTrackSchemaNode `json:"$defs"`
}

type previewTrackSchemaNode struct {
	Type                 string                            `json:"type"`
	AdditionalProperties *bool                             `json:"additionalProperties"`
	Required             []string                          `json:"required"`
	Properties           map[string]previewTrackSchemaNode `json:"properties"`
	Definitions          map[string]previewTrackSchemaNode `json:"$defs"`
	Items                *previewTrackSchemaNode           `json:"items"`
	Ref                  string                            `json:"$ref"`
	Const                string                            `json:"const"`
	Enum                 []string                          `json:"enum"`
	Pattern              string                            `json:"pattern"`
	MinLength            int                               `json:"minLength"`
	Minimum              *int                              `json:"minimum"`
	Maximum              *int                              `json:"maximum"`
	MinItems             int                               `json:"minItems"`
	MaxItems             int                               `json:"maxItems"`
}

type previewTrackGeneratedModel struct {
	Name       string
	Required   []string
	Properties map[string]previewTrackSchemaNode
	Scope      string
}

type previewTrackGeneratedEnum struct {
	Name   string
	Values []string
}

func generateContentPreviewTrackManifestContract(appDir string) error {
	raw, err := readMetadataDocument(previewTrackManifestSchemaPath)
	if err != nil {
		return fmt.Errorf(
			"read canonical preview track manifest schema from fixed ContractGraph: %w",
			err,
		)
	}
	content, err := renderContentPreviewTrackManifestContract(raw)
	if err != nil {
		return fmt.Errorf("render canonical preview track manifest contract: %w", err)
	}
	writeFile(
		filepath.Join(
			appDir,
			"packages",
			"quwoquan_cloud_contracts",
			"lib",
			"src",
			"content",
			"preview_track_manifest_contracts.g.dart",
		),
		content,
	)
	writeFile(
		filepath.Join(
			appDir,
			"packages",
			"quwoquan_cloud_contracts",
			"lib",
			"generated",
			"content_preview_track_contracts.dart",
		),
		"// Code generated from the canonical content preview-track owner. DO NOT EDIT.\n"+
			"// ContractGraph SHA256: "+activeContractSHA256+"\n\n"+
			"library;\n\n"+
			"export '../src/content/preview_track_manifest_contracts.g.dart';\n",
	)
	return nil
}

func renderContentPreviewTrackManifestContract(raw []byte) (string, error) {
	var schema previewTrackSchemaDocument
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&schema); err != nil {
		return "", err
	}
	if schema.Schema != "https://json-schema.org/draft/2020-12/schema" ||
		strings.TrimSpace(schema.ID) == "" ||
		schema.Title != "PreviewTrackManifest" ||
		schema.Type != "object" ||
		schema.AdditionalProperties {
		return "", fmt.Errorf("preview manifest root must be a closed PreviewTrackManifest object")
	}
	if err := validatePreviewTrackSchemaObject(
		"PreviewTrackManifest",
		schema.Required,
		schema.Properties,
		false,
	); err != nil {
		return "", err
	}
	if len(schema.Definitions) == 0 {
		return "", fmt.Errorf("preview manifest schema has no object definitions")
	}

	models := []previewTrackGeneratedModel{{
		Name:       schema.Title + "Wire",
		Required:   append([]string(nil), schema.Required...),
		Properties: schema.Properties,
		Scope:      strings.TrimSuffix(schema.Title, "Manifest"),
	}}
	definitionNames := make([]string, 0, len(schema.Definitions))
	for name := range schema.Definitions {
		definitionNames = append(definitionNames, name)
	}
	sort.Strings(definitionNames)
	for _, name := range definitionNames {
		definition := schema.Definitions[name]
		if definition.Type != "object" ||
			definition.AdditionalProperties == nil ||
			*definition.AdditionalProperties {
			return "", fmt.Errorf("preview manifest definition %s must be a closed object", name)
		}
		if err := validatePreviewTrackSchemaObject(
			name,
			definition.Required,
			definition.Properties,
			false,
		); err != nil {
			return "", err
		}
		models = append(models, previewTrackGeneratedModel{
			Name:       previewTrackDefinitionClass(schema.Title, name),
			Required:   append([]string(nil), definition.Required...),
			Properties: definition.Properties,
			Scope:      strings.TrimSuffix(schema.Title, "Manifest") + previewTrackExportedName(name),
		})
	}

	enums, err := previewTrackSchemaEnums(models)
	if err != nil {
		return "", err
	}
	definitionClasses := map[string]string{}
	for _, name := range definitionNames {
		definitionClasses[name] = previewTrackDefinitionClass(schema.Title, name)
	}

	var output strings.Builder
	output.WriteString("// Code generated from canonical content MediaAsset preview-track schema. DO NOT EDIT.\n")
	output.WriteString("// ContractGraph SHA256: ")
	output.WriteString(activeContractSHA256)
	output.WriteString("\n\nlibrary;\n\n")
	for _, enum := range enums {
		renderPreviewTrackDartEnum(&output, enum)
	}
	for _, model := range models {
		if err := renderPreviewTrackDartModel(
			&output,
			model,
			definitionClasses,
		); err != nil {
			return "", err
		}
	}
	output.WriteString(previewTrackDartDecoderHelpers)
	return output.String(), nil
}

func validatePreviewTrackSchemaObject(
	name string,
	required []string,
	properties map[string]previewTrackSchemaNode,
	allowOptional bool,
) error {
	if len(required) == 0 || len(properties) == 0 {
		return fmt.Errorf("preview manifest object %s has no required fields", name)
	}
	requiredSet := make(map[string]struct{}, len(required))
	for _, field := range required {
		if strings.TrimSpace(field) == "" {
			return fmt.Errorf("preview manifest object %s contains an empty required field", name)
		}
		if _, duplicate := requiredSet[field]; duplicate {
			return fmt.Errorf("preview manifest object %s repeats required field %s", name, field)
		}
		if _, exists := properties[field]; !exists {
			return fmt.Errorf("preview manifest object %s requires unknown field %s", name, field)
		}
		requiredSet[field] = struct{}{}
	}
	if !allowOptional && len(requiredSet) != len(properties) {
		return fmt.Errorf("preview manifest object %s contains unsupported optional fields", name)
	}
	return nil
}

func previewTrackSchemaEnums(
	models []previewTrackGeneratedModel,
) ([]previewTrackGeneratedEnum, error) {
	byName := map[string][]string{}
	for _, model := range models {
		for _, field := range model.Required {
			property := model.Properties[field]
			if len(property.Enum) == 0 {
				continue
			}
			name := model.Scope + previewTrackExportedName(field)
			if previous, exists := byName[name]; exists &&
				strings.Join(previous, "\x00") != strings.Join(property.Enum, "\x00") {
				return nil, fmt.Errorf("preview manifest enum %s has conflicting values", name)
			}
			byName[name] = append([]string(nil), property.Enum...)
		}
	}
	names := make([]string, 0, len(byName))
	for name := range byName {
		names = append(names, name)
	}
	sort.Strings(names)
	result := make([]previewTrackGeneratedEnum, 0, len(names))
	for _, name := range names {
		seen := map[string]struct{}{}
		for _, value := range byName[name] {
			if strings.TrimSpace(value) == "" {
				return nil, fmt.Errorf("preview manifest enum %s contains an empty value", name)
			}
			if _, duplicate := seen[value]; duplicate {
				return nil, fmt.Errorf("preview manifest enum %s repeats value %q", name, value)
			}
			seen[value] = struct{}{}
		}
		result = append(result, previewTrackGeneratedEnum{Name: name, Values: byName[name]})
	}
	return result, nil
}

func renderPreviewTrackDartEnum(output *strings.Builder, enum previewTrackGeneratedEnum) {
	fmt.Fprintf(output, "enum %s {\n", enum.Name)
	for index, value := range enum.Values {
		terminator := ","
		if index == len(enum.Values)-1 {
			terminator = ";"
		}
		fmt.Fprintf(
			output,
			"  %s(%s)%s\n",
			previewTrackDartEnumMember(value),
			previewTrackDartStringLiteral(value),
			terminator,
		)
	}
	fmt.Fprintf(output, "\n  const %s(this.wireName);\n\n", enum.Name)
	output.WriteString("  final String wireName;\n\n")
	fmt.Fprintf(output, "  static %s fromWire(Object? value, String path) {\n", enum.Name)
	output.WriteString("    return switch (value) {\n")
	for _, value := range enum.Values {
		fmt.Fprintf(
			output,
			"      %q => %s.%s,\n",
			value,
			enum.Name,
			previewTrackDartEnumMember(value),
		)
	}
	output.WriteString("      _ => throw FormatException('$path has an invalid enum value'),\n")
	output.WriteString("    };\n  }\n}\n\n")
}

func renderPreviewTrackDartModel(
	output *strings.Builder,
	model previewTrackGeneratedModel,
	definitionClasses map[string]string,
) error {
	fmt.Fprintf(output, "final class %s {\n", model.Name)
	fmt.Fprintf(output, "  const %s({\n", model.Name)
	for _, field := range model.Required {
		fmt.Fprintf(output, "    required this.%s,\n", toDartFieldName(field))
	}
	output.WriteString("  });\n\n")
	for _, field := range model.Required {
		typeName, err := previewTrackDartType(
			model.Scope,
			field,
			model.Properties[field],
			definitionClasses,
		)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field, err)
		}
		fmt.Fprintf(output, "  final %s %s;\n", typeName, toDartFieldName(field))
	}
	output.WriteString("\n  factory ")
	output.WriteString(model.Name)
	output.WriteString(".fromWire(Object? value, [String path = ")
	output.WriteString(strconv.Quote(model.Name))
	output.WriteString("]) {\n")
	output.WriteString("    final map = _previewRequiredObject(value, path);\n")
	output.WriteString("    _previewRejectUnknownFields(map, const <String>{")
	for index, field := range model.Required {
		if index > 0 {
			output.WriteString(", ")
		}
		output.WriteString(strconv.Quote(field))
	}
	output.WriteString("}, path);\n")
	fmt.Fprintf(output, "    return %s(\n", model.Name)
	for _, field := range model.Required {
		expression, err := previewTrackDartDecodeExpression(
			model.Scope,
			field,
			model.Properties[field],
			"map["+strconv.Quote(field)+"]",
			"'$path."+field+"'",
			definitionClasses,
		)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field, err)
		}
		fmt.Fprintf(output, "      %s: %s,\n", toDartFieldName(field), expression)
	}
	output.WriteString("    );\n  }\n\n")
	output.WriteString("  Map<String, Object?> toWire() => <String, Object?>{\n")
	for _, field := range model.Required {
		expression, err := previewTrackDartEncodeExpression(
			model.Properties[field],
			toDartFieldName(field),
		)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field, err)
		}
		fmt.Fprintf(output, "    %q: %s,\n", field, expression)
	}
	output.WriteString("  };\n}\n\n")
	return nil
}

func previewTrackDartType(
	scope string,
	field string,
	property previewTrackSchemaNode,
	definitionClasses map[string]string,
) (string, error) {
	if property.Ref != "" {
		name, err := previewTrackDefinitionRef(property.Ref)
		if err != nil {
			return "", err
		}
		className := definitionClasses[name]
		if className == "" {
			return "", fmt.Errorf("unknown definition ref %s", property.Ref)
		}
		return className, nil
	}
	if property.Const != "" {
		return "String", nil
	}
	if len(property.Enum) > 0 {
		return scope + previewTrackExportedName(field), nil
	}
	switch property.Type {
	case "string":
		return "String", nil
	case "integer":
		return "int", nil
	case "array":
		if property.Items == nil {
			return "", fmt.Errorf("array has no items schema")
		}
		itemType, err := previewTrackDartType(scope, field, *property.Items, definitionClasses)
		if err != nil {
			return "", err
		}
		return "List<" + itemType + ">", nil
	default:
		return "", fmt.Errorf("unsupported JSON schema type %q", property.Type)
	}
}

func previewTrackDartDecodeExpression(
	scope string,
	field string,
	property previewTrackSchemaNode,
	access string,
	path string,
	definitionClasses map[string]string,
) (string, error) {
	if property.Ref != "" {
		typeName, err := previewTrackDartType(scope, field, property, definitionClasses)
		if err != nil {
			return "", err
		}
		return typeName + ".fromWire(" + access + ", " + path + ")", nil
	}
	if property.Const != "" {
		return "_previewRequiredConstString(" + access + ", " + path + ", " +
			previewTrackDartStringLiteral(property.Const) + ")", nil
	}
	if len(property.Enum) > 0 {
		return scope + previewTrackExportedName(field) + ".fromWire(" + access + ", " + path + ")", nil
	}
	switch property.Type {
	case "string":
		arguments := ""
		if property.MinLength > 0 {
			arguments += fmt.Sprintf(", minLength: %d", property.MinLength)
		}
		if property.Pattern != "" {
			arguments += ", pattern: " + previewTrackDartStringLiteral(property.Pattern)
		}
		return "_previewRequiredString(" + access + ", " + path + arguments + ")", nil
	case "integer":
		arguments := ""
		if property.Minimum != nil {
			arguments += fmt.Sprintf(", min: %d", *property.Minimum)
		}
		if property.Maximum != nil {
			arguments += fmt.Sprintf(", max: %d", *property.Maximum)
		}
		return "_previewRequiredInt(" + access + ", " + path + arguments + ")", nil
	case "array":
		if property.Items == nil {
			return "", fmt.Errorf("array has no items schema")
		}
		itemType, err := previewTrackDartType(scope, field, *property.Items, definitionClasses)
		if err != nil {
			return "", err
		}
		itemExpression, err := previewTrackDartDecodeExpression(
			scope,
			field,
			*property.Items,
			"entry.value",
			path+" + '[${entry.key}]'",
			definitionClasses,
		)
		if err != nil {
			return "", err
		}
		arguments := ""
		if property.MinItems > 0 {
			arguments += fmt.Sprintf(", minItems: %d", property.MinItems)
		}
		if property.MaxItems > 0 {
			arguments += fmt.Sprintf(", maxItems: %d", property.MaxItems)
		}
		return "List<" + itemType + ">.unmodifiable(_previewRequiredList(" + access + ", " + path +
			arguments + ").asMap().entries.map((entry) => " + itemExpression + "))", nil
	default:
		return "", fmt.Errorf("unsupported JSON schema type %q", property.Type)
	}
}

// JSON Schema patterns may contain `$`, which starts interpolation in Dart
// even inside double-quoted strings. Go's strconv.Quote handles the remaining
// escapes; the additional backslash preserves `$` as literal schema data.
func previewTrackDartStringLiteral(value string) string {
	return strings.ReplaceAll(strconv.Quote(value), "$", `\$`)
}

func previewTrackDartEncodeExpression(
	property previewTrackSchemaNode,
	fieldName string,
) (string, error) {
	if property.Ref != "" {
		return fieldName + ".toWire()", nil
	}
	if property.Const != "" {
		return fieldName, nil
	}
	if len(property.Enum) > 0 {
		return fieldName + ".wireName", nil
	}
	switch property.Type {
	case "string":
		return fieldName, nil
	case "integer":
		return fieldName, nil
	case "array":
		if property.Items == nil {
			return "", fmt.Errorf("array has no items schema")
		}
		if property.Items.Ref != "" {
			return fieldName + ".map((entry) => entry.toWire()).toList(growable: false)", nil
		}
		return fieldName + ".toList(growable: false)", nil
	default:
		return "", fmt.Errorf("unsupported JSON schema type %q", property.Type)
	}
}

func previewTrackDefinitionRef(ref string) (string, error) {
	const prefix = "#/$defs/"
	if !strings.HasPrefix(ref, prefix) || len(ref) == len(prefix) {
		return "", fmt.Errorf("preview manifest only supports local definition refs: %s", ref)
	}
	return strings.TrimPrefix(ref, prefix), nil
}

func previewTrackDefinitionClass(title, definition string) string {
	return strings.TrimSuffix(title, "Manifest") + previewTrackExportedName(definition) + "Wire"
}

func previewTrackExportedName(value string) string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsDigit(r)
	})
	if len(parts) == 0 {
		return "Value"
	}
	var result strings.Builder
	for _, part := range parts {
		runes := []rune(part)
		if len(runes) == 0 {
			continue
		}
		result.WriteRune(unicode.ToUpper(runes[0]))
		result.WriteString(string(runes[1:]))
	}
	return result.String()
}

func previewTrackDartEnumMember(value string) string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsDigit(r)
	})
	if len(parts) == 0 {
		return "value"
	}
	var result strings.Builder
	for index, part := range parts {
		runes := []rune(part)
		if len(runes) == 0 {
			continue
		}
		if index == 0 {
			result.WriteRune(unicode.ToLower(runes[0]))
		} else {
			result.WriteRune(unicode.ToUpper(runes[0]))
		}
		result.WriteString(string(runes[1:]))
	}
	member := result.String()
	if member == "" {
		return "value"
	}
	if unicode.IsDigit([]rune(member)[0]) {
		return "value" + previewTrackExportedName(member)
	}
	return member
}

const previewTrackDartDecoderHelpers = `
Map<String, Object?> _previewRequiredObject(Object? value, String path) {
  if (value is! Map) {
    throw FormatException('$path must be an object');
  }
  return value.map((key, child) {
    if (key is! String) {
      throw FormatException('$path contains a non-string key');
    }
    return MapEntry(key, child);
  });
}

List<Object?> _previewRequiredList(
  Object? value,
  String path, {
  int? minItems,
  int? maxItems,
}) {
  if (value is! List) {
    throw FormatException('$path must be an array');
  }
  if (minItems != null && value.length < minItems) {
    throw FormatException('$path has fewer than $minItems items');
  }
  if (maxItems != null && value.length > maxItems) {
    throw FormatException('$path has more than $maxItems items');
  }
  return List<Object?>.unmodifiable(value);
}

String _previewRequiredString(
  Object? value,
  String path, {
  int? minLength,
  String? pattern,
}) {
  if (value is! String ||
      (minLength != null && value.length < minLength) ||
      (pattern != null && !RegExp(pattern).hasMatch(value))) {
    throw FormatException('$path has an invalid string value');
  }
  return value;
}

String _previewRequiredConstString(
  Object? value,
  String path,
  String expected,
) {
  final decoded = _previewRequiredString(value, path);
  if (decoded != expected) {
    throw FormatException('$path does not match the canonical schema identity');
  }
  return decoded;
}

int _previewRequiredInt(
  Object? value,
  String path, {
  int? min,
  int? max,
}) {
  if (value is! num || value.isNaN || value.isInfinite) {
    throw FormatException('$path must be an integer');
  }
  final decoded = value.toInt();
  if (decoded.toDouble() != value.toDouble() ||
      (min != null && decoded < min) ||
      (max != null && decoded > max)) {
    throw FormatException('$path has an invalid integer value');
  }
  return decoded;
}

void _previewRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  final unknown = map.keys.where((key) => !allowed.contains(key)).toList();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}
`
