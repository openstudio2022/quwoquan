package main

import (
	"fmt"
	"sort"
	"strings"
)

func renderOperationRequestPart(
	library requestLibrarySpec,
	partOfURI string,
	enumValues map[string][]string,
) (string, error) {
	reachableLibrary, err := requestLibraryWithReachableModels(library)
	if err != nil {
		return "", err
	}
	library = reachableLibrary
	var output strings.Builder
	output.WriteString("// Code generated from the accepted ContractGraph. DO NOT EDIT.\n")
	output.WriteString("// ContractGraph SHA256: ")
	output.WriteString(activeContractSHA256)
	output.WriteString("\n\npart of '")
	output.WriteString(partOfURI)
	output.WriteString("';\n\n")
	if requestLibraryUsesNormalization(library, "trim_to_null") {
		output.WriteString(
			"String? _normalizeGeneratedOptionalText(String? value) {\n" +
				"  final normalized = value?.trim();\n" +
				"  return normalized == null || normalized.isEmpty ? null : normalized;\n" +
				"}\n\n",
		)
	}
	if requestLibraryUsesTextListNormalization(library) {
		output.WriteString(
			"List<String> _normalizeGeneratedTextList(\n" +
				"  Iterable<String> values, {\n" +
				"  required bool deduplicate,\n" +
				"}) {\n" +
				"  final result = <String>[];\n" +
				"  final seen = <String>{};\n" +
				"  for (final value in values) {\n" +
				"    final normalized = value.trim();\n" +
				"    if (normalized.isEmpty) continue;\n" +
				"    if (deduplicate && !seen.add(normalized)) continue;\n" +
				"    result.add(normalized);\n" +
				"  }\n" +
				"  return List<String>.unmodifiable(result);\n" +
				"}\n\n",
		)
	}
	if requestLibraryUsesWireMode(library, "nullableMutationWireValue") {
		output.WriteString(
			"Object _encodeGeneratedNullableMutation<T extends Object>(\n" +
				"  NullableSettingMutation<T> mutation,\n" +
				"  Object Function(T value) encoder,\n" +
				") {\n" +
				"  if (mutation.clearsValue) return '';\n" +
				"  final value = mutation.value;\n" +
				"  if (value == null) {\n" +
				"    throw StateError('setting mutation must contain a value or clear marker');\n" +
				"  }\n" +
				"  return encoder(value);\n" +
				"}\n\n",
		)
	}
	if requestLibraryUsesWireMode(library, "structuredValue") {
		output.WriteString(
			"Object? _encodeGeneratedStructuredValue(ContentPostStructuredValue value) =>\n" +
				"    switch (value) {\n" +
				"      ContentPostStructuredObject(:final fields) => <String, Object?>{\n" +
				"        for (final entry in fields.entries)\n" +
				"          entry.key: _encodeGeneratedStructuredValue(entry.value),\n" +
				"      },\n" +
				"      ContentPostStructuredArray(:final values) => values\n" +
				"          .map(_encodeGeneratedStructuredValue)\n" +
				"          .toList(growable: false),\n" +
				"      ContentPostStructuredText(:final value) => value,\n" +
				"      ContentPostStructuredNumber(:final value) => value,\n" +
				"      ContentPostStructuredBoolean(:final value) => value,\n" +
				"      ContentPostStructuredNull() => null,\n" +
				"    };\n\n",
		)
	}

	var modelOutput strings.Builder
	modelNames := make([]string, 0, len(library.Models))
	for name := range library.Models {
		modelNames = append(modelNames, name)
	}
	sort.Strings(modelNames)
	for _, name := range modelNames {
		if _, provided := library.ProvidedModels[name]; provided {
			continue
		}
		model, err := requestModelWithProvidedWireOwners(
			library.Models[name],
			library.ProvidedModels,
		)
		if err != nil {
			return "", fmt.Errorf("%s: %w", library.OwnerImport, err)
		}
		if err := renderRequestModel(
			&modelOutput,
			model,
			enumValues,
		); err != nil {
			return "", fmt.Errorf("%s: %w", library.OwnerImport, err)
		}
	}
	writeGeneratedRequestWireDecoderHelpers(&output, modelOutput.String())
	output.WriteString(modelOutput.String())

	operations := append([]requestOperationSpec(nil), library.Operations...)
	sort.Slice(operations, func(left, right int) bool {
		return operations[left].CanonicalOperationID <
			operations[right].CanonicalOperationID
	})
	for _, operation := range operations {
		model, err := requestModelWithProvidedWireOwners(
			library.Models[operation.RequestType],
			library.ProvidedModels,
		)
		if err != nil {
			return "", fmt.Errorf(
				"%s: %w",
				operation.CanonicalOperationID,
				err,
			)
		}
		if err := renderRequestEncoder(
			&output,
			operation,
			model,
			enumValues,
		); err != nil {
			return "", fmt.Errorf(
				"%s: %w",
				operation.CanonicalOperationID,
				err,
			)
		}
	}
	return output.String(), nil
}

