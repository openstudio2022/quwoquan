package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

// operationRequestArtifact is the generated request ABI consumed by one
// GeneratedCloudOperationClient method. Request types are emitted as Dart part
// files owned by the existing response/contract library so domain enums and
// nested value objects remain in one library without an import cycle.
type operationRequestArtifact struct {
	RequestType string
	Encoder     string
}

type requestLibrarySpec struct {
	OwnerImport string
	Models      map[string]requestModelSpec
	Operations  []requestOperationSpec
}

type requestModelSpec struct {
	Name   string
	Fields []fieldDef
}

type requestOperationSpec struct {
	CanonicalOperationID string
	RequestType          string
	RequestBodyKind      string
	RequestBindings      appRequestBindings
	RequestConstants     appRequestConstants
}

func writeGeneratedOperationRequests(
	appDir string,
	lock appContractLock,
) (map[string]operationRequestArtifact, error) {
	libraries := map[string]*requestLibrarySpec{}
	artifacts := map[string]operationRequestArtifact{}
	clientOperationCount := 0
	for _, operation := range lock.AppExposedOperations {
		if operation.ClientContract != nil {
			clientOperationCount++
		}
	}
	if clientOperationCount == 0 {
		return nil, fmt.Errorf("empty-green: no App client operation")
	}
	enumValues, err := loadCanonicalRequestEnumValues()
	if err != nil {
		return nil, err
	}

	operations := append([]appExposedOperation(nil), lock.AppExposedOperations...)
	sort.Slice(operations, func(left, right int) bool {
		return operations[left].CanonicalOperationID <
			operations[right].CanonicalOperationID
	})
	for _, operation := range operations {
		client := operation.ClientContract
		if client == nil {
			continue
		}
		requestType := strings.TrimSpace(operation.RequestEntity)
		if requestType == "" {
			return nil, fmt.Errorf(
				"%s App client operation has no canonical request_entity",
				operation.CanonicalOperationID,
			)
		}
		bodyKind := strings.TrimSpace(operation.RequestBodyKind)
		if bodyKind != "object" && bodyKind != "none" {
			return nil, fmt.Errorf(
				"%s request_body_kind must be explicit object or none",
				operation.CanonicalOperationID,
			)
		}
		model, dependencies, err := loadOperationRequestModel(operation, requestType)
		if err != nil {
			return nil, err
		}
		if err := validateRequestModelCanonicalEnums(
			operation.CanonicalOperationID,
			model,
			enumValues,
		); err != nil {
			return nil, err
		}
		if err := validateRequestModelDefaults(
			operation.CanonicalOperationID,
			model,
		); err != nil {
			return nil, err
		}
		bindings := appRequestBindings{}
		if operation.RequestBindings != nil {
			bindings = *operation.RequestBindings
		}
		if err := validateRequestModelBindings(
			operation.CanonicalOperationID,
			model,
			bodyKind,
			bindings,
			operation.RequestConstants,
		); err != nil {
			return nil, err
		}
		if err := validateVersionPreconditionRequestContract(
			operation,
			model,
			bindings,
		); err != nil {
			return nil, err
		}
		clientModel := projectClientRequestModel(model, bindings)
		clientModel, err = applyOperationPaginationContract(
			operation.CanonicalOperationID,
			clientModel,
			bindings,
			operation.Pagination,
		)
		if err != nil {
			return nil, err
		}

		library := libraries[client.DartImport]
		if library == nil {
			library = &requestLibrarySpec{
				OwnerImport: client.DartImport,
				Models:      map[string]requestModelSpec{},
			}
			libraries[client.DartImport] = library
		}
		dependencyNames := make([]string, 0, len(dependencies))
		for name := range dependencies {
			dependencyNames = append(dependencyNames, name)
		}
		sort.Strings(dependencyNames)
		for _, name := range dependencyNames {
			dependency := dependencies[name]
			if err := validateRequestModelCanonicalEnums(
				operation.CanonicalOperationID,
				dependency,
				enumValues,
			); err != nil {
				return nil, err
			}
			if err := validateRequestModelDefaults(
				operation.CanonicalOperationID,
				dependency,
			); err != nil {
				return nil, err
			}
			if previous, exists := library.Models[name]; exists {
				if requestModelFingerprint(previous) != requestModelFingerprint(dependency) {
					return nil, fmt.Errorf(
						"%s reuses request value object %s with a different field contract",
						operation.CanonicalOperationID,
						name,
					)
				}
			} else {
				library.Models[name] = dependency
			}
		}
		if previous, exists := library.Models[requestType]; exists {
			if requestModelFingerprint(previous) != requestModelFingerprint(clientModel) {
				return nil, fmt.Errorf(
					"%s reuses request_entity %s with a different field contract",
					operation.CanonicalOperationID,
					requestType,
				)
			}
		} else {
			library.Models[requestType] = clientModel
		}
		constants := appRequestConstants{}
		if operation.RequestConstants != nil {
			constants = *operation.RequestConstants
		}
		library.Operations = append(library.Operations, requestOperationSpec{
			CanonicalOperationID: operation.CanonicalOperationID,
			RequestType:          requestType,
			RequestBodyKind:      bodyKind,
			RequestBindings:      bindings,
			RequestConstants:     constants,
		})
		artifacts[operation.CanonicalOperationID] = operationRequestArtifact{
			RequestType: requestType,
			Encoder: generatedOperationRequestEncoder(
				operation.CanonicalOperationID,
			),
		}
	}
	if len(artifacts) != clientOperationCount {
		return nil, fmt.Errorf(
			"request artifact coverage mismatch: clients=%d artifacts=%d",
			clientOperationCount,
			len(artifacts),
		)
	}

	imports := make([]string, 0, len(libraries))
	for ownerImport := range libraries {
		imports = append(imports, ownerImport)
	}
	sort.Strings(imports)
	for _, ownerImport := range imports {
		library := libraries[ownerImport]
		outputRelative, ownerRelative, err := requestPartPaths(ownerImport)
		if err != nil {
			return nil, err
		}
		outputPath := filepath.Join(
			appDir,
			"packages",
			"quwoquan_cloud_contracts",
			"lib",
			"src",
			filepath.FromSlash(outputRelative),
		)
		partOfURI, err := filepath.Rel(
			filepath.Dir(filepath.FromSlash(outputRelative)),
			filepath.FromSlash(ownerRelative),
		)
		if err != nil {
			return nil, fmt.Errorf("resolve request part owner: %w", err)
		}
		rendered, err := renderOperationRequestPart(
			*library,
			filepath.ToSlash(partOfURI),
			enumValues,
		)
		if err != nil {
			return nil, err
		}
		writeFile(outputPath, rendered)
	}
	return artifacts, nil
}

