package validate

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

func loadSourceFields(
	documents map[string]ast.SourceDocument,
	documentPath string,
	entityName string,
) ([]string, error) {
	document, exists := documents[documentPath]
	if !exists {
		return nil, fmt.Errorf("source document %q does not exist", documentPath)
	}
	var fields fieldsDocument
	if err := json.Unmarshal(document.Content, &fields); err != nil {
		return nil, fmt.Errorf("decode %q: %w", documentPath, err)
	}
	var declarations []fieldDocument
	switch {
	case fields.Entities != nil:
		entity, ok := fields.Entities[entityName]
		if ok {
			declarations = entity.Fields
			break
		}
		if fields.Entity == entityName {
			declarations = fields.Fields
			break
		}
		return nil, fmt.Errorf(
			"source entity %q does not exist in %q",
			entityName,
			documentPath,
		)
	case fields.Entity == entityName:
		declarations = fields.Fields
	default:
		return nil, fmt.Errorf(
			"source entity %q does not exist in %q",
			entityName,
			documentPath,
		)
	}
	result := make([]string, 0, len(declarations))
	for _, field := range declarations {
		result = append(result, strings.TrimSpace(field.Name))
	}
	return result, nil
}

func validateMappedFields(
	sourcePath string,
	object ast.BusinessObjectBoundary,
	sourceFields []string,
) []Issue {
	var issues []Issue
	mapped := map[string]string{}
	for _, role := range businessObjectStorageFieldRoles {
		for _, field := range object.FieldRoles[role] {
			if previous, exists := mapped[field]; exists {
				issues = append(issues, issue(
					"CONTRACT.OBJECT_MAP.FIELD_ROLE_DUPLICATE",
					sourcePath,
					"object %q field %q is classified as both %s and %s",
					object.CanonicalObject,
					field,
					previous,
					role,
				))
			}
			mapped[field] = role
		}
	}
	for _, field := range object.FieldRoles["reference"] {
		if _, exists := mapped[field]; !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_MAP.REFERENCE_WITHOUT_STORAGE_ROLE",
				sourcePath,
				"object %q reference field %q has no persistence role",
				object.CanonicalObject,
				field,
			))
		}
	}

	sourceSet := make(map[string]struct{}, len(sourceFields))
	for _, field := range sourceFields {
		sourceSet[field] = struct{}{}
		if _, exists := mapped[field]; !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_MAP.UNCLASSIFIED_FIELD",
				sourcePath,
				"object %q field %q is not classified",
				object.CanonicalObject,
				field,
			))
		}
	}
	for field := range mapped {
		if _, exists := sourceSet[field]; !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_MAP.UNKNOWN_FIELD",
				sourcePath,
				"object %q classifies unknown field %q",
				object.CanonicalObject,
				field,
			))
		}
	}

	switch object.ObjectKind {
	case ast.ObjectKindAppendOnlyFact:
		issues = append(
			issues,
			requireOnlyRole(sourcePath, object, "append_only_fact")...,
		)
	case ast.ObjectKindProjection:
		issues = append(
			issues,
			requireOnlyRole(sourcePath, object, "projection")...,
		)
	}
	return issues
}

func requireOnlyRole(
	sourcePath string,
	object ast.BusinessObjectBoundary,
	allowedRole string,
) []Issue {
	var disallowed []string
	for role, fields := range object.FieldRoles {
		if role == allowedRole || role == "reference" {
			continue
		}
		for _, field := range fields {
			disallowed = append(disallowed, role+":"+field)
		}
	}
	sort.Strings(disallowed)
	if len(disallowed) == 0 {
		return nil
	}
	return []Issue{issue(
		"CONTRACT.OBJECT_MAP.INVALID_FIELD_ROLE",
		sourcePath,
		"%s %q may only use %s fields; got %s",
		object.ObjectKind,
		object.CanonicalObject,
		allowedRole,
		strings.Join(disallowed, ", "),
	)}
}

func mappedFieldCount(roles map[string][]string) int {
	total := 0
	for _, role := range businessObjectStorageFieldRoles {
		total += len(roles[role])
	}
	return total
}

func requiresFieldSource(kind ast.ObjectKind) bool {
	switch kind {
	case ast.ObjectKindAggregateRoot,
		ast.ObjectKindOwnedEntity,
		ast.ObjectKindValueObject,
		ast.ObjectKindAppendOnlyFact,
		ast.ObjectKindProjection:
		return true
	default:
		return false
	}
}

