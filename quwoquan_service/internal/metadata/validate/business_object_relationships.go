package validate

import (
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

func validateObjectRelationships(
	sourcePath string,
	domain string,
	object ast.BusinessObjectBoundary,
	boundaries map[string]registeredBoundary,
	members map[string]registeredMember,
) []Issue {
	var issues []Issue
	seen := map[string]struct{}{}
	boundReferenceFields := map[string]string{}
	for _, relationship := range object.Relationships {
		if _, exists := seen[relationship.Name]; exists {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.DUPLICATE_NAME",
				sourcePath,
				"object %q relationship %q is declared more than once",
				object.CanonicalObject,
				relationship.Name,
			))
		}
		seen[relationship.Name] = struct{}{}
		for _, field := range relationship.ReferenceFields {
			if previous, exists := boundReferenceFields[field]; exists {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.DUPLICATE_FIELD_BINDING",
					sourcePath,
					"object %q reference field %q is bound by both %q and %q",
					object.CanonicalObject,
					field,
					previous,
					relationship.Name,
				))
			}
			boundReferenceFields[field] = relationship.Name
		}
		if !oneOf(relationship.Kind, "owned", "reference", "event_source", "projection_source", "external") ||
			!oneOf(relationship.Cardinality, "1:1", "1:N", "N:1", "N:N") ||
			!oneOf(relationship.Consistency, "strong", "eventual", "runtime") ||
			!oneOf(relationship.Access, "aggregate_root", "command_facade", "named_reader", "event", "external_port", "none") ||
			!oneOf(relationship.OnDelete, "cascade", "restrict", "tombstone", "retain", "detach") {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.INVALID_POLICY",
				sourcePath,
				"object %q relationship %q has an invalid kind/cardinality/consistency/access/on_delete policy",
				object.CanonicalObject,
				relationship.Name,
			))
		}
		targetIDs := append([]string{}, relationship.TargetObjects...)
		if relationship.TargetObject != "" {
			targetIDs = append(targetIDs, relationship.TargetObject)
		}
		if len(targetIDs) == 0 ||
			(relationship.TargetObject != "" && len(relationship.TargetObjects) != 0) {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.INVALID_TARGET_SET",
				sourcePath,
				"object %q relationship %q must declare exactly one of target_object or target_objects",
				object.CanonicalObject,
				relationship.Name,
			))
			continue
		}
		if relationship.Kind == "owned" {
			if len(relationship.ReferenceFields) != 0 {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.OWNED_REFERENCE_FIELD",
					sourcePath,
					"owned relationship %s.%s cannot bind reference fields",
					object.CanonicalObject,
					relationship.Name,
				))
			}
			if len(targetIDs) != 1 {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.POLYMORPHIC_OWNERSHIP",
					sourcePath,
					"owned relationship %s.%s must have exactly one target",
					object.CanonicalObject,
					relationship.Name,
				))
				continue
			}
			target, exists := members[targetIDs[0]]
			if !exists {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.UNKNOWN_TARGET",
					sourcePath,
					"object %q relationship %q references unknown target %q",
					object.CanonicalObject,
					relationship.Name,
					targetIDs[0],
				))
				continue
			}
			ownerID := canonicalObjectID(domain, object.CanonicalObject)
			if object.ObjectKind != ast.ObjectKindAggregateRoot ||
				target.Context != object.BoundedContext || target.OwnerID != ownerID ||
				!oneOf(target.Kind, ast.ObjectKindOwnedEntity, ast.ObjectKindValueObject) ||
				relationship.Consistency != "strong" ||
				relationship.Access != "aggregate_root" ||
				!oneOf(relationship.OnDelete, "cascade", "restrict") {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.INVALID_OWNERSHIP",
					sourcePath,
					"owned relationship %s.%s must stay inside one aggregate and use strong aggregate_root access",
					object.CanonicalObject,
					relationship.Name,
				))
			}
			continue
		}
		if len(relationship.ReferenceFields) == 0 {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.MISSING_FIELD_BINDING",
				sourcePath,
				"relationship %s.%s must bind at least one concrete reference field",
				object.CanonicalObject,
				relationship.Name,
			))
		}
		for _, targetID := range targetIDs {
			if member, isMember := members[targetID]; isMember {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.DIRECT_CHILD_ACCESS",
					sourcePath,
					"relationship %s.%s targets aggregate member %q owned by %q",
					object.CanonicalObject,
					relationship.Name,
					targetID,
					member.OwnerID,
				))
				continue
			}
			target, exists := boundaries[targetID]
			if !exists {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.UNKNOWN_TARGET",
					sourcePath,
					"object %q relationship %q references unknown target %q",
					object.CanonicalObject,
					relationship.Name,
					targetID,
				))
				continue
			}
			sameContext := target.Domain == domain && target.Context == object.BoundedContext
			if !sameContext && relationship.Access == "aggregate_root" {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.CROSS_CONTEXT_DIRECT_ACCESS",
					sourcePath,
					"cross-context relationship %s.%s must use command_facade, named_reader, event or external_port",
					object.CanonicalObject,
					relationship.Name,
				))
			}
			if !sameContext && relationship.Consistency == "strong" {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.CROSS_CONTEXT_STRONG_CONSISTENCY",
					sourcePath,
					"cross-context relationship %s.%s cannot claim strong consistency",
					object.CanonicalObject,
					relationship.Name,
				))
			}
			if relationship.Kind == "external" &&
				(target.Object.ObjectKind != ast.ObjectKindExternalReference ||
					relationship.Access != "external_port") {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.INVALID_EXTERNAL_ACCESS",
					sourcePath,
					"external relationship %s.%s must target external_reference through external_port",
					object.CanonicalObject,
					relationship.Name,
				))
			}
		}
	}
	declaredReferenceFields := map[string]struct{}{}
	for _, field := range object.FieldRoles["reference"] {
		declaredReferenceFields[field] = struct{}{}
	}
	for field := range declaredReferenceFields {
		if _, exists := boundReferenceFields[field]; !exists {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.UNBOUND_REFERENCE_FIELD",
				sourcePath,
				"object %q reference field %q has no relationship binding",
				object.CanonicalObject,
				field,
			))
		}
	}
	for field, relationship := range boundReferenceFields {
		if _, exists := declaredReferenceFields[field]; !exists {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.UNKNOWN_REFERENCE_FIELD",
				sourcePath,
				"object %q relationship %q binds non-reference field %q",
				object.CanonicalObject,
				relationship,
				field,
			))
		}
	}
	return issues
}