func validateRequestModelCanonicalEnums(
	operationID string,
	model requestModelSpec,
	enumValues map[string][]string,
) error {
	violations := make([]string, 0)
	for _, field := range model.Fields {
		if err := validateCanonicalRequestEnumField(field, enumValues); err != nil {
			violations = append(
				violations,
				fmt.Sprintf("%s.%s: %v", model.Name, field.Name, err),
			)
		}
	}
	if len(violations) > 0 {
		return fmt.Errorf(
			"%s request enum contract is not single-track: %s",
			operationID,
			strings.Join(violations, "; "),
		)
	}
	return nil
}

func validateRequestModelDefaults(
	operationID string,
	model requestModelSpec,
) error {
	violations := make([]string, 0)
	for _, field := range model.Fields {
		if !hasRequestConstraint(field, "NOT_BLANK") ||
			!isExplicitEmptyListClientDefault(field.ClientDefault) {
			continue
		}
		dartType, _, err := requestFieldDartType(field)
		if err != nil {
			return fmt.Errorf(
				"%s validate request default %s.%s: %w",
				operationID,
				model.Name,
				field.Name,
				err,
			)
		}
		if !strings.HasPrefix(strings.TrimSuffix(dartType, "?"), "List<") {
			continue
		}
		violations = append(
			violations,
			fmt.Sprintf(
				"%s.%s combines NOT_BLANK with explicit empty list client_default %q",
				model.Name,
				field.Name,
				strings.TrimSpace(field.ClientDefault),
			),
		)
	}
	if len(violations) > 0 {
		return fmt.Errorf(
			"%s request default contract is contradictory: %s",
			operationID,
			strings.Join(violations, "; "),
		)
	}
	return nil
}

