package main

import (
	"errors"
	"fmt"

	"github.com/vektah/gqlparser/v2/ast"
)

func validateBundleSchemaTypes(schema *ast.Schema, targetTypeName string, projectionFields []string, queries []bundleQueryInput, plan detailBundlePlan) error {
	target := schema.Types[targetTypeName]
	if target == nil || target.Kind != ast.Object {
		return fmt.Errorf("GraphQL schema assembly target %s must be an object matching App lock response type", targetTypeName)
	}
	if err := validateTargetProjectionFields(target, projectionFields); err != nil {
		return err
	}
	mappedSources := map[string]bool{}
	for _, mapping := range plan.AssemblyMappings {
		for _, source := range mapping.Sources {
			mappedSources[source.SourceField] = true
		}
	}
	sourceDefinitions := map[string][]*ast.FieldDefinition{}
	for _, query := range queries {
		root := schema.Types[query.rootTypeName]
		if root == nil || root.Kind != ast.Object {
			return fmt.Errorf("operation %s root type %s must be an object", query.entry.OperationName, query.rootTypeName)
		}
		for _, fieldName := range query.selectedFields {
			field := root.Fields.ForName(fieldName)
			if field == nil || field.Type == nil {
				return fmt.Errorf("operation %s selected field %s is absent from root type %s", query.entry.OperationName, fieldName, root.Name)
			}
			sourceDefinitions[fieldName] = append(sourceDefinitions[fieldName], field)
			if mappedSources[fieldName] {
				continue
			}
			targetField := target.Fields.ForName(fieldName)
			if targetField == nil || targetField.Type == nil || !sameGraphQLType(field.Type, targetField.Type) {
				return fmt.Errorf("direct assembly field %s type differs between %s and %s", fieldName, root.Name, target.Name)
			}
		}
	}
	for fieldName, definitions := range sourceDefinitions {
		if len(definitions) < 2 {
			continue
		}
		for _, definition := range definitions[1:] {
			if !sameGraphQLType(definitions[0].Type, definition.Type) {
				return fmt.Errorf("shared bundle identity field %s has inconsistent types", fieldName)
			}
		}
		definition := schema.Types[definitions[0].Type.Name()]
		if definition == nil || definition.Kind != ast.Scalar && definition.Kind != ast.Enum {
			return fmt.Errorf("shared bundle field %s must be a scalar or enum identity", fieldName)
		}
	}
	for _, mapping := range plan.AssemblyMappings {
		targetField := target.Fields.ForName(mapping.TargetField)
		if targetField == nil || targetField.Type == nil {
			return fmt.Errorf("assembly target field %s is absent from %s", mapping.TargetField, target.Name)
		}
		if err := validateMappingSchemaTypes(schema, targetField, mapping, sourceDefinitions); err != nil {
			return err
		}
	}
	for _, contentType := range plan.SupportedContentTypes {
		assembled, err := assembledFieldSet(contentType, plan.Base, plan.Extensions, plan.AssemblyMappings)
		if err != nil {
			return err
		}
		for _, field := range target.Fields {
			if field.Type != nil && field.Type.NonNull && !assembled[field.Name] {
				return fmt.Errorf("content type %s omits required App projection field %s", contentType, field.Name)
			}
		}
	}
	return nil
}

func validateTargetProjectionFields(target *ast.Definition, projectionFields []string) error {
	actual := make(map[string]bool, len(target.Fields))
	for _, field := range target.Fields {
		actual[field.Name] = true
	}
	if missing := missingFields(projectionFields, actual); len(missing) != 0 {
		return fmt.Errorf("GraphQL assembly target %s misses ContractGraph projection fields: %v", target.Name, missing)
	}
	if extra := extraFields(projectionFields, actual); len(extra) != 0 {
		return fmt.Errorf("GraphQL assembly target %s adds fields outside ContractGraph projection: %v", target.Name, extra)
	}
	return nil
}

func validateMappingSchemaTypes(schema *ast.Schema, targetField *ast.FieldDefinition, mapping assemblyMapping, sources map[string][]*ast.FieldDefinition) error {
	targetObject := schema.Types[targetField.Type.Name()]
	assignedKeys := map[string]bool{}
	if mapping.PresenceSourceField != "" {
		presence := sources[mapping.PresenceSourceField]
		if len(presence) == 0 || presence[0].Type == nil || presence[0].Type.NonNull {
			return fmt.Errorf("assembly presence source %s must be selected and nullable", mapping.PresenceSourceField)
		}
	}
	for _, source := range mapping.Sources {
		definitions := sources[source.SourceField]
		if len(definitions) == 0 {
			return fmt.Errorf("assembly source field %s is not selected by any bundle slice", source.SourceField)
		}
		for _, definition := range definitions[1:] {
			if !sameGraphQLType(definitions[0].Type, definition.Type) {
				return fmt.Errorf("assembly source field %s has inconsistent types across bundle slices", source.SourceField)
			}
		}
		sourceType := definitions[0].Type
		switch source.Strategy {
		case "replace":
			if len(mapping.Sources) != 1 || !sameGraphQLType(sourceType, targetField.Type) {
				return fmt.Errorf("assembly replace %s must be the only source and exact target type", source.SourceField)
			}
		case "merge_object":
			sourceObject := schema.Types[sourceType.Name()]
			if sourceObject == nil || sourceObject.Kind != ast.Object || targetObject == nil || targetObject.Kind != ast.Object {
				return fmt.Errorf("assembly merge_object %s requires object source and target", source.SourceField)
			}
			for _, sourceField := range sourceObject.Fields {
				targetKey := targetObject.Fields.ForName(sourceField.Name)
				if targetKey == nil || !sameGraphQLType(sourceField.Type, targetKey.Type) || assignedKeys[sourceField.Name] {
					return fmt.Errorf("assembly merge_object key %s is absent, type-drifted or conflicting", sourceField.Name)
				}
				assignedKeys[sourceField.Name] = true
			}
		case "assign_key":
			if targetObject == nil || targetObject.Kind != ast.Object || !isListOrObjectType(schema, sourceType) {
				return fmt.Errorf("assembly assign_key %s requires list/object source and object target", source.SourceField)
			}
			targetKey := targetObject.Fields.ForName(source.TargetKey)
			if targetKey == nil || !sameGraphQLType(sourceType, targetKey.Type) || assignedKeys[source.TargetKey] {
				return fmt.Errorf("assembly assign_key target %s is absent, type-drifted or conflicting", source.TargetKey)
			}
			assignedKeys[source.TargetKey] = true
		default:
			return errors.New("assembly mapping contains an unsupported strategy after shape validation")
		}
	}
	return nil
}

func isListOrObjectType(schema *ast.Schema, value *ast.Type) bool {
	if value == nil {
		return false
	}
	if value.Elem != nil {
		return true
	}
	definition := schema.Types[value.Name()]
	return definition != nil && definition.Kind == ast.Object
}

func sameGraphQLType(left, right *ast.Type) bool {
	return left != nil && right != nil && left.String() == right.String()
}
