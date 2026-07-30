package validate

import (
	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func validateProjectionGovernance(contractGraph *graph.ContractGraph) []Issue {
	var issues []Issue
	dartClasses := map[string]ast.Projection{}
	outputPaths := map[string]ast.Projection{}
	for _, projection := range contractGraph.Projections {
		if !projection.ReadModelExplicit {
			issues = append(issues, issue(
				"CONTRACT.PROJECTION.NON_CANONICAL_IDENTITY",
				projection.SourcePath,
				"projection %q must declare read_model; dart_class/projection/name are not projection identities",
				projection.ID,
			))
		}
		if len(projection.FieldNames) == 0 {
			issues = append(issues, issue(
				"CONTRACT.PROJECTION.MISSING_CANONICAL_FIELDS",
				projection.SourcePath,
				"projection %q must declare a non-empty canonical field shape",
				projection.ID,
			))
		}
		seenFields := map[string]struct{}{}
		for _, field := range projection.FieldNames {
			if _, exists := seenFields[field]; exists {
				issues = append(issues, issue(
					"CONTRACT.PROJECTION.DUPLICATE_FIELD",
					projection.SourcePath,
					"projection %q declares field %q more than once",
					projection.ID,
					field,
				))
			}
			seenFields[field] = struct{}{}
		}
		hasClientPath := projection.OutputPath != "" || projection.ExternalDartPath != ""
		hasDartClass := projection.DartClass != ""
		if hasDartClass != hasClientPath {
			issues = append(issues, issue(
				"CONTRACT.PROJECTION.INCOMPLETE_CLIENT_OUTPUT",
				projection.SourcePath,
				"projection %q client output requires both dart_class and output_path",
				projection.ID,
			))
		}
		if projection.DartClass != "" {
			if previous, exists := dartClasses[projection.DartClass]; exists {
				issues = append(issues, issue(
					"CONTRACT.PROJECTION.DUPLICATE_DART_CLASS",
					projection.SourcePath,
					"dart class %q is owned by both %s and %s",
					projection.DartClass,
					previous.SourcePath,
					projection.SourcePath,
				))
			} else {
				dartClasses[projection.DartClass] = projection
			}
		}
		if projection.OutputPath != "" {
			if previous, exists := outputPaths[projection.OutputPath]; exists {
				issues = append(issues, issue(
					"CONTRACT.PROJECTION.DUPLICATE_OUTPUT_PATH",
					projection.SourcePath,
					"client output path %q is owned by both %s and %s",
					projection.OutputPath,
					previous.SourcePath,
					projection.SourcePath,
				))
			} else {
				outputPaths[projection.OutputPath] = projection
			}
		}
	}
	return issues
}