func validateVersionPreconditionRequestContract(
	operation appExposedOperation,
	model requestModelSpec,
	bindings appRequestBindings,
) error {
	if strings.TrimSpace(operation.Concurrency.VersionPrecondition) != "if_match" {
		return nil
	}
	ifMatchCount := 0
	for _, binding := range bindings.Header {
		if strings.EqualFold(strings.TrimSpace(binding.Name), "If-Match") {
			ifMatchCount++
			if strings.TrimSpace(binding.Name) != "If-Match" ||
				strings.TrimSpace(binding.Field) != "expectedVersion" {
				return fmt.Errorf(
					"%s if_match must bind canonical If-Match to expectedVersion",
					operation.CanonicalOperationID,
				)
			}
		}
	}
	if ifMatchCount != 1 {
		return fmt.Errorf(
			"%s if_match requires exactly one canonical If-Match binding",
			operation.CanonicalOperationID,
		)
	}
	for _, field := range model.Fields {
		if strings.TrimSpace(field.Name) != "expectedVersion" {
			continue
		}
		if !isRequestNumericField(field) ||
			!hasRequestConstraint(field, "POSITIVE") ||
			strings.TrimSpace(field.ClientWire) != "quoted" {
			return fmt.Errorf(
				"%s expectedVersion must be numeric, POSITIVE, and client_wire quoted",
				operation.CanonicalOperationID,
			)
		}
		return nil
	}
	return fmt.Errorf(
		"%s if_match request entity %s has no expectedVersion field",
		operation.CanonicalOperationID,
		model.Name,
	)
}

func isExplicitEmptyListClientDefault(value string) bool {
	normalized := strings.Join(strings.Fields(value), "")
	normalized = strings.TrimPrefix(normalized, "const")
	if normalized == "[]" {
		return true
	}
	return strings.HasPrefix(normalized, "<") &&
		strings.HasSuffix(normalized, ">[]")
}

func validateCanonicalRequestEnumField(
	field fieldDef,
	enumValues map[string][]string,
) error {
	dartType, _, err := requestFieldDartType(field)
	if err != nil {
		return err
	}
	canonicalType := strings.TrimSuffix(dartType, "?")
	if strings.HasPrefix(canonicalType, "List<") &&
		strings.HasSuffix(canonicalType, ">") {
		canonicalType = strings.TrimSuffix(
			strings.TrimPrefix(canonicalType, "List<"),
			">",
		)
	}
	_, isCanonicalEnum := enumValues[canonicalType]
	mode := strings.TrimSpace(field.ClientWire)
	if len(field.ClientEnumMembers) > 0 && mode != "canonicalEnum" {
		return fmt.Errorf(
			"client_enum_members requires client_wire canonicalEnum",
		)
	}
	enumRef := strings.TrimSpace(field.EnumRef)
	_, hasCanonicalEnumRef := enumValues[enumRef]
	isTypedDartValue := canonicalType != "String" &&
		canonicalType != "int" && canonicalType != "double" &&
		canonicalType != "bool" && canonicalType != "DateTime" &&
		!strings.HasPrefix(canonicalType, "Map<")
	isLegacyEnumWire := mode == "name" || mode == "wire" ||
		mode == "wireValue" || mode == "wireName" ||
		mode == "toApiString"
	if !isTypedDartValue || (!isCanonicalEnum && !hasCanonicalEnumRef &&
		mode != "canonicalEnum" && !isLegacyEnumWire) {
		return nil
	}
	if enumRef == "" {
		return fmt.Errorf(
			"typed enum %s requires explicit enum_ref",
			canonicalType,
		)
	}
	if !hasCanonicalEnumRef {
		return fmt.Errorf("enum_ref %s has no canonical values", enumRef)
	}
	if mode != "canonicalEnum" {
		return fmt.Errorf(
			"typed enum %s requires client_wire canonicalEnum, got %q",
			canonicalType,
			mode,
		)
	}
	if _, err := canonicalRequestEnumMembers(
		field,
		enumValues[enumRef],
	); err != nil {
		return err
	}
	return nil
}

