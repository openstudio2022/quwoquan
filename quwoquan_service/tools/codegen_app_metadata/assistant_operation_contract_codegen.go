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
	requestSchemaImports := assistantRequestSchemaImports(
		fields,
		service,
		objectSchemas,
	)
	requestSchemaOutputs := make(map[string]struct{}, len(requestSchemaImports))
	for _, output := range requestSchemaImports {
		requestSchemaOutputs[output] = struct{}{}
	}
	requestSchemaTypes := assistantSchemaTypesForOutputs(
		objectSchemas,
		requestSchemaOutputs,
	)
	responseFields := assistantFieldsWithSchemaTypes(fields, schemaTypes)
	responseEntities := assistantDirectResponseEntities(
		responseFields,
		service,
		schemaTypes,
	)
	responseModels := collectAssistantWireEntityClosure(
		responseFields,
		append(append(
			append([]string(nil), responseEntities...),
			"AssistantDeviceActionExecutionReceipt",
		), assistantObjectSchemaResponseRoots(
			responseFields,
			objectSchemas,
		)...),
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
			requestSchemaTypes,
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
			name:   "assistant_stream_event",
			output: "assistant_stream_event.g.dart",
			explicitImports: []string{
				"assistant_runtime_enums.g.dart",
				"assistant_runtime_failure.g.dart",
			},
			suppressedRefs: []string{"RuntimeFailureWire"},
		},
	} {
		schemaPath := filepath.Join(
			metadataDir,
			"assistant",
			schemaSpec.name,
			"schema.yaml",
		)
		schema, readErr := readAssistantContractSchema(schemaPath)
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
		schemaImports, schemaRefs, dependencyErr := assistantObjectSchemaDependencies(
			schema,
			responseFields,
			objectSchemas,
		)
		if dependencyErr != nil {
			return dependencyErr
		}
		schema.Imports = schemaImports
		if assistantSchemaNeedsRuntimeEnums(schema) {
			schema.Imports = append(
				schema.Imports,
				"assistant_runtime_enums.g.dart",
			)
			sort.Strings(schema.Imports)
		}
		localIndex := cloneAssistantContractIndex(contractIndex)
		for _, ref := range schemaRefs {
			// The package-local import above owns this ref. Suppress the
			// App-local library_path from the general schema renderer.
			localIndex.libraryByClass[ref] = schema.LibraryPath
		}
		_, requestOwned := requestSchemaOutputs[objectSchema.output]
		if requestOwned && len(schemaRefs) > 0 {
			return fmt.Errorf(
				"Assistant request-owned schema %s has external refs %s without one wire codec owner",
				schema.DartClass,
				strings.Join(schemaRefs, ", "),
			)
		}
		var rendered string
		if requestOwned {
			rendered = renderAssistantSchemaDrivenWireContract(
				schema,
				localIndex,
				objectSchema.source,
			)
			rendered += renderAssistantWireSchemaDecoder(schema.DartClass)
		} else {
			rendered = renderAssistantSchemaDrivenContract(
				schema,
				localIndex,
				objectSchema.source,
			)
			rendered += renderAssistantSchemaDecoder(schema.DartClass)
		}
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
			requestSchemaImports,
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
		cloned := entityDef{Fields: make([]fieldDef, 0, len(definition.Fields))}
		for _, field := range definition.Fields {
			if strings.EqualFold(strings.TrimSpace(field.APIExposure), "none") {
				continue
			}
			cloned.Fields = append(cloned.Fields, field)
		}
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

func assistantSchemaTypesForOutputs(
	objectSchemas []assistantOperationObjectSchema,
	outputs map[string]struct{},
) map[string]struct{} {
	result := map[string]struct{}{}
	for _, objectSchema := range objectSchemas {
		if _, selected := outputs[objectSchema.output]; !selected {
			continue
		}
		result[objectSchema.schema.DartClass] = struct{}{}
		for _, subcontract := range objectSchema.schema.Subcontracts {
			className := strings.TrimSpace(subcontract.ClassName)
			if className != "" {
				result[className] = struct{}{}
			}
		}
	}
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
	schemaTypes map[string]string,
) []string {
	schemaOwned := make(map[string]struct{}, len(schemaTypes)*2)
	for entityName, dartClass := range schemaTypes {
		schemaOwned[entityName] = struct{}{}
		schemaOwned[dartClass] = struct{}{}
	}
	seen := map[string]struct{}{}
	result := make([]string, 0, len(service.APIRoutes))
	for _, route := range service.APIRoutes {
		name := strings.TrimSpace(route.ResponseEntity)
		if name == "" {
			continue
		}
		if _, owned := schemaOwned[name]; owned {
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

func assistantObjectSchemaDependencies(
	schema *assistantContractSchema,
	responseFields *fieldsFile,
	objectSchemas []assistantOperationObjectSchema,
) ([]string, []string, error) {
	outputByClass := make(map[string]string, len(objectSchemas))
	for _, objectSchema := range objectSchemas {
		outputByClass[objectSchema.schema.DartClass] = objectSchema.output
		for _, subcontract := range objectSchema.schema.Subcontracts {
			className := strings.TrimSpace(subcontract.ClassName)
			if className != "" {
				outputByClass[className] = objectSchema.output
			}
		}
	}

	imports := map[string]struct{}{}
	refs := assistantExternalSchemaRefs(schema)
	for _, ref := range refs {
		if output, exists := outputByClass[ref]; exists {
			if output != schema.LibraryPath {
				imports[output] = struct{}{}
			}
			continue
		}
		if _, exists := responseFields.Entities[ref]; exists {
			imports["assistant_api_responses.g.dart"] = struct{}{}
			continue
		}
		return nil, nil, fmt.Errorf(
			"Assistant object schema %s ref %s has no package-owned generated library",
			schema.DartClass,
			ref,
		)
	}

	result := make([]string, 0, len(imports))
	for path := range imports {
		result = append(result, path)
	}
	sort.Strings(result)
	return result, refs, nil
}

func assistantObjectSchemaResponseRoots(
	responseFields *fieldsFile,
	objectSchemas []assistantOperationObjectSchema,
) []string {
	schemaOwned := map[string]struct{}{}
	for _, objectSchema := range objectSchemas {
		schemaOwned[objectSchema.schema.DartClass] = struct{}{}
		for _, subcontract := range objectSchema.schema.Subcontracts {
			className := strings.TrimSpace(subcontract.ClassName)
			if className != "" {
				schemaOwned[className] = struct{}{}
			}
		}
	}

	seen := map[string]struct{}{}
	for _, objectSchema := range objectSchemas {
		for _, ref := range assistantExternalSchemaRefs(objectSchema.schema) {
			if _, owned := schemaOwned[ref]; owned {
				continue
			}
			if _, exists := responseFields.Entities[ref]; exists {
				seen[ref] = struct{}{}
			}
		}
	}
	result := make([]string, 0, len(seen))
	for ref := range seen {
		result = append(result, ref)
	}
	sort.Strings(result)
	return result
}

func assistantExternalSchemaRefs(schema *assistantContractSchema) []string {
	seenRefs := map[string]struct{}{}
	visitedSubcontracts := map[string]struct{}{}
	var visitFields func([]assistantContractField)
	visitFields = func(fields []assistantContractField) {
		for _, field := range fields {
			ref := strings.TrimSpace(field.Ref)
			if ref == "" {
				continue
			}
			if subcontract, local := schema.Subcontracts[ref]; local {
				if _, visited := visitedSubcontracts[ref]; visited {
					continue
				}
				visitedSubcontracts[ref] = struct{}{}
				visitFields(subcontract.Fields)
				continue
			}
			seenRefs[ref] = struct{}{}
		}
	}
	visitFields(schema.Fields)

	result := make([]string, 0, len(seenRefs))
	for ref := range seenRefs {
		result = append(result, ref)
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
	wireSchemaTypes map[string]struct{},
) string {
	rendered := renderAssistantCloudApiWireDart(
		fields,
		responseModels,
		enumCatalog,
	)
	rendered = assistantRewriteResponseSchemaWireCodecs(
		rendered,
		fields,
		responseModels,
		wireSchemaTypes,
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

func assistantRewriteResponseSchemaWireCodecs(
	rendered string,
	fields *fieldsFile,
	responseModels []string,
	wireSchemaTypes map[string]struct{},
) string {
	if len(wireSchemaTypes) == 0 {
		return rendered
	}
	for _, modelName := range responseModels {
		definition, exists := fields.Entities[modelName]
		if !exists {
			continue
		}
		start := strings.Index(rendered, "class "+modelName+" {")
		if start < 0 {
			continue
		}
		end := len(rendered)
		if next := strings.Index(rendered[start+1:], "\nclass "); next >= 0 {
			end = start + 1 + next
		}
		block := rendered[start:end]
		for _, field := range definition.Fields {
			typeName := assistantSchemaFieldBaseType(field.Type)
			if _, wireOwned := wireSchemaTypes[typeName]; !wireOwned {
				continue
			}
			block = strings.ReplaceAll(
				block,
				typeName+".fromJson(",
				typeName+".fromWire(",
			)
			for _, pair := range [][2]string{
				{
					field.Name + "?.map((item) => item.toJson())",
					field.Name + "?.map((item) => item.toWire())",
				},
				{
					field.Name + ".map((item) => item.toJson())",
					field.Name + ".map((item) => item.toWire())",
				},
				{
					field.Name + "?.toJson()",
					field.Name + "?.toWire()",
				},
				{
					field.Name + ".toJson()",
					field.Name + ".toWire()",
				},
			} {
				block = strings.ReplaceAll(block, pair[0], pair[1])
			}
		}
		rendered = rendered[:start] + block + rendered[end:]
	}
	return rendered
}

func assistantSchemaFieldBaseType(value string) string {
	value = strings.TrimSuffix(strings.TrimSpace(value), "?")
	if strings.HasPrefix(value, "[]") {
		return strings.TrimSpace(strings.TrimPrefix(value, "[]"))
	}
	for _, prefix := range []string{"list<", "List<"} {
		if strings.HasPrefix(value, prefix) && strings.HasSuffix(value, ">") {
			return strings.TrimSpace(strings.TrimSuffix(
				strings.TrimPrefix(value, prefix),
				">",
			))
		}
	}
	return value
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

func renderAssistantWireSchemaDecoder(className string) string {
	className = strings.TrimSpace(className)
	return fmt.Sprintf(
		"\n\n%s decode%s(Object? response) {\n"+
			"  if (response is! Map) {\n"+
			"    throw const FormatException('%s response must be an object');\n"+
			"  }\n"+
			"  return %s.fromWire(response.cast<String, Object?>());\n"+
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
		"export '../generated/assistant/assistant_stream_event.g.dart';\n" +
		"export '../generated/assistant/assistant_runtime_enums.g.dart';\n" +
		objectExports.String() + "\n" +
		"part '../generated/requests/assistant/" +
		"assistant_operation_contracts.g.requests.g.dart';\n"
}
