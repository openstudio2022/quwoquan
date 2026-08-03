package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"
)

const assistantOperationOwnerImport = "../assistant/assistant_operation_contracts.g.dart"

// generateAssistantOperationContracts emits the package-owned Assistant wire
// ABI. App code imports this library through quwoquan_cloud_contracts; it no
// longer decodes Assistant business responses from app-local Map values.
func generateAssistantOperationContracts(metadataDir, appDir string) error {
	fields, service, enumCatalog, err := loadAssistantCloudAPISource(metadataDir)
	if err != nil {
		return err
	}
	generatedDir := filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"generated",
		"assistant",
	)
	writeFile(
		filepath.Join(generatedDir, "assistant_runtime_enums.g.dart"),
		renderAssistantRuntimeEnumsDart(enumCatalog),
	)
	objectSchemas, schemaTypes, err := loadAssistantOperationObjectSchemas(
		metadataDir,
	)
	if err != nil {
		return err
	}
	responseFields := assistantFieldsWithSchemaTypes(fields, schemaTypes)
	responseEntities := assistantDirectResponseEntities(responseFields, service)
	responseModels := collectAssistantWireEntityClosure(
		responseFields,
		append(
			append([]string(nil), responseEntities...),
			"AssistantDeviceActionExecutionReceipt",
		),
	)
	responseModels = assistantExcludeSchemaModels(responseModels, schemaTypes)
	responseSchemaImports := assistantResponseSchemaImports(
		responseFields,
		responseModels,
		objectSchemas,
	)
	writeFile(
		filepath.Join(generatedDir, "assistant_api_responses.g.dart"),
		renderAssistantOperationResponsesDart(
			responseFields,
			responseModels,
			responseEntities,
			enumCatalog,
			responseSchemaImports,
		),
	)

	contractIndex, err := loadAssistantContractIndex(metadataDir)
	if err != nil {
		return err
	}
	for _, schemaSpec := range []struct {
		name            string
		output          string
		explicitImports []string
		suppressedRefs  []string
	}{
		{
			name:            "runtime_failure",
			output:          "assistant_runtime_failure.g.dart",
			explicitImports: []string{"assistant_runtime_enums.g.dart"},
		},
		{
			name:            "assistant_run_envelope",
			output:          "assistant_run_envelope.g.dart",
			explicitImports: []string{"assistant_api_responses.g.dart"},
			suppressedRefs:  []string{"AssistantRunTerminalSnapshotView"},
		},
		{
			name:   "assistant_stream_event",
			output: "assistant_stream_event.g.dart",
			explicitImports: []string{
				"assistant_runtime_enums.g.dart",
				"assistant_runtime_failure.g.dart",
			},
			suppressedRefs: []string{"RuntimeFailureWire"},
		},
	} {
		schema, readErr := readAssistantContractSchema(filepath.Join(
			metadataDir,
			"assistant",
			schemaSpec.name,
			"schema.yaml",
		))
		if readErr != nil {
			return readErr
		}
		schema.LibraryPath = schemaSpec.output
		schema.Imports = append([]string(nil), schemaSpec.explicitImports...)
		localIndex := cloneAssistantContractIndex(contractIndex)
		for _, ref := range schemaSpec.suppressedRefs {
			localIndex.libraryByClass[ref] = schema.LibraryPath
		}
		rendered := renderAssistantSchemaDrivenContract(
			schema,
			localIndex,
			"assistant/_shared/"+schemaSpec.name+"/schema.yaml",
		)
		rendered += renderAssistantSchemaDecoder(schema.DartClass)
		writeFile(filepath.Join(generatedDir, schemaSpec.output), rendered)
	}
	objectSchemaOutputs := make([]string, 0, len(objectSchemas))
	for _, objectSchema := range objectSchemas {
		schema := objectSchema.schema
		schema.LibraryPath = objectSchema.output
		schema.Imports = nil
		if assistantSchemaNeedsRuntimeEnums(schema) {
			schema.Imports = []string{"assistant_runtime_enums.g.dart"}
		}
		rendered := renderAssistantSchemaDrivenContract(
			schema,
			cloneAssistantContractIndex(contractIndex),
			objectSchema.source,
		)
		rendered += renderAssistantSchemaDecoder(schema.DartClass)
		writeFile(filepath.Join(generatedDir, objectSchema.output), rendered)
		objectSchemaOutputs = append(objectSchemaOutputs, objectSchema.output)
	}

	ownerPath := filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"assistant",
		"assistant_operation_contracts.g.dart",
	)
	writeFile(
		ownerPath,
		renderAssistantOperationOwnerLibrary(
			objectSchemaOutputs,
			assistantRequestSchemaImports(fields, service, objectSchemas),
		),
	)
	return nil
}

type assistantOperationObjectSchema struct {
	schema *assistantContractSchema
	source string
	output string
}