func loadOperationRequestModel(
	operation appExposedOperation,
	requestType string,
) (requestModelSpec, map[string]requestModelSpec, error) {
	fieldsPath := filepath.Join(
		filepath.Dir(operation.SourcePath),
		"fields.yaml",
	)
	var document fieldsFile
	if err := decodeMetadataDocument(
		filepath.Join(activeMetadataRoot, filepath.FromSlash(fieldsPath)),
		&document,
	); err != nil {
		return requestModelSpec{}, nil, fmt.Errorf(
			"%s load request model %s: %w",
			operation.CanonicalOperationID,
			requestType,
			err,
		)
	}
	entities := map[string]entityDef{}
	for name, entity := range document.Entities {
		entities[name] = entity
	}
	for name, entity := range document.Types {
		entities[name] = entity
	}
	for name, entity := range document.ValueObjects {
		entities[name] = entity
	}
	for name, entity := range document.Members {
		entities[name] = entity
	}
	var shared fieldsFile
	sharedPath := filepath.Join(activeMetadataRoot, "_shared", "types.yaml")
	if err := decodeMetadataDocument(sharedPath, &shared); err != nil {
		return requestModelSpec{}, nil, fmt.Errorf(
			"%s load shared request value types: %w",
			operation.CanonicalOperationID,
			err,
		)
	}
	for name, sharedEntity := range shared.Types {
		if local, found := entities[name]; found {
			localModel := requestModelSpec{Name: name, Fields: local.Fields}
			sharedModel := requestModelSpec{Name: name, Fields: sharedEntity.Fields}
			if requestModelFingerprint(localModel) != requestModelFingerprint(sharedModel) {
				return requestModelSpec{}, nil, fmt.Errorf(
					"%s request type %s conflicts with canonical _shared/types.yaml",
					operation.CanonicalOperationID,
					name,
				)
			}
			continue
		}
		entities[name] = sharedEntity
	}
	entity, exists := entities[requestType]
	if !exists && strings.TrimSpace(document.Entity) == requestType && document.Fields != nil {
		entity = entityDef{Fields: append([]fieldDef(nil), document.Fields...)}
		exists = true
	}
	if !exists {
		return requestModelSpec{}, nil, fmt.Errorf(
			"%s request_entity %s is absent from %s",
			operation.CanonicalOperationID,
			requestType,
			fieldsPath,
		)
	}
	root := requestModelSpec{
		Name:   requestType,
		Fields: append([]fieldDef(nil), entity.Fields...),
	}
	dependencies := map[string]requestModelSpec{}
	visiting := map[string]bool{requestType: true}
	var collect func(requestModelSpec) error
	collect = func(model requestModelSpec) error {
		for _, field := range model.Fields {
			typeName := strings.TrimPrefix(strings.TrimSpace(field.Type), "[]")
			dependencyEntity, found := entities[typeName]
			if !found || typeName == requestType {
				continue
			}
			if visiting[typeName] {
				return fmt.Errorf(
					"%s request value object cycle includes %s",
					operation.CanonicalOperationID,
					typeName,
				)
			}
			if _, found := dependencies[typeName]; found {
				continue
			}
			dependency := requestModelSpec{
				Name:   typeName,
				Fields: append([]fieldDef(nil), dependencyEntity.Fields...),
			}
			dependencies[typeName] = dependency
			visiting[typeName] = true
			if err := collect(dependency); err != nil {
				return err
			}
			delete(visiting, typeName)
		}
		return nil
	}
	if err := collect(root); err != nil {
		return requestModelSpec{}, nil, err
	}
	return root, dependencies, nil
}

