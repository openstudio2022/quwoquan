package validate

import "quwoquan_service/internal/metadata/graph"

func validateMetadataGovernance(contractGraph *graph.ContractGraph) []Issue {
	var issues []Issue
	issues = append(issues, validateProjectionGovernance(contractGraph)...)
	issues = append(issues, validateActorVocabulary(contractGraph)...)
	issues = append(issues, validateEnumGovernance(contractGraph)...)
	issues = append(issues, validateFieldTypes(contractGraph)...)
	issues = append(issues, validateAuthoritativeFieldOwnership(contractGraph)...)
	issues = append(issues, validateLifecycleGovernance(contractGraph)...)
	issues = append(issues, validateErrorGovernance(contractGraph)...)
	issues = append(issues, validateEventGovernance(contractGraph)...)
	issues = append(issues, validatePrivacyGovernance(contractGraph)...)
	issues = append(issues, validateAppSurfaceGovernance(contractGraph)...)
	return issues
}
