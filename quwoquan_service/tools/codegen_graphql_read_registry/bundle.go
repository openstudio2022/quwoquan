package main

import (
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"

	"github.com/vektah/gqlparser/v2/ast"
)

var contentTypePattern = regexp.MustCompile(`^[a-z][a-z0-9_]*$`)

func projectAppClientBundle(
	schema *ast.Schema,
	document *ast.QueryDocument,
	operation *ast.OperationDefinition,
	owner ownerPersistedQueryBinding,
) (*AppClientBundle, error) {
	if owner.AppClientBundle == nil {
		if owner.AssemblyProjectionID != "" || len(owner.AssemblyMappings) != 0 {
			return nil, errors.New("assembly metadata requires appClientBundle")
		}
		return nil, nil
	}
	if strings.TrimSpace(owner.AssemblyProjectionID) == "" {
		return nil, errors.New("appClientBundle requires assemblyProjectionId")
	}
	analyzer := operationAnalyzer{schema: schema, document: document, operation: operation}
	rootFields, err := analyzer.collectFields(schema.Query, operation.SelectionSet, map[string]bool{})
	if err != nil {
		return nil, fmt.Errorf("collect bundle root field: %w", err)
	}
	if len(rootFields) != 1 {
		return nil, fmt.Errorf("appClientBundle operation must select exactly one root field, got %d", len(rootFields))
	}
	var root mergedField
	for _, field := range rootFields {
		root = field
	}
	if root.field == nil || root.field.Definition == nil || root.field.Definition.Type == nil {
		return nil, errors.New("bundle root field definition is unavailable")
	}
	rootType := schema.Types[root.field.Definition.Type.Name()]
	if rootType == nil || rootType.Kind != ast.Object {
		return nil, errors.New("appClientBundle root field must return a concrete object")
	}
	selected, err := analyzer.collectFields(rootType, root.selectionSet, map[string]bool{})
	if err != nil {
		return nil, fmt.Errorf("collect bundle selected fields: %w", err)
	}
	selectedNames := sortedMergedFieldNames(selected)

	projectionName := owner.AssemblyProjectionID
	if separator := strings.LastIndex(projectionName, "."); separator >= 0 {
		projectionName = projectionName[separator+1:]
	}
	if !graphQLName.MatchString(projectionName) {
		return nil, fmt.Errorf("assemblyProjectionId %q has invalid GraphQL type", owner.AssemblyProjectionID)
	}
	projection := schema.Types[projectionName]
	if projection == nil || projection.Kind != ast.Object {
		return nil, fmt.Errorf("assembly projection type %s is unavailable", projectionName)
	}
	if err := validateAssemblyTypes(schema, analyzer, projection, selected, owner.AssemblyMappings); err != nil {
		return nil, err
	}

	binding := owner.AppClientBundle
	bundle := &AppClientBundle{
		BundleID: binding.BundleID, Role: binding.Role,
		SupportedContentTypes:   append([]string(nil), binding.SupportedContentTypes...),
		RequiredForContentTypes: append([]string(nil), binding.RequiredForContentTypes...),
		SelectedFields:          selectedNames,
		AssemblyMappings:        cloneAssemblyMappings(owner.AssemblyMappings),
	}
	if bundle.AssemblyMappings == nil {
		bundle.AssemblyMappings = []AssemblyMapping{}
	}
	if err := validateBundleShape(bundle); err != nil {
		return nil, err
	}
	return bundle, nil
}

