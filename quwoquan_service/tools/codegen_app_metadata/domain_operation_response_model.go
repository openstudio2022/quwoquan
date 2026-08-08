package main

import (
	"fmt"
	"path/filepath"
	"strings"
)

func loadOperationResponseModel(
	operation appExposedOperation,
	responseType string,
) (requestModelSpec, map[string]requestModelSpec, error) {
	fieldsPath := filepath.Join(
		filepath.Dir(operation.SourcePath),
		"fields.yaml",
	)
	var document fieldsFile
	if err := decodeMetadataDocument(filepath.Join(
		activeMetadataRoot,
		filepath.FromSlash(fieldsPath),
	), &document); err != nil {
		return requestModelSpec{}, nil, fmt.Errorf(
			"%s load response model %s: %w",
			operation.CanonicalOperationID,
			responseType,
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
	projectionPaths, err := filepath.Glob(filepath.Join(
		activeMetadataRoot,
		filepath.FromSlash(filepath.Dir(operation.SourcePath)),
		"projections",
		"*.yaml",
	))
	if err != nil {
		return requestModelSpec{}, nil, fmt.Errorf(
			"%s list object-local response projections: %w",
			operation.CanonicalOperationID,
			err,
		)
	}
	for _, projectionPath := range projectionPaths {
		projection, projectionErr := readProjection(projectionPath)
		if projectionErr != nil {
			return requestModelSpec{}, nil, fmt.Errorf(
				"%s load object-local response projection %s: %w",
				operation.CanonicalOperationID,
				filepath.Base(projectionPath),
				projectionErr,
			)
		}
		name := strings.TrimSpace(projection.ReadModel)
		if name == "" || len(projection.Fields) == 0 {
			continue
		}
		fields, projectionErr := canonicalProjectionResponseFields(
			projection.Fields,
		)
		if projectionErr != nil {
			return requestModelSpec{}, nil, fmt.Errorf(
				"%s projection %s: %w",
				operation.CanonicalOperationID,
				name,
				projectionErr,
			)
		}
		definition := entityDef{Fields: fields}
		if existing, declared := entities[name]; declared {
			definition = existing
		} else {
			entities[name] = definition
		}
		if dartClass := strings.TrimSpace(projection.ClientProjection.DartClass); dartClass != "" {
			entities[dartClass] = definition
		}
	}
	rootName := toDartExportedName(
		operation.ObjectID[strings.LastIndex(operation.ObjectID, ".")+1:],
	)
	root := entityDef{Fields: append([]fieldDef(nil), document.Fields...)}
	entities[rootName] = root
	if declared := strings.TrimSpace(document.Entity); declared != "" {
		entities[declared] = root
	}
	sharedTypes, err := loadCanonicalSharedValueTypes(operation)
	if err != nil {
		return requestModelSpec{}, nil, err
	}
	for name, entity := range sharedTypes {
		if local, exists := entities[name]; exists {
			if responseModelFingerprint(requestModelSpec{Name: name, Fields: local.Fields}) !=
				responseModelFingerprint(requestModelSpec{Name: name, Fields: entity.Fields}) {
				return requestModelSpec{}, nil, fmt.Errorf(
					"%s response type %s conflicts with canonical _shared/types.yaml",
					operation.CanonicalOperationID,
					name,
				)
			}
			continue
		}
		entities[name] = entity
	}
	entity, exists := entities[responseType]
	if !exists {
		var resolveErr error
		entity, resolveErr = canonicalProjectionResponseDefinition(responseType)
		if resolveErr != nil {
			return requestModelSpec{}, nil, fmt.Errorf(
				"%s response_entity %s has no unique canonical owner: %w",
				operation.CanonicalOperationID,
				responseType,
				resolveErr,
			)
		}
		entities[responseType] = entity
	}
	model := requestModelSpec{
		Name:   responseType,
		Fields: append([]fieldDef(nil), entity.Fields...),
	}
	dependencies := map[string]requestModelSpec{}
	visiting := map[string]bool{responseType: true}
	var collect func(requestModelSpec) error
	collect = func(current requestModelSpec) error {
		for _, field := range current.Fields {
			name := responseFieldReference(field)
			if name == "" || name == responseType || name == current.Name {
				continue
			}
			definition, found := entities[name]
			if !found {
				var resolveErr error
				definition, resolveErr = canonicalProjectionResponseDefinition(name)
				if resolveErr != nil {
					return fmt.Errorf(
						"%s response field %s.%s references undeclared type %s: %w",
						operation.CanonicalOperationID,
						current.Name,
						field.Name,
						name,
						resolveErr,
					)
				}
				entities[name] = definition
			}
			if visiting[name] {
				return fmt.Errorf(
					"%s response value object cycle includes %s",
					operation.CanonicalOperationID,
					name,
				)
			}
			if _, found := dependencies[name]; found {
				continue
			}
			dependency := requestModelSpec{
				Name:   name,
				Fields: append([]fieldDef(nil), definition.Fields...),
			}
			dependencies[name] = dependency
			visiting[name] = true
			if err := collect(dependency); err != nil {
				return err
			}
			delete(visiting, name)
		}
		return nil
	}
	if err := collect(model); err != nil {
		return requestModelSpec{}, nil, err
	}
	return model, dependencies, nil
}

// canonicalProjectionResponseDefinition resolves a response root or nested
// response value from its unique canonical fields/projection owner. This
// permits an explicit composition response to reuse another object's named
// packet while rejecting ambiguous or unowned types.
func canonicalProjectionResponseDefinition(name string) (entityDef, error) {
	definition, _, err := canonicalProjectionResponseDefinitionWithOwner(name)
	return definition, err
}

func canonicalProjectionResponseDefinitionWithOwner(
	name string,
) (entityDef, string, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return entityDef{}, "", fmt.Errorf("canonical response type is required")
	}
	matchedPath := ""
	matchedDefinition := entityDef{}
	register := func(path string, definition entityDef) error {
		if len(definition.Fields) == 0 {
			return nil
		}
		if matchedPath != "" && matchedPath != path {
			first, _ := filepath.Rel(activeMetadataRoot, matchedPath)
			second, _ := filepath.Rel(activeMetadataRoot, path)
			return fmt.Errorf(
				"canonical response type %s has multiple owners: %s, %s",
				name,
				filepath.ToSlash(first),
				filepath.ToSlash(second),
			)
		}
		matchedPath = path
		matchedDefinition = definition
		return nil
	}
	for _, path := range metadataDocumentPaths("", ".yaml") {
		if filepath.Base(filepath.Dir(path)) != "projections" {
			continue
		}
		binding, err := readProjectionBinding(path)
		if err != nil {
			continue
		}
		readModel := strings.TrimSpace(binding.ReadModel)
		if name != readModel {
			continue
		}
		projection, err := readProjection(path)
		if err != nil {
			return entityDef{}, "", err
		}
		if len(projection.Fields) == 0 {
			relative, _ := filepath.Rel(activeMetadataRoot, path)
			return entityDef{}, "", fmt.Errorf(
				"canonical projection owner %s has no top-level fields",
				filepath.ToSlash(relative),
			)
		}
		fields, err := canonicalProjectionResponseFields(projection.Fields)
		if err != nil {
			return entityDef{}, "", err
		}
		if err := register(path, entityDef{Fields: fields}); err != nil {
			return entityDef{}, "", err
		}
	}
	for _, path := range metadataDocumentPaths("", "fields.yaml") {
		var document fieldsFile
		if err := decodeMetadataDocument(path, &document); err != nil {
			return entityDef{}, "", err
		}
		definitions := map[string]entityDef{}
		for key, definition := range document.Entities {
			definitions[key] = definition
		}
		for key, definition := range document.Types {
			definitions[key] = definition
		}
		for key, definition := range document.ValueObjects {
			definitions[key] = definition
		}
		for key, definition := range document.Members {
			definitions[key] = definition
		}
		rootName := strings.TrimSpace(document.Entity)
		if rootName == "" {
			rootName = toDartExportedName(filepath.Base(filepath.Dir(path)))
		}
		if len(document.Fields) > 0 {
			definitions[rootName] = entityDef{Fields: document.Fields}
		}
		definition, exists := definitions[name]
		if !exists {
			continue
		}
		if err := register(path, definition); err != nil {
			return entityDef{}, "", err
		}
	}
	if matchedPath == "" {
		return entityDef{}, "", fmt.Errorf("canonical response type has no owner")
	}
	return matchedDefinition, matchedPath, nil
}

func canonicalProjectionResponseFields(
	fields []projectionFieldDef,
) ([]fieldDef, error) {
	result := make([]fieldDef, 0, len(fields))
	for _, field := range fields {
		name := strings.TrimSpace(field.Name)
		fieldType := strings.TrimSpace(field.WireType)
		if name == "" || fieldType == "" {
			return nil, fmt.Errorf("canonical projection field requires name and type")
		}
		constraints := []string{"NOT_NULL"}
		if field.Nullable {
			constraints = []string{"NULLABLE"}
		}
		result = append(result, fieldDef{
			Name:           name,
			Type:           fieldType,
			EnumRef:        strings.TrimSpace(field.EnumRef),
			Constraints:    constraints,
			ClientWireName: strings.TrimSpace(field.WireName),
			MaxUTF8Bytes:   field.MaxUTF8Bytes,
			MaxItems:       field.MaxItems,
			Format:         strings.TrimSpace(field.Format),
			CoPresentWith:  append([]string(nil), field.CoPresentWith...),
		})
	}
	return result, nil
}

func responseFieldReference(field fieldDef) string {
	if reference := strings.TrimSpace(field.ObjectRef); reference != "" {
		return reference
	}
	typeName := strings.TrimPrefix(strings.TrimSpace(field.Type), "[]")
	switch typeName {
	case "", "string", "tag_ref", "time", "url", "ObjectId", "uuid", "identifier",
		"int", "int32", "int64", "long",
		"float", "float32", "float64", "double",
		"bool", "boolean", "timestamp", "datetime", "date",
		"enum", "object", "json", "jsonb":
		return ""
	default:
		return typeName
	}
}

func collectDomainEnumMembers(
	target map[string][]canonicalRequestEnumMember,
	model requestModelSpec,
	enumValues map[string][]string,
) error {
	for _, field := range model.Fields {
		enumRef := strings.TrimSpace(field.EnumRef)
		if enumRef == "" {
			continue
		}
		values := enumValues[enumRef]
		if len(values) == 0 {
			return fmt.Errorf(
				"%s.%s enum_ref %s has no canonical values",
				model.Name,
				field.Name,
				enumRef,
			)
		}
		members, err := canonicalRequestEnumMembers(field, values)
		if err != nil {
			return err
		}
		if previous, exists := target[enumRef]; exists {
			if domainEnumFingerprint(previous) != domainEnumFingerprint(members) {
				return fmt.Errorf(
					"enum %s has conflicting Dart member mappings",
					enumRef,
				)
			}
			continue
		}
		target[enumRef] = members
	}
	return nil
}

func domainEnumFingerprint(values []canonicalRequestEnumMember) string {
	parts := make([]string, 0, len(values))
	for _, value := range values {
		parts = append(parts, value.WireValue+"="+value.DartMember)
	}
	return strings.Join(parts, ",")
}

func domainEnumWireFingerprint(values []canonicalRequestEnumMember) string {
	parts := make([]string, 0, len(values))
	for _, value := range values {
		parts = append(parts, value.WireValue)
	}
	return strings.Join(parts, "\x00")
}