func validateIdentityFields(
	sourcePath string,
	object ast.BusinessObjectBoundary,
	sourceFields []string,
) []Issue {
	var issues []Issue
	if len(object.Identity.Fields) == 0 {
		issues = append(issues, issue(
			"CONTRACT.OBJECT_REGISTRY.MISSING_IDENTITY_FIELD",
			sourcePath,
			"object %q must bind at least one identity field",
			object.CanonicalObject,
		))
	}
	available := make(map[string]struct{}, len(sourceFields))
	for _, field := range sourceFields {
		available[field] = struct{}{}
	}
	for _, field := range object.Identity.Fields {
		if _, exists := available[field]; !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.UNKNOWN_IDENTITY_FIELD",
				sourcePath,
				"object %q identity field %q is absent from its source entity",
				object.CanonicalObject,
				field,
			))
		}
	}
	if object.Identity.VersionField != "" {
		if _, exists := available[object.Identity.VersionField]; !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.UNKNOWN_VERSION_FIELD",
				sourcePath,
				"object %q version field %q is absent from its source entity",
				object.CanonicalObject,
				object.Identity.VersionField,
			))
		}
	}
	issues = append(issues, validateIdentityLikeFieldRoles(sourcePath, object, sourceFields)...)
	return issues
}

func validateIdentityLikeFieldRoles(
	sourcePath string,
	object ast.BusinessObjectBoundary,
	sourceFields []string,
) []Issue {
	classified := map[string]string{}
	for _, field := range object.Identity.Fields {
		classified[field] = "identity"
	}
	for _, field := range object.FieldRoles["reference"] {
		classified[field] = "typed_reference"
	}
	for _, field := range object.FieldRoles["transport_only"] {
		classified[field] = "transport_only"
	}
	var issues []Issue
	available := make(map[string]struct{}, len(sourceFields))
	for _, field := range sourceFields {
		available[field] = struct{}{}
		if !isIdentityLikeField(field) {
			continue
		}
		if _, ok := classified[field]; ok {
			continue
		}
		if reason := strings.TrimSpace(object.LocalIdentityReasons[field]); reason == "" {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.UNCLASSIFIED_ID_FIELD",
				sourcePath,
				"object %q identity-like field %q must be an object identity, typed relationship reference, transport-only field, or declare local_identity_reasons",
				object.CanonicalObject,
				field,
			))
		}
	}
	for field, reason := range object.LocalIdentityReasons {
		if _, exists := available[field]; !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.UNKNOWN_LOCAL_IDENTITY_FIELD",
				sourcePath,
				"object %q local identity reason references unknown field %q",
				object.CanonicalObject,
				field,
			))
			continue
		}
		if !isIdentityLikeField(field) {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.NON_ID_LOCAL_IDENTITY_REASON",
				sourcePath,
				"object %q field %q is not identity-like and cannot declare local_identity_reasons",
				object.CanonicalObject,
				field,
			))
		}
		if role, exists := classified[field]; exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.REDUNDANT_LOCAL_IDENTITY_REASON",
				sourcePath,
				"object %q field %q is already classified as %s and cannot declare local_identity_reasons",
				object.CanonicalObject,
				field,
				role,
			))
		}
		if strings.TrimSpace(reason) == "" {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.EMPTY_LOCAL_IDENTITY_REASON",
				sourcePath,
				"object %q field %q local identity reason must be non-empty",
				object.CanonicalObject,
				field,
			))
		}
	}
	return issues
}

func isIdentityLikeField(field string) bool {
	trimmed := strings.TrimSpace(field)
	return trimmed == "id" || trimmed == "_id" ||
		strings.HasSuffix(trimmed, "Id") || strings.HasSuffix(trimmed, "Ids") ||
		strings.HasSuffix(trimmed, "ID") || strings.HasSuffix(trimmed, "IDs")
}

func snakeCase(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed != "" && strings.ToUpper(trimmed) == trimmed {
		return strings.ToLower(trimmed)
	}
	var result strings.Builder
	for index, current := range trimmed {
		if current >= 'A' && current <= 'Z' {
			if index > 0 {
				result.WriteByte('_')
			}
			result.WriteRune(current + ('a' - 'A'))
			continue
		}
		result.WriteRune(current)
	}
	return result.String()
}

func equalIntMaps(left, right map[string]int) bool {
	if len(left) != len(right) {
		return false
	}
	for key, value := range left {
		if right[key] != value {
			return false
		}
	}
	return true
}