func validateRequestModelBindings(
	operationID string,
	model requestModelSpec,
	bodyKind string,
	bindings appRequestBindings,
	constants *appRequestConstants,
) error {
	fields := make(map[string]fieldDef, len(model.Fields))
	for _, field := range model.Fields {
		name := strings.TrimSpace(field.Name)
		if name == "" {
			return fmt.Errorf("%s request model has an empty field", operationID)
		}
		if _, exists := fields[name]; exists {
			return fmt.Errorf(
				"%s request model repeats field %s",
				operationID,
				name,
			)
		}
		fields[name] = field
	}
	bound := map[string]string{}
	for _, group := range []struct {
		name   string
		values []appRequestBinding
	}{
		{name: "path", values: bindings.Path},
		{name: "query", values: bindings.Query},
		{name: "header", values: bindings.Header},
		{name: "injected", values: bindings.Injected},
	} {
		for _, binding := range group.values {
			if group.name != "injected" {
				if _, exists := fields[binding.Field]; !exists {
					return fmt.Errorf(
						"%s request_bindings.%s field %s is absent from request_entity %s",
						operationID,
						group.name,
						binding.Field,
						model.Name,
					)
				}
			}
			if previous, exists := bound[binding.Field]; exists {
				return fmt.Errorf(
					"%s request field %s is bound to both %s and %s",
					operationID,
					binding.Field,
					previous,
					group.name,
				)
			}
			bound[binding.Field] = group.name
		}
	}
	unbound := 0
	for _, field := range model.Fields {
		if _, exists := bound[field.Name]; !exists {
			unbound++
		}
	}
	if bodyKind == "none" && unbound != 0 {
		return fmt.Errorf(
			"%s request_body_kind=none leaves %d request_entity fields without a canonical non-body binding",
			operationID,
			unbound,
		)
	}
	if bodyKind == "object" && unbound == 0 {
		if constants == nil || len(constants.Body) == 0 {
			return fmt.Errorf(
				"%s request_body_kind=object has an empty body after canonical bindings",
				operationID,
			)
		}
	}
	if constants == nil {
		return nil
	}
	return validateRequestBodyConstants(
		operationID,
		model,
		bound,
		constants.Body,
	)
}

// projectClientRequestModel removes values owned by the authenticated transport
// boundary. Injected fields remain in the server request entity, but exposing
// them in the App constructor would create a second, spoofable identity input.
func projectClientRequestModel(
	model requestModelSpec,
	bindings appRequestBindings,
) requestModelSpec {
	injected := make(map[string]struct{}, len(bindings.Injected))
	for _, binding := range bindings.Injected {
		if field := strings.TrimSpace(binding.Field); field != "" {
			injected[field] = struct{}{}
		}
	}
	projected := requestModelSpec{
		Name:   model.Name,
		Fields: make([]fieldDef, 0, len(model.Fields)),
	}
	for _, field := range model.Fields {
		if _, isInjected := injected[strings.TrimSpace(field.Name)]; isInjected {
			continue
		}
		projected.Fields = append(projected.Fields, field)
	}
	return projected
}