func validateAssemblyTypes(
	schema *ast.Schema,
	analyzer operationAnalyzer,
	projection *ast.Definition,
	selected map[string]mergedField,
	mappings []AssemblyMapping,
) error {
	seenTargets := map[string]bool{}
	seenSources := map[string]bool{}
	for index, mapping := range mappings {
		if index > 0 && mappings[index-1].TargetField >= mapping.TargetField {
			return errors.New("assemblyMappings must be unique and sorted by targetField")
		}
		target := projection.Fields.ForName(mapping.TargetField)
		if target == nil || target.Type == nil {
			return fmt.Errorf("assembly target field %s does not exist", mapping.TargetField)
		}
		if seenTargets[mapping.TargetField] {
			return fmt.Errorf("assembly target field %s is duplicated", mapping.TargetField)
		}
		seenTargets[mapping.TargetField] = true
		if _, conflict := selected[mapping.TargetField]; conflict {
			return fmt.Errorf("assembly target field %s conflicts with a selected field", mapping.TargetField)
		}
		if len(mapping.Sources) == 0 {
			return fmt.Errorf("assembly target field %s has no sources", mapping.TargetField)
		}
		mappingSources := map[string]bool{}
		mergeKeys := map[string]bool{}
		assignKeys := map[string]bool{}
		for sourceIndex, source := range mapping.Sources {
			if sourceIndex > 0 && mapping.Sources[sourceIndex-1].SourceField >= source.SourceField {
				return fmt.Errorf("assembly sources for %s must be unique and sorted", mapping.TargetField)
			}
			selectedSource, ok := selected[source.SourceField]
			if !ok || selectedSource.field == nil || selectedSource.field.Definition == nil ||
				selectedSource.field.Definition.Type == nil {
				return fmt.Errorf("assembly source field %s does not exist in the operation selection", source.SourceField)
			}
			if seenSources[source.SourceField] {
				return fmt.Errorf("assembly source field %s is consumed more than once", source.SourceField)
			}
			seenSources[source.SourceField] = true
			mappingSources[source.SourceField] = true
			sourceType := selectedSource.field.Definition.Type
			switch source.Strategy {
			case "replace":
				if source.TargetKey != "" || len(mapping.Sources) != 1 {
					return fmt.Errorf("assembly replace for %s requires exactly one source and forbids targetKey", mapping.TargetField)
				}
				if sourceType.String() != target.Type.String() {
					return fmt.Errorf("assembly replace %s -> %s requires exact type (%s != %s)", source.SourceField, mapping.TargetField, sourceType, target.Type)
				}
			case "assign_key":
				if strings.TrimSpace(source.TargetKey) == "" || assignKeys[source.TargetKey] {
					return fmt.Errorf("assembly assign_key for %s requires a unique targetKey", mapping.TargetField)
				}
				assignKeys[source.TargetKey] = true
				targetObject := schema.Types[target.Type.Name()]
				if targetObject == nil || targetObject.Kind != ast.Object {
					return fmt.Errorf("assembly assign_key target %s must be an object", mapping.TargetField)
				}
				targetKey := targetObject.Fields.ForName(source.TargetKey)
				if targetKey == nil || targetKey.Type == nil {
					return fmt.Errorf("assembly target key %s.%s does not exist", mapping.TargetField, source.TargetKey)
				}
				if sourceType.String() != targetKey.Type.String() {
					return fmt.Errorf("assembly assign_key %s -> %s.%s requires exact type (%s != %s)", source.SourceField, mapping.TargetField, source.TargetKey, sourceType, targetKey.Type)
				}
			case "merge_object":
				if source.TargetKey != "" {
					return fmt.Errorf("assembly merge_object for %s forbids targetKey", mapping.TargetField)
				}
				sourceObject := schema.Types[sourceType.Name()]
				targetObject := schema.Types[target.Type.Name()]
				if sourceObject == nil || sourceObject.Kind != ast.Object || targetObject == nil || targetObject.Kind != ast.Object {
					return fmt.Errorf("assembly merge_object %s -> %s requires object types", source.SourceField, mapping.TargetField)
				}
				nested, err := analyzer.collectFields(sourceObject, selectedSource.selectionSet, map[string]bool{})
				if err != nil {
					return fmt.Errorf("assembly merge source %s: %w", source.SourceField, err)
				}
				for nestedName, nestedField := range nested {
					if mergeKeys[nestedName] {
						return fmt.Errorf("assembly merge_object target %s has conflicting key %s", mapping.TargetField, nestedName)
					}
					mergeKeys[nestedName] = true
					targetField := targetObject.Fields.ForName(nestedName)
					if targetField == nil || targetField.Type == nil || nestedField.field == nil ||
						nestedField.field.Definition == nil || nestedField.field.Definition.Type == nil ||
						nestedField.field.Definition.Type.String() != targetField.Type.String() {
						return fmt.Errorf("assembly merge_object field %s.%s requires exact target type", mapping.TargetField, nestedName)
					}
				}
			default:
				return fmt.Errorf("unsupported assembly strategy %q", source.Strategy)
			}
		}
		if mapping.PresenceSourceField != "" {
			if !mappingSources[mapping.PresenceSourceField] {
				return fmt.Errorf("presenceSourceField %s must reference a source in the same mapping", mapping.PresenceSourceField)
			}
			presence := selected[mapping.PresenceSourceField].field.Definition.Type
			presenceDefinition := schema.Types[presence.Name()]
			if presence.NonNull || presence.Elem != nil || presenceDefinition == nil || presenceDefinition.Kind != ast.Object {
				return fmt.Errorf("presenceSourceField %s must be a nullable object", mapping.PresenceSourceField)
			}
		}
	}
	return nil
}

