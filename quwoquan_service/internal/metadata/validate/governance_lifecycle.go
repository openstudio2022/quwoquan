package validate

import (
	"sort"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func validateLifecycleGovernance(contractGraph *graph.ContractGraph) []Issue {
	objects := map[string]ast.Object{}
	for _, object := range contractGraph.Objects {
		objects[object.ID] = object
	}
	fieldsByObject := map[string]map[string]ast.FieldDefinition{}
	for _, field := range contractGraph.Governance.Fields {
		object, exists := objects[field.ObjectID]
		if !exists || field.Entity != object.Name {
			continue
		}
		if fieldsByObject[field.ObjectID] == nil {
			fieldsByObject[field.ObjectID] = map[string]ast.FieldDefinition{}
		}
		fieldsByObject[field.ObjectID][field.Name] = field
	}
	var issues []Issue
	for _, packet := range contractGraph.Governance.Objects {
		object := objects[packet.ObjectID]
		lifecycle := packet.Lifecycle
		if object.Kind == ast.ObjectKindAppendOnlyFact &&
			(lifecycle == nil || !lifecycle.Immutable) {
			issues = append(issues, issue(
				"CONTRACT.LIFECYCLE.FACT_NOT_IMMUTABLE",
				packet.SourcePath,
				"append-only fact %q must declare lifecycle.immutable=true",
				packet.ObjectID,
			))
		}
		if lifecycle == nil {
			continue
		}
		if lifecycle.Immutable {
			if object.Kind != ast.ObjectKindAppendOnlyFact {
				issues = append(issues, issue(
					"CONTRACT.LIFECYCLE.IMMUTABLE_NON_FACT",
					lifecycle.SourcePath,
					"object %q declares lifecycle.immutable but kind is %q",
					packet.ObjectID,
					object.Kind,
				))
			}
			if lifecycle.StateField != "" {
				issues = append(issues, issue(
					"CONTRACT.LIFECYCLE.IMMUTABLE_STATE_FIELD",
					lifecycle.SourcePath,
					"immutable object %q must not declare lifecycle.state_field",
					packet.ObjectID,
				))
			}
			continue
		}
		if len(lifecycle.States) == 0 {
			continue
		}
		if lifecycle.StateField == "" {
			issues = append(issues, issue(
				"CONTRACT.LIFECYCLE.MISSING_STATE_FIELD",
				lifecycle.SourcePath,
				"stateful object %q must declare lifecycle.state_field",
				packet.ObjectID,
			))
			continue
		}
		field, exists := fieldsByObject[packet.ObjectID][lifecycle.StateField]
		if !exists {
			issues = append(issues, issue(
				"CONTRACT.LIFECYCLE.UNKNOWN_STATE_FIELD",
				lifecycle.SourcePath,
				"object %q lifecycle.state_field %q is not declared in fields.yaml",
				packet.ObjectID,
				lifecycle.StateField,
			))
			continue
		}
		if field.Type != "enum" || field.EnumRef == "" {
			issues = append(issues, issue(
				"CONTRACT.LIFECYCLE.UNTYPED_STATE_FIELD",
				field.SourcePath,
				"object %q state field %q must use type=enum and enum_ref",
				packet.ObjectID,
				lifecycle.StateField,
			))
			continue
		}
		definitionIndex := resolveEnumDefinition(
			contractGraph.Governance.Enums,
			ast.EnumReference{
				Name:       field.EnumRef,
				Domain:     field.Domain,
				ObjectID:   field.ObjectID,
				SourcePath: field.SourcePath,
			},
		)
		if definitionIndex >= 0 && !sameStringSet(
			lifecycle.States,
			contractGraph.Governance.Enums[definitionIndex].Values,
		) {
			issues = append(issues, issue(
				"CONTRACT.LIFECYCLE.ENUM_DRIFT",
				lifecycle.SourcePath,
				"object %q lifecycle states do not exactly match enum %q",
				packet.ObjectID,
				field.EnumRef,
			))
		}
	}
	return issues
}

func sameStringSet(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	leftCopy := append([]string(nil), left...)
	rightCopy := append([]string(nil), right...)
	sort.Strings(leftCopy)
	sort.Strings(rightCopy)
	for index := range leftCopy {
		if leftCopy[index] != rightCopy[index] {
			return false
		}
	}
	return true
}