func validateProjectionSourceRelationship(
	sourcePath string,
	object ast.BusinessObjectBoundary,
) []Issue {
	if object.ObjectKind != ast.ObjectKindProjection {
		return nil
	}
	for _, relationship := range object.Relationships {
		if relationship.Kind == "projection_source" {
			return nil
		}
	}
	return []Issue{issue(
		"CONTRACT.PROJECTION.MISSING_SOURCE_RELATIONSHIP",
		sourcePath,
		"projection object %q must declare at least one projection_source relationship",
		object.CanonicalObject,
	)}
}

func validateCounterSources(
	sourcePath string,
	object ast.BusinessObjectBoundary,
	boundaries map[string]registeredBoundary,
	members map[string]registeredMember,
) []Issue {
	var issues []Issue
	for counter, source := range object.CounterSources {
		parts := strings.Split(strings.TrimSpace(source), ".")
		if len(parts) < 2 || strings.TrimSpace(parts[0]) == "" || strings.TrimSpace(parts[1]) == "" {
			issues = append(issues, issue(
				"CONTRACT.COUNTER_SOURCE.INVALID_REFERENCE",
				sourcePath,
				"object %q counter %q has invalid source %q; expected domain.Object or domain.Object.fact",
				object.CanonicalObject,
				counter,
				source,
			))
			continue
		}
		for _, qualifier := range parts[2:] {
			if strings.TrimSpace(qualifier) == "" {
				issues = append(issues, issue(
					"CONTRACT.COUNTER_SOURCE.INVALID_REFERENCE",
					sourcePath,
					"object %q counter %q has invalid source %q; qualifiers cannot be empty",
					object.CanonicalObject,
					counter,
					source,
				))
				break
			}
		}
		targetID := strings.TrimSpace(parts[0]) + "." + strings.TrimSpace(parts[1])
		if member, exists := members[targetID]; exists {
			issues = append(issues, issue(
				"CONTRACT.COUNTER_SOURCE.DIRECT_CHILD_ACCESS",
				sourcePath,
				"object %q counter %q targets aggregate member %q owned by %q",
				object.CanonicalObject,
				counter,
				targetID,
				member.OwnerID,
			))
			continue
		}
		if _, exists := boundaries[targetID]; !exists {
			issues = append(issues, issue(
				"CONTRACT.COUNTER_SOURCE.UNKNOWN_TARGET",
				sourcePath,
				"object %q counter %q references unknown source object %q",
				object.CanonicalObject,
				counter,
				targetID,
			))
		}
	}
	return issues
}

func canonicalObjectID(domain, object string) string {
	return strings.TrimSpace(domain) + "." + strings.TrimSpace(object)
}

func oneOf[T comparable](value T, allowed ...T) bool {
	for _, candidate := range allowed {
		if value == candidate {
			return true
		}
	}
	return false
}