func validateRegistryBundles(entries []RegistryEntry) error {
	groups := map[string][]RegistryEntry{}
	for _, entry := range entries {
		if entry.AppClientBundle == nil {
			continue
		}
		if err := validateBundleShape(entry.AppClientBundle); err != nil {
			return fmt.Errorf("operation %s appClientBundle: %w", entry.OperationName, err)
		}
		groups[entry.AppClientBundle.BundleID] = append(groups[entry.AppClientBundle.BundleID], entry)
	}
	for bundleID, group := range groups {
		if err := validateBundleGroup(bundleID, group); err != nil {
			return err
		}
	}
	return nil
}

func validateBundleShape(bundle *AppClientBundle) error {
	if bundle == nil || !executorPattern.MatchString(bundle.BundleID) {
		return errors.New("bundleId is required and must be canonical")
	}
	if err := validateSortedContentTypes(bundle.SupportedContentTypes, "supportedContentTypes"); err != nil {
		return err
	}
	if err := validateSortedContentTypes(bundle.RequiredForContentTypes, "requiredForContentTypes"); err != nil {
		return err
	}
	if err := validateSortedNames(bundle.SelectedFields, "selectedFields"); err != nil {
		return err
	}
	switch bundle.Role {
	case "base":
		if len(bundle.SupportedContentTypes) == 0 || len(bundle.RequiredForContentTypes) != 0 {
			return errors.New("base requires supportedContentTypes and forbids requiredForContentTypes")
		}
	case "extension":
		if len(bundle.SupportedContentTypes) != 0 || len(bundle.RequiredForContentTypes) == 0 {
			return errors.New("extension requires non-empty requiredForContentTypes and forbids supportedContentTypes")
		}
	default:
		return fmt.Errorf("unsupported bundle role %q", bundle.Role)
	}
	return nil
}

