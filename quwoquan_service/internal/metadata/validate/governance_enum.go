package validate

import (
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func validateEnumGovernance(contractGraph *graph.ContractGraph) []Issue {
	definitions := contractGraph.Governance.Enums
	var issues []Issue
	byScope := map[string][]int{}
	byName := map[string][]int{}
	for index, definition := range definitions {
		scopeKey := enumScopeKey(definition)
		byScope[scopeKey] = append(byScope[scopeKey], index)
		byName[definition.Name] = append(byName[definition.Name], index)
		if definition.Name == "" || len(definition.Values) == 0 {
			issues = append(issues, issue(
				"CONTRACT.ENUM.INVALID_DEFINITION",
				definition.SourcePath,
				"enum %q must declare a non-empty value set",
				definition.Name,
			))
		}
		seenValues := map[string]struct{}{}
		for _, value := range definition.Values {
			if _, exists := seenValues[value]; exists {
				issues = append(issues, issue(
					"CONTRACT.ENUM.DUPLICATE_VALUE",
					definition.SourcePath,
					"enum %q declares wire value %q more than once",
					definition.Name,
					value,
				))
			}
			seenValues[value] = struct{}{}
		}
	}
	for _, indexes := range byScope {
		if len(indexes) < 2 {
			continue
		}
		first := definitions[indexes[0]]
		for _, index := range indexes[1:] {
			issues = append(issues, issue(
				"CONTRACT.ENUM.DUPLICATE_OWNER",
				definitions[index].SourcePath,
				"enum %q has duplicate %s owners at %s and %s",
				first.Name,
				first.OwnerLevel,
				first.SourcePath,
				definitions[index].SourcePath,
			))
		}
	}
	for name, indexes := range byName {
		for left := 0; left < len(indexes); left++ {
			for right := left + 1; right < len(indexes); right++ {
				first := definitions[indexes[left]]
				second := definitions[indexes[right]]
				if enumScopesOverlap(first, second) &&
					first.OwnerLevel != second.OwnerLevel {
					issues = append(issues, issue(
						"CONTRACT.ENUM.SHADOWED_OWNER",
						second.SourcePath,
						"enum %q is declared at overlapping %s and %s scopes (%s, %s)",
						name,
						first.OwnerLevel,
						second.OwnerLevel,
						first.SourcePath,
						second.SourcePath,
					))
				}
				if first.OwnerLevel == ast.EnumOwnerObject &&
					second.OwnerLevel == ast.EnumOwnerObject &&
					first.Domain == second.Domain &&
					first.ObjectID != second.ObjectID {
					issues = append(issues, issue(
						"CONTRACT.ENUM.CROSS_OBJECT_DUPLICATE",
						second.SourcePath,
						"enum %q is duplicated by objects %s and %s; move it to the service owner",
						name,
						first.ObjectID,
						second.ObjectID,
					))
				}
			}
		}
	}

	used := map[int]struct{}{}
	for _, reference := range contractGraph.Governance.EnumReferences {
		index := resolveEnumDefinition(definitions, reference)
		if index < 0 {
			issues = append(issues, issue(
				"CONTRACT.ENUM.UNKNOWN_REFERENCE",
				reference.SourcePath,
				"enum_ref %q has no object, service, or global owner",
				reference.Name,
			))
			continue
		}
		used[index] = struct{}{}
	}
	for index, definition := range definitions {
		if _, exists := used[index]; exists {
			continue
		}
		issues = append(issues, issue(
			"CONTRACT.ENUM.DEAD_DEFINITION",
			definition.SourcePath,
			"enum %q owned at %s scope has no resolving enum_ref consumer",
			definition.Name,
			definition.OwnerLevel,
		))
	}
	return issues
}

func enumScopeKey(definition ast.EnumDefinition) string {
	return strings.Join([]string{
		string(definition.OwnerLevel),
		definition.Domain,
		definition.ObjectID,
		definition.Name,
	}, "\x00")
}

func enumScopesOverlap(left, right ast.EnumDefinition) bool {
	if left.Name != right.Name {
		return false
	}
	if left.OwnerLevel == ast.EnumOwnerGlobal || right.OwnerLevel == ast.EnumOwnerGlobal {
		return true
	}
	if left.Domain != right.Domain {
		return false
	}
	if left.OwnerLevel == ast.EnumOwnerService || right.OwnerLevel == ast.EnumOwnerService {
		return true
	}
	return left.ObjectID == right.ObjectID
}

func resolveEnumDefinition(
	definitions []ast.EnumDefinition,
	reference ast.EnumReference,
) int {
	for _, level := range []ast.EnumOwnerLevel{
		ast.EnumOwnerObject,
		ast.EnumOwnerService,
		ast.EnumOwnerGlobal,
	} {
		for index, definition := range definitions {
			if definition.Name != reference.Name || definition.OwnerLevel != level {
				continue
			}
			switch level {
			case ast.EnumOwnerObject:
				if definition.ObjectID == reference.ObjectID {
					return index
				}
			case ast.EnumOwnerService:
				if definition.Domain == reference.Domain {
					return index
				}
			case ast.EnumOwnerGlobal:
				return index
			}
		}
	}
	return -1
}
