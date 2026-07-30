package validate

import (
	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func validatePrivacyGovernance(contractGraph *graph.ContractGraph) []Issue {
	objects := map[string]ast.Object{}
	objectsByDomainName := map[string]ast.Object{}
	for _, object := range contractGraph.Objects {
		objects[object.ID] = object
		objectsByDomainName[object.Domain+"\x00"+object.Name] = object
	}
	rootFields := map[string]map[string]struct{}{}
	for _, field := range contractGraph.Governance.Fields {
		object, exists := objects[field.ObjectID]
		if !exists || field.Entity != object.Name {
			continue
		}
		if rootFields[field.ObjectID] == nil {
			rootFields[field.ObjectID] = map[string]struct{}{}
		}
		rootFields[field.ObjectID][field.Name] = struct{}{}
	}

	var issues []Issue
	for _, packet := range contractGraph.Governance.Objects {
		privacy := packet.Privacy
		if privacy == nil {
			continue
		}
		object, exists := objects[packet.ObjectID]
		if !exists {
			continue
		}
		if privacy.Aggregate != object.Name {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.AGGREGATE_MISMATCH",
				privacy.SourcePath,
				"privacy aggregate %q must equal canonical object %q",
				privacy.Aggregate,
				object.Name,
			))
		}
		fieldGroups := []struct {
			kind   string
			fields []string
		}{
			{kind: "app_log_policy", fields: privacy.AppLogFields},
			{kind: "field_visibility", fields: privacy.VisibilityFields},
			{kind: "anonymization_on_delete", fields: privacy.AnonymizationFields},
		}
		for _, group := range fieldGroups {
			seen := map[string]struct{}{}
			for _, field := range group.fields {
				if _, duplicate := seen[field]; duplicate {
					issues = append(issues, issue(
						"CONTRACT.PRIVACY.DUPLICATE_FIELD_REFERENCE",
						privacy.SourcePath,
						"privacy %s references field %q more than once",
						group.kind,
						field,
					))
					continue
				}
				seen[field] = struct{}{}
				if _, fieldExists := rootFields[packet.ObjectID][field]; !fieldExists {
					issues = append(issues, issue(
						"CONTRACT.PRIVACY.UNKNOWN_FIELD",
						privacy.SourcePath,
						"privacy %s references unknown %s field %q",
						object.ID,
						group.kind,
						field,
					))
				}
			}
		}
		seenTargets := map[string]struct{}{}
		for _, target := range privacy.DeletionTargets {
			if _, duplicate := seenTargets[target]; duplicate {
				issues = append(issues, issue(
					"CONTRACT.PRIVACY.DUPLICATE_DELETION_TARGET",
					privacy.SourcePath,
					"privacy %s references deletion target %q more than once",
					object.ID,
					target,
				))
				continue
			}
			seenTargets[target] = struct{}{}
			if _, targetExists := objectsByDomainName[object.Domain+"\x00"+target]; !targetExists {
				issues = append(issues, issue(
					"CONTRACT.PRIVACY.UNKNOWN_DELETION_TARGET",
					privacy.SourcePath,
					"privacy %s references unknown same-domain object %q",
					object.ID,
					target,
				))
			}
		}
	}
	return issues
}