func validateBundleGroup(bundleID string, entries []RegistryEntry) error {
	baseCount := 0
	var supported []string
	operationNames := map[string]bool{}
	selectedFields := map[string]bool{}
	targets := map[string]bool{}
	sources := map[string]bool{}
	for _, entry := range entries {
		bundle := entry.AppClientBundle
		if operationNames[entry.OperationName] {
			return fmt.Errorf("bundle %s has duplicate operationName %s", bundleID, entry.OperationName)
		}
		operationNames[entry.OperationName] = true
		if bundle.Role == "base" {
			baseCount++
			supported = bundle.SupportedContentTypes
			if !containsName(bundle.SelectedFields, "contentType") {
				return fmt.Errorf("bundle %s base must select contentType", bundleID)
			}
		}
		for _, field := range bundle.SelectedFields {
			selectedFields[field] = true
		}
		for _, mapping := range bundle.AssemblyMappings {
			if targets[mapping.TargetField] {
				return fmt.Errorf("bundle %s assembly target %s is duplicated", bundleID, mapping.TargetField)
			}
			targets[mapping.TargetField] = true
			mappingSources := map[string]bool{}
			for _, source := range mapping.Sources {
				if !containsName(bundle.SelectedFields, source.SourceField) {
					return fmt.Errorf("bundle %s assembly source %s does not exist in its entry selectedFields", bundleID, source.SourceField)
				}
				if sources[source.SourceField] {
					return fmt.Errorf("bundle %s assembly source %s is consumed more than once", bundleID, source.SourceField)
				}
				sources[source.SourceField] = true
				mappingSources[source.SourceField] = true
			}
			if mapping.PresenceSourceField != "" && !mappingSources[mapping.PresenceSourceField] {
				return fmt.Errorf("bundle %s presenceSourceField %s is outside its mapping", bundleID, mapping.PresenceSourceField)
			}
		}
	}
	if baseCount != 1 {
		return fmt.Errorf("bundle %s requires exactly one base, got %d", bundleID, baseCount)
	}
	supportedSet := make(map[string]bool, len(supported))
	for _, contentType := range supported {
		supportedSet[contentType] = true
	}
	for _, entry := range entries {
		if entry.AppClientBundle.Role != "extension" {
			continue
		}
		for _, contentType := range entry.AppClientBundle.RequiredForContentTypes {
			if !supportedSet[contentType] {
				return fmt.Errorf("bundle %s extension %s content type %s is outside base supportedContentTypes", bundleID, entry.OperationName, contentType)
			}
		}
	}
	for target := range targets {
		if selectedFields[target] {
			return fmt.Errorf("bundle %s assembly target %s conflicts with selectedFields", bundleID, target)
		}
	}
	return nil
}

func validateSortedContentTypes(values []string, label string) error {
	for index, value := range values {
		if !contentTypePattern.MatchString(value) || index > 0 && values[index-1] >= value {
			return fmt.Errorf("%s must be closed, unique and sorted", label)
		}
	}
	return nil
}

func validateSortedNames(values []string, label string) error {
	if len(values) == 0 {
		return fmt.Errorf("%s must be non-empty", label)
	}
	for index, value := range values {
		if !graphQLName.MatchString(value) || index > 0 && values[index-1] >= value {
			return fmt.Errorf("%s must be GraphQL names, unique and sorted", label)
		}
	}
	return nil
}

func sortedMergedFieldNames(fields map[string]mergedField) []string {
	result := make([]string, 0, len(fields))
	for name := range fields {
		result = append(result, name)
	}
	sort.Strings(result)
	return result
}

func cloneAppClientBundle(bundle *AppClientBundle) *AppClientBundle {
	if bundle == nil {
		return nil
	}
	return &AppClientBundle{
		BundleID: bundle.BundleID, Role: bundle.Role,
		SupportedContentTypes:   append([]string(nil), bundle.SupportedContentTypes...),
		RequiredForContentTypes: append([]string(nil), bundle.RequiredForContentTypes...),
		SelectedFields:          append([]string(nil), bundle.SelectedFields...),
		AssemblyMappings:        cloneAssemblyMappings(bundle.AssemblyMappings),
	}
}

func cloneAssemblyMappings(mappings []AssemblyMapping) []AssemblyMapping {
	if mappings == nil {
		return nil
	}
	result := make([]AssemblyMapping, len(mappings))
	for index, mapping := range mappings {
		result[index] = AssemblyMapping{
			TargetField: mapping.TargetField, PresenceSourceField: mapping.PresenceSourceField,
			Sources: append([]AssemblySource(nil), mapping.Sources...),
		}
	}
	return result
}

func containsName(values []string, target string) bool {
	index := sort.SearchStrings(values, target)
	return index < len(values) && values[index] == target
}