func loadAssistantOperationObjectSchemas(
	metadataDir string,
) ([]assistantOperationObjectSchema, map[string]string, error) {
	paths, err := assistantObjectDocumentPaths("schema.yaml")
	if err != nil {
		return nil, nil, fmt.Errorf("discover Assistant object schemas: %w", err)
	}
	sort.Strings(paths)
	result := make([]assistantOperationObjectSchema, 0, len(paths))
	schemaTypes := make(map[string]string, len(paths))
	for _, path := range paths {
		schema, readErr := readAssistantContractSchema(path)
		if readErr != nil {
			return nil, nil, readErr
		}
		objectName := filepath.Base(filepath.Dir(path))
		entityName := objectTypeName(objectName)
		if schema.DartClass == "" {
			return nil, nil, fmt.Errorf(
				"%s is missing dart_class",
				path,
			)
		}
		schemaTypes[entityName] = schema.DartClass
		result = append(result, assistantOperationObjectSchema{
			schema: schema,
			source: filepath.ToSlash(filepath.Join(
				"assistant",
				"assistant",
				objectName,
				"schema.yaml",
			)),
			output: objectName + ".g.dart",
		})
	}
	return result, schemaTypes, nil
}

func assistantFieldsWithSchemaTypes(
	fields *fieldsFile,
	schemaTypes map[string]string,
) *fieldsFile {
	result := &fieldsFile{Entities: map[string]entityDef{}}
	for name, definition := range fields.Entities {
		if _, schemaOwned := schemaTypes[name]; schemaOwned {
			continue
		}
		cloned := entityDef{Fields: append([]fieldDef(nil), definition.Fields...)}
		for index := range cloned.Fields {
			cloned.Fields[index].Type = assistantSchemaWireType(
				cloned.Fields[index].Type,
				schemaTypes,
			)
		}
		result.Entities[name] = cloned
	}
	for _, dartClass := range schemaTypes {
		// Schema-owned types participate in nested response decoding but are
		// emitted from their object-local schema, never from fields.yaml again.
		result.Entities[dartClass] = entityDef{}
	}
	return result
}

func assistantExcludeSchemaModels(
	models []string,
	schemaTypes map[string]string,
) []string {
	schemaOwned := make(map[string]struct{}, len(schemaTypes))
	for _, dartClass := range schemaTypes {
		schemaOwned[dartClass] = struct{}{}
	}
	result := make([]string, 0, len(models))
	for _, model := range models {
		if _, excluded := schemaOwned[model]; excluded {
			continue
		}
		result = append(result, model)
	}
	return result
}

func assistantResponseSchemaImports(
	fields *fieldsFile,
	responseModels []string,
	objectSchemas []assistantOperationObjectSchema,
) []string {
	outputByClass := make(map[string]string, len(objectSchemas))
	for _, objectSchema := range objectSchemas {
		outputByClass[objectSchema.schema.DartClass] = objectSchema.output
	}
	seen := map[string]struct{}{}
	for _, model := range responseModels {
		definition, exists := fields.Entities[model]
		if !exists {
			continue
		}
		for _, field := range definition.Fields {
			typeName := strings.TrimSpace(field.Type)
			typeName = strings.TrimPrefix(typeName, "[]")
			if strings.HasPrefix(typeName, "list<") && strings.HasSuffix(typeName, ">") {
				typeName = strings.TrimSuffix(strings.TrimPrefix(typeName, "list<"), ">")
			}
			if output, exists := outputByClass[typeName]; exists {
				seen[output] = struct{}{}
			}
		}
	}
	result := make([]string, 0, len(seen))
	for output := range seen {
		result = append(result, output)
	}
	sort.Strings(result)
	return result
}

func assistantRequestSchemaImports(
	fields *fieldsFile,
	service *serviceFile,
	objectSchemas []assistantOperationObjectSchema,
) []string {
	outputByClass := map[string]string{}
	for _, objectSchema := range objectSchemas {
		outputByClass[objectSchema.schema.DartClass] = objectSchema.output
		for _, subcontract := range objectSchema.schema.Subcontracts {
			className := strings.TrimSpace(subcontract.ClassName)
			if className != "" {
				outputByClass[className] = objectSchema.output
			}
		}
	}
	seen := map[string]struct{}{}
	for _, route := range service.APIRoutes {
		definition, exists := fields.Entities[strings.TrimSpace(route.RequestEntity)]
		if !exists {
			continue
		}
		for _, field := range definition.Fields {
			typeName := strings.TrimSpace(field.ClientDartType)
			typeName = strings.TrimSuffix(typeName, "?")
			if strings.HasPrefix(typeName, "List<") && strings.HasSuffix(typeName, ">") {
				typeName = strings.TrimSuffix(strings.TrimPrefix(typeName, "List<"), ">")
			}
			if output, exists := outputByClass[typeName]; exists {
				seen[output] = struct{}{}
			}
		}
	}
	result := make([]string, 0, len(seen))
	for output := range seen {
		result = append(result, output)
	}
	sort.Strings(result)
	return result
}