func requestLibraryWithReachableModels(
	library requestLibrarySpec,
) (requestLibrarySpec, error) {
	// Model-only renderer tests intentionally omit operations. Production
	// libraries always have operation roots and are filtered below.
	if len(library.Operations) == 0 {
		return library, nil
	}
	reachable := make(map[string]struct{}, len(library.Models))
	visiting := map[string]struct{}{}
	var visit func(string) error
	visit = func(name string) error {
		if _, exists := reachable[name]; exists {
			return nil
		}
		model, exists := library.Models[name]
		if !exists {
			return fmt.Errorf(
				"%s request model %s is absent from generated library",
				library.OwnerImport,
				name,
			)
		}
		if _, cyclic := visiting[name]; cyclic {
			return fmt.Errorf(
				"%s request client type cycle includes %s",
				library.OwnerImport,
				name,
			)
		}
		visiting[name] = struct{}{}
		for _, field := range model.Fields {
			dartType, _, err := requestFieldDartType(field)
			if err != nil {
				return fmt.Errorf("%s.%s: %w", name, field.Name, err)
			}
			dependencyName := requestDartModelBaseType(dartType)
			if dependencyName == "" {
				continue
			}
			if _, provided := library.ProvidedModels[dependencyName]; provided {
				continue
			}
			if _, local := library.Models[dependencyName]; !local {
				continue
			}
			if err := visit(dependencyName); err != nil {
				return err
			}
		}
		delete(visiting, name)
		reachable[name] = struct{}{}
		return nil
	}
	for _, operation := range library.Operations {
		if err := visit(strings.TrimSpace(operation.RequestType)); err != nil {
			return requestLibrarySpec{}, err
		}
	}
	filtered := library
	filtered.Models = make(map[string]requestModelSpec, len(reachable))
	for name := range reachable {
		filtered.Models[name] = library.Models[name]
	}
	return filtered, nil
}

func requestDartModelBaseType(value string) string {
	value = strings.TrimSuffix(strings.TrimSpace(value), "?")
	for strings.HasPrefix(value, "List<") && strings.HasSuffix(value, ">") {
		value = strings.TrimSuffix(strings.TrimPrefix(value, "List<"), ">")
		value = strings.TrimSuffix(strings.TrimSpace(value), "?")
	}
	return value
}

func writeGeneratedRequestWireDecoderHelpers(
	output *strings.Builder,
	modelPayload string,
) {
	helpers := []struct {
		reference string
		payload   string
	}{
		{reference: "_generatedRequestObject(", payload: generatedRequestObjectHelper},
		{reference: "_generatedRequestRejectUnknownFields(", payload: generatedRequestUnknownFieldsHelper},
		{reference: "_generatedRequestString(", payload: generatedRequestStringHelper},
		{reference: "_generatedRequestInt(", payload: generatedRequestIntHelper},
		{reference: "_generatedRequestDouble(", payload: generatedRequestDoubleHelper},
		{reference: "_generatedRequestBool(", payload: generatedRequestBoolHelper},
		{reference: "_generatedRequestTimestamp(", payload: generatedRequestTimestampHelper},
		{reference: "_generatedRequestList(", payload: generatedRequestListHelper},
	}
	for _, helper := range helpers {
		if strings.Contains(modelPayload, helper.reference) {
			output.WriteString(helper.payload)
		}
	}
}

const generatedRequestObjectHelper = `Map<String, Object?> _generatedRequestObject(Object? value, String path) {
  if (value is Map<String, Object?>) return value;
  if (value is Map) return Map<String, Object?>.from(value);
  throw FormatException('$path must be an object');
}

`

const generatedRequestUnknownFieldsHelper = `
void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}

`

const generatedRequestStringHelper = `
String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}

`

const generatedRequestIntHelper = `
int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}

`

const generatedRequestDoubleHelper = `
double _generatedRequestDouble(Object? value, String path) {
  if (value is num) return value.toDouble();
  throw FormatException('$path must be a number');
}

`

const generatedRequestBoolHelper = `
bool _generatedRequestBool(Object? value, String path) {
  if (value is bool) return value;
  throw FormatException('$path must be a boolean');
}

`

const generatedRequestTimestampHelper = `
DateTime _generatedRequestTimestamp(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a timestamp');
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$path must be a timestamp');
  return parsed.toUtc();
}

`

const generatedRequestListHelper = `
List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

`

func requestModelWithProvidedWireOwners(
	model requestModelSpec,
	provided map[string]struct{},
) (requestModelSpec, error) {
	if len(provided) == 0 {
		return model, nil
	}
	result := model
	result.Fields = append([]fieldDef(nil), model.Fields...)
	for index, field := range result.Fields {
		if strings.TrimSpace(field.ClientWire) != "" {
			continue
		}
		dartType, _, err := requestFieldDartType(field)
		if err != nil {
			return requestModelSpec{}, err
		}
		baseType := strings.TrimSuffix(dartType, "?")
		if strings.HasPrefix(baseType, "List<") && strings.HasSuffix(baseType, ">") {
			baseType = strings.TrimSuffix(strings.TrimPrefix(baseType, "List<"), ">")
		}
		if _, ownerProvided := provided[baseType]; ownerProvided {
			result.Fields[index].ClientWire = "toWire"
		}
	}
	return result, nil
}

func requestLibraryUsesWireMode(
	library requestLibrarySpec,
	expected string,
) bool {
	for _, model := range library.Models {
		for _, field := range model.Fields {
			if strings.TrimSpace(field.ClientWire) == expected {
				return true
			}
		}
	}
	return false
}

func requestLibraryUsesNormalization(
	library requestLibrarySpec,
	expected ...string,
) bool {
	wanted := make(map[string]struct{}, len(expected))
	for _, value := range expected {
		wanted[value] = struct{}{}
	}
	for _, model := range library.Models {
		for _, field := range model.Fields {
			if _, ok := wanted[strings.TrimSpace(field.ClientNormalization)]; ok {
				return true
			}
		}
	}
	return false
}

func requestLibraryUsesTextListNormalization(
	library requestLibrarySpec,
) bool {
	for _, model := range library.Models {
		for _, field := range model.Fields {
			switch strings.TrimSpace(field.ClientNormalization) {
			case "trim_drop_empty", "trim_dedupe_drop_empty":
				return true
			case "trim":
				dartType, _, err := requestFieldDartType(field)
				if err == nil &&
					strings.TrimSuffix(dartType, "?") == "List<String>" {
					return true
				}
			}
		}
	}
	return false
}
