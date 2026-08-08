package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

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
	if mode != "" && mode != "canonicalEnum" {
		return fmt.Errorf(
			"typed enum %s only permits implicit enum_ref serialization or client_wire canonicalEnum, got %q",
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
	sharedTypes, err := loadCanonicalSharedValueTypes(operation)
	if err != nil {
		return requestModelSpec{}, nil, err
	}
	for name, sharedEntity := range sharedTypes {
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
	validationKinds := map[string]string{}
	derivedSources := map[string]string{}
	derivedDigests := map[string]string{}
	if err := includeProductOpsIngestRequestTypes(
		operation,
		fieldsPath,
		document,
		entities,
		validationKinds,
		derivedSources,
		derivedDigests,
	); err != nil {
		return requestModelSpec{}, nil, err
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
		Name:           requestType,
		Fields:         append([]fieldDef(nil), entity.Fields...),
		ValidationKind: validationKinds[requestType],
		DerivedSource:  derivedSources[requestType],
		DerivedSHA256:  derivedDigests[requestType],
	}
	dependencies := map[string]requestModelSpec{}
	visiting := map[string]bool{requestType: true}
	var collect func(requestModelSpec) error
	collect = func(model requestModelSpec) error {
		for _, field := range model.Fields {
			dartType, _, typeErr := requestFieldDartType(field)
			if typeErr != nil {
				return fmt.Errorf(
					"%s request value object %s.%s: %w",
					operation.CanonicalOperationID,
					model.Name,
					field.Name,
					typeErr,
				)
			}
			typeName := requestDartModelBaseType(dartType)
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
				Name:           typeName,
				Fields:         append([]fieldDef(nil), dependencyEntity.Fields...),
				ValidationKind: validationKinds[typeName],
				DerivedSource:  derivedSources[typeName],
				DerivedSHA256:  derivedDigests[typeName],
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

func includeProductOpsIngestRequestTypes(
	operation appExposedOperation,
	fieldsPath string,
	document fieldsFile,
	entities map[string]entityDef,
	validationKinds map[string]string,
	derivedSources map[string]string,
	derivedDigests map[string]string,
) error {
	fieldsSourcePath := filepath.Join(activeMetadataRoot, filepath.FromSlash(fieldsPath))
	var ingestContract productOpsIngestFieldsContract
	if err := decodeMetadataDocument(fieldsSourcePath, &ingestContract); err != nil {
		return fmt.Errorf("%s load typed ingest contract: %w", operation.CanonicalOperationID, err)
	}
	switch operation.CanonicalOperationID {
	case "ops.event_record.ReportEventBatch":
		typed := ingestContract.TypedExtensions
		if typed.Catalog != "event_catalog.yaml" ||
			typed.Discriminator != "eventType" ||
			typed.DefinitionsKey != "extension_fields" ||
			typed.RequiredByEventKey != "required_extensions" ||
			typed.OptionalByEventKey != "optional_extensions" ||
			typed.WireEncoding != "flattened" ||
			typed.UnknownFieldPolicy != "reject" {
			return fmt.Errorf(
				"%s requires flattened discriminator-bound typed_extensions with reject unknown-field policy",
				operation.CanonicalOperationID,
			)
		}
		var catalog telemetryEventCatalogFile
		catalogPath := filepath.Join(
			filepath.Dir(fieldsSourcePath),
			"event_catalog.yaml",
		)
		if err := decodeMetadataDocument(catalogPath, &catalog); err != nil {
			return fmt.Errorf("%s load event catalog: %w", operation.CanonicalOperationID, err)
		}
		if len(document.Fields) == 0 || len(catalog.ExtensionFields) == 0 {
			return fmt.Errorf("%s requires EventRecord envelope and typed extensions", operation.CanonicalOperationID)
		}
		fields := append([]fieldDef(nil), document.Fields...)
		names := make([]string, 0, len(catalog.ExtensionFields))
		for name := range catalog.ExtensionFields {
			names = append(names, name)
		}
		sort.Strings(names)
		for _, name := range names {
			extension := catalog.ExtensionFields[name]
			fieldType := map[string]string{
				"string":      "string",
				"int":         "int",
				"double":      "double",
				"bool":        "bool",
				"string_list": "[]string",
			}[extension.Type]
			if fieldType == "" {
				return fmt.Errorf(
					"%s event extension %s has unsupported type %s",
					operation.CanonicalOperationID,
					name,
					extension.Type,
				)
			}
			constraints := []string{"NULLABLE"}
			if extension.Minimum != nil {
				constraints = append(constraints, fmt.Sprintf("MIN_%d", *extension.Minimum))
			}
			if extension.Maximum != nil {
				constraints = append(constraints, fmt.Sprintf("MAX_%d", *extension.Maximum))
			}
			if extension.MaxLength > 0 {
				constraints = append(constraints, fmt.Sprintf("MAX_LENGTH_%d", extension.MaxLength))
			}
			if extension.MaxItems > 0 {
				constraints = append(constraints, fmt.Sprintf("MAX_ITEMS_%d", extension.MaxItems))
			}
			fields = append(fields, fieldDef{
				Name:        name,
				Source:      "event_catalog.extension_fields." + name,
				Type:        fieldType,
				Constraints: constraints,
			})
		}
		entities["EventRecord"] = entityDef{Fields: fields}
		validationKinds["EventRecord"] = requestValidationProductOpsEventRecord
		derivedSources["EventRecord"] = "product_ops/event_record/event_catalog.yaml"
		digest, err := metadataDocumentSHA256(catalogPath)
		if err != nil {
			return fmt.Errorf("%s hash event catalog: %w", operation.CanonicalOperationID, err)
		}
		derivedDigests["EventRecord"] = digest
	case "ops.event_record.ReportRuntimeLogBatch":
		marker, exists := ingestContract.Types["RuntimeLogRecordWire"]
		if !exists || marker.DerivedFrom != "_shared/runtime_observability.yaml#envelope" ||
			len(marker.Fields) != 0 {
			return fmt.Errorf(
				"%s RuntimeLogRecordWire must be the explicit empty derived marker for _shared/runtime_observability.yaml#envelope",
				operation.CanonicalOperationID,
			)
		}
		var catalog runtimeObservabilityContract
		catalogPath := filepath.Join(
			activeMetadataRoot,
			"_shared",
			"runtime_observability.yaml",
		)
		if err := decodeMetadataDocument(catalogPath, &catalog); err != nil {
			return fmt.Errorf("%s load runtime observability contract: %w", operation.CanonicalOperationID, err)
		}
		derived, err := runtimeLogRequestEntities(catalog)
		if err != nil {
			return fmt.Errorf("%s: %w", operation.CanonicalOperationID, err)
		}
		for name, entity := range derived {
			entities[name] = entity
		}
		validationKinds["RuntimeLogRecordWire"] = requestValidationRuntimeLogRecord
		derivedSources["RuntimeLogRecordWire"] = "_shared/runtime_observability.yaml#envelope"
		digest, err := metadataDocumentSHA256(catalogPath)
		if err != nil {
			return fmt.Errorf("%s hash runtime observability contract: %w", operation.CanonicalOperationID, err)
		}
		derivedDigests["RuntimeLogRecordWire"] = digest
	}
	return nil
}

func metadataDocumentSHA256(path string) (string, error) {
	payload, err := readMetadataDocument(path)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(payload)
	return fmt.Sprintf("%x", digest[:]), nil
}

func runtimeLogRequestEntities(
	catalog runtimeObservabilityContract,
) (map[string]entityDef, error) {
	if strings.TrimSpace(catalog.Schema) == "" || len(catalog.Signals) == 0 {
		return nil, fmt.Errorf("runtime_observability.yaml has no schema or signals")
	}
	resource := make([]fieldDef, 0, len(catalog.Envelope.ResourceRequired)+len(catalog.Envelope.ResourceOptional))
	for _, name := range catalog.Envelope.ResourceRequired {
		resource = append(resource, runtimeLogStringField(name, false))
	}
	for _, name := range catalog.Envelope.ResourceOptional {
		resource = append(resource, runtimeLogStringField(name, true))
	}
	correlation := make([]fieldDef, 0, len(catalog.Envelope.CorrelationOptional))
	for _, name := range catalog.Envelope.CorrelationOptional {
		correlation = append(correlation, runtimeLogStringField(name, true))
	}
	attributeNames := map[string]struct{}{}
	for _, signal := range catalog.Signals {
		for _, name := range signal.AttributeAllowlist {
			attributeNames[name] = struct{}{}
		}
	}
	attributes := make([]fieldDef, 0, len(attributeNames))
	orderedAttributes := make([]string, 0, len(attributeNames))
	for name := range attributeNames {
		orderedAttributes = append(orderedAttributes, name)
	}
	sort.Strings(orderedAttributes)
	for _, name := range orderedAttributes {
		field := runtimeLogStringField(name, true)
		if catalog.Limits.MaxAttributeValueLength > 0 {
			field.Constraints = append(
				field.Constraints,
				fmt.Sprintf("MAX_LENGTH_%d", catalog.Limits.MaxAttributeValueLength),
			)
		}
		attributes = append(attributes, field)
	}
	record := []fieldDef{
		{Name: "schema", Source: "runtime_observability.schema", Type: "string", Constraints: []string{"NOT_BLANK"}},
		{Name: "recordId", Source: "runtime_observability.envelope.recordId", Type: "string", Constraints: []string{"NULLABLE"}},
		{Name: "occurredAt", Source: "runtime_observability.envelope.occurredAt", Type: "timestamp", Constraints: []string{"NOT_NULL"}, ClientNormalization: "utc"},
		{Name: "observedAt", Source: "runtime_observability.envelope.observedAt", Type: "timestamp", Constraints: []string{"NOT_NULL"}, ClientNormalization: "utc"},
		{Name: "logKind", Source: "runtime_observability.envelope.logKind", Type: "string", Constraints: []string{"NOT_BLANK"}},
		{Name: "severity", Source: "runtime_observability.envelope.severity", Type: "string", Constraints: []string{"NOT_BLANK"}},
		{Name: "signal", Source: "runtime_observability.envelope.signal", Type: "string", Constraints: []string{"NOT_BLANK"}},
		{Name: "message", Source: "runtime_observability.envelope.message", Type: "string", Constraints: []string{"NOT_NULL"}},
		{Name: "resource", Source: "runtime_observability.envelope.resource", Type: "RuntimeLogResourceWire", Constraints: []string{"NOT_NULL"}},
		{Name: "correlation", Source: "runtime_observability.envelope.correlation", Type: "RuntimeLogCorrelationWire", Constraints: []string{"NULLABLE"}},
	}
	optionalKinds := map[string]string{
		"step": "string", "event": "string", "result": "string", "method": "string",
		"route": "string", "status": "string", "durationMs": "int", "action": "string",
		"target": "string", "errorCode": "string", "fingerprint": "string",
	}
	for _, name := range catalog.Envelope.Optional {
		if name == "recordId" || name == "correlation" || name == "attributes" {
			continue
		}
		fieldType := optionalKinds[name]
		if fieldType == "" {
			return nil, fmt.Errorf("runtime observability optional field %s has no typed wire mapping", name)
		}
		record = append(record, fieldDef{
			Name:        name,
			Source:      "runtime_observability.envelope." + name,
			Type:        fieldType,
			Constraints: []string{"NULLABLE"},
		})
	}
	record = append(record, fieldDef{
		Name:        "attributes",
		Source:      "runtime_observability.envelope.attributes",
		Type:        "RuntimeLogAttributesWire",
		Constraints: []string{"NULLABLE"},
	})
	return map[string]entityDef{
		"RuntimeLogRecordWire":      {Fields: record},
		"RuntimeLogResourceWire":    {Fields: resource},
		"RuntimeLogCorrelationWire": {Fields: correlation},
		"RuntimeLogAttributesWire":  {Fields: attributes},
	}, nil
}

func runtimeLogStringField(name string, nullable bool) fieldDef {
	constraints := []string{"NOT_BLANK"}
	if nullable {
		constraints = []string{"NULLABLE"}
	}
	field := fieldDef{
		Name:        strings.ReplaceAll(name, ".", "Version"),
		Source:      "runtime_observability." + name,
		Type:        "string",
		Constraints: constraints,
	}
	if field.Name != name {
		field.ClientWireName = name
	}
	return field
}

func loadCanonicalSharedValueTypes(
	operation appExposedOperation,
) (map[string]entityDef, error) {
	result := map[string]entityDef{}
	paths := []string{
		filepath.Join(activeMetadataRoot, "_shared", "types.yaml"),
		filepath.Join(
			activeMetadataRoot,
			strings.TrimSpace(operation.Domain),
			"_shared",
			"types.yaml",
		),
	}
	for index, path := range paths {
		var shared fieldsFile
		if err := decodeMetadataDocument(path, &shared); err != nil {
			if index > 0 && os.IsNotExist(err) {
				continue
			}
			return nil, fmt.Errorf(
				"%s load shared value types from %s: %w",
				operation.CanonicalOperationID,
				path,
				err,
			)
		}
		for name, entity := range shared.Types {
			if previous, exists := result[name]; exists {
				left := requestModelSpec{Name: name, Fields: previous.Fields}
				right := requestModelSpec{Name: name, Fields: entity.Fields}
				if requestModelFingerprint(left) != requestModelFingerprint(right) {
					return nil, fmt.Errorf(
						"%s shared value type %s has multiple definitions",
						operation.CanonicalOperationID,
						name,
					)
				}
				continue
			}
			result[name] = entity
		}
	}
	return result, nil
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
		Name:           model.Name,
		Fields:         make([]fieldDef, 0, len(model.Fields)),
		ValidationKind: model.ValidationKind,
		DerivedSource:  model.DerivedSource,
		DerivedSHA256:  model.DerivedSHA256,
		Pagination:     model.Pagination,
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
	requestBodyKind string,
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
	if limitField == "" && strings.TrimSpace(requestBodyKind) == "object" {
		bound := map[string]struct{}{}
		for _, values := range [][]appRequestBinding{
			bindings.Path,
			bindings.Query,
			bindings.Header,
			bindings.Injected,
		} {
			for _, binding := range values {
				bound[strings.TrimSpace(binding.Field)] = struct{}{}
			}
		}
		if _, isNonBodyBinding := bound["limit"]; !isNonBodyBinding {
			for _, field := range model.Fields {
				if strings.TrimSpace(field.Name) == "limit" {
					limitField = "limit"
					break
				}
			}
		}
	}
	if limitField == "" {
		return requestModelSpec{}, fmt.Errorf(
			"%s pagination policy requires one canonical limit query binding or object-body field",
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
		model.Pagination = &requestPaginationSpec{
			Field:        limitField,
			DefaultItems: policy.DefaultItems,
			MaximumItems: policy.MaximumItems,
		}
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
	values := []string{model.ValidationKind, model.DerivedSource, model.DerivedSHA256}
	if model.Pagination != nil {
		values = append(values, strings.Join([]string{
			model.Pagination.Field,
			strconv.Itoa(model.Pagination.DefaultItems),
			strconv.Itoa(model.Pagination.MaximumItems),
		}, "\x00"))
	}
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