func applyOperationPaginationContract(
	operationID string,
	model requestModelSpec,
	bindings appRequestBindings,
	policy *appPaginationPolicy,
) (requestModelSpec, error) {
	if policy == nil {
		return model, nil
	}
	if policy.DefaultItems <= 0 || policy.MaximumItems < policy.DefaultItems {
		return requestModelSpec{}, fmt.Errorf(
			"%s has invalid pagination policy default=%d maximum=%d",
			operationID,
			policy.DefaultItems,
			policy.MaximumItems,
		)
	}
	limitField := ""
	for _, binding := range bindings.Query {
		if strings.TrimSpace(binding.Name) == "limit" {
			limitField = strings.TrimSpace(binding.Field)
			break
		}
	}
	if limitField == "" {
		return requestModelSpec{}, fmt.Errorf(
			"%s pagination policy requires one canonical limit query binding",
			operationID,
		)
	}
	for index := range model.Fields {
		if strings.TrimSpace(model.Fields[index].Name) != limitField {
			continue
		}
		if !isRequestNumericField(model.Fields[index]) {
			return requestModelSpec{}, fmt.Errorf(
				"%s pagination field %s must be numeric",
				operationID,
				limitField,
			)
		}
		clientDefault := strings.TrimSpace(model.Fields[index].ClientDefault)
		if clientDefault == "" {
			model.Fields[index].ClientDefault = strconv.Itoa(policy.DefaultItems)
		} else if parsed, err := strconv.Atoi(clientDefault); err == nil &&
			parsed != policy.DefaultItems {
			return requestModelSpec{}, fmt.Errorf(
				"%s pagination field %s client_default=%d differs from policy default=%d",
				operationID,
				limitField,
				parsed,
				policy.DefaultItems,
			)
		}
		model.Fields[index].Constraints = appendUniqueRequestConstraints(
			model.Fields[index].Constraints,
			"POSITIVE",
			fmt.Sprintf("MAX_%d", policy.MaximumItems),
		)
		return model, nil
	}
	return requestModelSpec{}, fmt.Errorf(
		"%s pagination limit field %s is absent from request entity %s",
		operationID,
		limitField,
		model.Name,
	)
}