func assistantSchemaWireType(
	value string,
	schemaTypes map[string]string,
) string {
	trimmed := strings.TrimSpace(value)
	for entityName, dartClass := range schemaTypes {
		if trimmed == entityName {
			return dartClass
		}
		if trimmed == "[]"+entityName {
			return "[]" + dartClass
		}
		if trimmed == "list<"+entityName+">" {
			return "list<" + dartClass + ">"
		}
	}
	return value
}

func assistantDirectResponseEntities(
	fields *fieldsFile,
	service *serviceFile,
) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0, len(service.APIRoutes))
	for _, route := range service.APIRoutes {
		name := strings.TrimSpace(route.ResponseEntity)
		if name == "" {
			continue
		}
		if _, exists := fields.Entities[name]; !exists {
			continue
		}
		if _, exists := seen[name]; exists {
			continue
		}
		seen[name] = struct{}{}
		result = append(result, name)
	}
	sort.Strings(result)
	return result
}

func renderAssistantOperationResponsesDart(
	fields *fieldsFile,
	responseModels []string,
	responseEntities []string,
	enumCatalog *assistantEnumCatalog,
	schemaImports []string,
) string {
	rendered := renderAssistantCloudApiWireDart(
		fields,
		responseModels,
		enumCatalog,
	)
	if len(schemaImports) > 0 {
		var imports strings.Builder
		for _, path := range schemaImports {
			fmt.Fprintf(&imports, "import '%s';\n", path)
		}
		rendered = strings.Replace(
			rendered,
			"import 'assistant_runtime_enums.g.dart';\n",
			"import 'assistant_runtime_enums.g.dart';\n"+imports.String(),
			1,
		)
	}
	rendered = strings.Replace(
		rendered,
		"strongly-typed AssistantRepository wire views",
		"canonical Assistant operation response wire types",
		1,
	)
	var decoders strings.Builder
	for _, name := range responseEntities {
		fmt.Fprintf(
			&decoders,
			"\n%s decode%s(Object? response) {\n"+
				"  if (response is! Map) {\n"+
				"    throw const FormatException('%s response must be an object');\n"+
				"  }\n"+
				"  return %s.fromJson(response.cast<String, dynamic>());\n"+
				"}\n",
			name,
			name,
			name,
			name,
		)
	}
	return rendered + decoders.String()
}

func renderAssistantSchemaDecoder(className string) string {
	className = strings.TrimSpace(className)
	return fmt.Sprintf(
		"\n\n%s decode%s(Object? response) {\n"+
			"  if (response is! Map) {\n"+
			"    throw const FormatException('%s response must be an object');\n"+
			"  }\n"+
			"  return %s.fromJson(response.cast<String, dynamic>());\n"+
			"}\n",
		className,
		className,
		className,
		className,
	)
}

func cloneAssistantContractIndex(
	index *assistantContractIndex,
) *assistantContractIndex {
	clone := &assistantContractIndex{
		libraryByClass: map[string]string{},
		fieldsByClass:  map[string][]assistantContractField{},
	}
	if index == nil {
		return clone
	}
	for name, path := range index.libraryByClass {
		clone.libraryByClass[name] = path
	}
	for name, fields := range index.fieldsByClass {
		clone.fieldsByClass[name] = append([]assistantContractField(nil), fields...)
	}
	return clone
}

func renderAssistantOperationOwnerLibrary(
	objectSchemaOutputs []string,
	requestSchemaImports []string,
) string {
	var objectImports strings.Builder
	requestImports := append(
		[]string{"assistant_runtime_enums.g.dart"},
		requestSchemaImports...,
	)
	sort.Strings(requestImports)
	previousImport := ""
	for _, output := range requestImports {
		if output == previousImport {
			continue
		}
		fmt.Fprintf(
			&objectImports,
			"import '../generated/assistant/%s';\n",
			output,
		)
		previousImport = output
	}
	outputs := append([]string(nil), objectSchemaOutputs...)
	sort.Strings(outputs)
	var objectExports strings.Builder
	for _, output := range outputs {
		fmt.Fprintf(
			&objectExports,
			"export '../generated/assistant/%s';\n",
			output,
		)
	}
	return "// Code generated from canonical Assistant contracts. DO NOT EDIT.\n" +
		"library;\n\n" +
		"import '../operation_request_payload.dart';\n" +
		objectImports.String() + "\n" +
		"export '../generated/assistant/assistant_api_responses.g.dart';\n" +
		"export '../generated/assistant/assistant_runtime_failure.g.dart';\n" +
		"export '../generated/assistant/assistant_run_envelope.g.dart';\n" +
		"export '../generated/assistant/assistant_stream_event.g.dart';\n" +
		"export '../generated/assistant/assistant_runtime_enums.g.dart';\n" +
		objectExports.String() + "\n" +
		"part '../generated/requests/assistant/" +
		"assistant_operation_contracts.g.requests.g.dart';\n"
}