func appendUniqueRequestConstraints(values []string, additions ...string) []string {
	result := append([]string(nil), values...)
	seen := make(map[string]struct{}, len(result)+len(additions))
	for _, value := range result {
		seen[value] = struct{}{}
	}
	for _, value := range additions {
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func validateRequestBodyConstants(
	operationID string,
	model requestModelSpec,
	bound map[string]string,
	constants []appRequestConstant,
) error {
	seen := map[string]struct{}{}
	bodyFields := map[string]struct{}{}
	for _, field := range model.Fields {
		if _, exists := bound[field.Name]; !exists {
			bodyFields[requestFieldWireName(field)] = struct{}{}
		}
	}
	for _, constant := range constants {
		name := strings.TrimSpace(constant.Name)
		if name == "" {
			return fmt.Errorf("%s request constant has an empty body name", operationID)
		}
		if _, exists := seen[name]; exists {
			return fmt.Errorf("%s repeats request body constant %s", operationID, name)
		}
		seen[name] = struct{}{}
		if _, exists := bodyFields[name]; exists {
			return fmt.Errorf(
				"%s request body constant %s collides with request_entity field",
				operationID,
				name,
			)
		}
		if _, err := dartRequestConstant(constant.Value); err != nil {
			return fmt.Errorf("%s request body constant %s: %w", operationID, name, err)
		}
	}
	return nil
}

func requestModelFingerprint(model requestModelSpec) string {
	var values []string
	for _, field := range model.Fields {
		values = append(values, strings.Join([]string{
			field.Name,
			field.Type,
			field.EnumRef,
			field.ClientDartName,
			field.ClientDartType,
			field.ClientParameterType,
			field.ClientDefault,
			field.ClientNormalization,
			field.ClientWire,
			canonicalRequestEnumMembersFingerprint(field.ClientEnumMembers),
			field.ClientWireName,
			strconv.FormatBool(field.ClientOmitEmpty),
			strconv.FormatBool(field.ClientSpreadBody),
			strings.Join(field.Constraints, ","),
		}, "\x00"))
	}
	return strings.Join(values, "\x01")
}

func requestPartPaths(ownerImport string) (string, string, error) {
	owner := strings.TrimPrefix(strings.TrimSpace(ownerImport), "../")
	if owner == "" || filepath.Ext(owner) != ".dart" ||
		strings.HasPrefix(owner, "../") {
		return "", "", fmt.Errorf(
			"invalid request owner Dart import %q",
			ownerImport,
		)
	}
	stem := strings.TrimSuffix(owner, ".dart")
	return filepath.ToSlash(
		filepath.Join("generated", "requests", stem+".requests.g.dart"),
	), filepath.ToSlash(owner), nil
}

func generatedOperationRequestEncoder(operationID string) string {
	return "encode" + upperCamelIdentifier(operationID) + "GeneratedRequest"
}

func upperCamelIdentifier(value string) string {
	parts := strings.FieldsFunc(value, func(current rune) bool {
		return current == '.' || current == '_' || current == '-'
	})
	var result strings.Builder
	for _, part := range parts {
		normalized := lowerCamel(part)
		if normalized == "" {
			continue
		}
		result.WriteString(strings.ToUpper(normalized[:1]))
		result.WriteString(normalized[1:])
	}
	return result.String()
}

func renderOperationRequestPart(
	library requestLibrarySpec,
	partOfURI string,
	enumValues map[string][]string,
) (string, error) {
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

	modelNames := make([]string, 0, len(library.Models))
	for name := range library.Models {
		modelNames = append(modelNames, name)
	}
	sort.Strings(modelNames)
	for _, name := range modelNames {
		if err := renderRequestModel(
			&output,
			library.Models[name],
			enumValues,
		); err != nil {
			return "", fmt.Errorf("%s: %w", library.OwnerImport, err)
		}
	}

	operations := append([]requestOperationSpec(nil), library.Operations...)
	sort.Slice(operations, func(left, right int) bool {
		return operations[left].CanonicalOperationID <
			operations[right].CanonicalOperationID
	})
	for _, operation := range operations {
		model := library.Models[operation.RequestType]
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

func renderRequestModel(
	output *strings.Builder,
	model requestModelSpec,
	enumValues map[string][]string,
) error {
	fmt.Fprintf(output, "final class %s {\n", model.Name)
	if len(model.Fields) == 0 {
		fmt.Fprintf(output, "  const %s();\n", model.Name)
		output.WriteString("}\n\n")
		return nil
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
	}
	output.WriteString("\n  Map<String, Object?> toJson() => <String, Object?>{\n")
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

func requestFieldDartType(field fieldDef) (string, bool, error) {
	nullable := hasRequestConstraint(field, "NULLABLE")
	dartType := strings.TrimSpace(field.ClientDartType)
	if dartType == "" {
		switch strings.TrimSpace(field.Type) {
		case "string", "ObjectId", "uuid", "identifier":
			dartType = "String"
		case "int", "int32", "int64", "long":
			dartType = "int"
		case "float", "float32", "float64", "double":
			dartType = "double"
		case "bool":
			dartType = "bool"
		case "timestamp", "date":
			dartType = "DateTime"
		case "enum":
			dartType = "String"
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
	case "bool":
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
	case metaType == "timestamp" || metaType == "date":
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
		result = nonNullAccess + ".name"
	case baseDartType == "String" || baseDartType == "int" ||
		baseDartType == "double" || baseDartType == "bool" ||
		strings.HasPrefix(baseDartType, "Map<"):
		result = nonNullAccess
	default:
		return "", fmt.Errorf(
			"field %s (%s) requires canonical client_wire serialization",
			field.Name,
			baseDartType,
		)
	}
	if stringPosition &&
		baseDartType != "String" &&
		mode != "uri_csv" &&
		mode != "quoted" {
		result = "(" + result + ").toString()"
	}
	return result, nil
}

func requestInlineObjectWireExpression(
	access string,
	dartType string,
) (string, error) {
	switch dartType {
	case "HomepageGeoPointInput":
		return "<String, Object?>{" +
			"'lat': " + access + ".lat, " +
			"'lng': " + access + ".lng" +
			"}", nil
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
