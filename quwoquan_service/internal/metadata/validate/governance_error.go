package validate

import (
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func validateErrorGovernance(contractGraph *graph.ContractGraph) []Issue {
	type ownedErrorDefinition struct {
		definition ast.ErrorDefinition
		objectID   string
		domain     string
	}
	operationsByObject := map[string]map[string]ast.Operation{}
	operationsByID := map[string]ast.Operation{}
	for _, operation := range contractGraph.Operations {
		if operationsByObject[operation.ObjectID] == nil {
			operationsByObject[operation.ObjectID] = map[string]ast.Operation{}
		}
		operationsByObject[operation.ObjectID][operation.LocalID] = operation
		operationsByID[operation.ID] = operation
	}
	objectsByID := map[string]ast.Object{}
	for _, object := range contractGraph.Objects {
		objectsByID[object.ID] = object
	}
	definitionsByCode := map[string][]ownedErrorDefinition{}
	for _, packet := range contractGraph.Governance.Objects {
		for _, definition := range packet.Errors {
			domain := packet.Domain
			if domain == "" {
				domain = objectsByID[packet.ObjectID].Domain
			}
			definitionsByCode[definition.Code] = append(
				definitionsByCode[definition.Code],
				ownedErrorDefinition{
					definition: definition,
					objectID:   packet.ObjectID,
					domain:     domain,
				},
			)
		}
	}
	allowedSurfaces := map[string]struct{}{
		"http": {}, "rpc": {}, "worker": {}, "consumer": {},
		"provider_callback": {}, "terminal_snapshot": {}, "app": {},
		"player": {}, "control_plane": {}, "gateway": {}, "graphql": {},
	}
	var issues []Issue
	for code, definitions := range definitionsByCode {
		if len(definitions) < 2 {
			continue
		}
		first := definitions[0]
		for _, duplicate := range definitions[1:] {
			issues = append(issues, issue(
				"CONTRACT.ERROR.DUPLICATE_CODE_OWNER",
				duplicate.definition.SourcePath,
				"error %q is owned by both %s (%s) and %s (%s)",
				code,
				first.objectID,
				first.definition.SourcePath,
				duplicate.objectID,
				duplicate.definition.SourcePath,
			))
		}
	}
	for _, packet := range contractGraph.Governance.Objects {
		for _, definition := range packet.Errors {
			ownerDomain := packet.Domain
			if ownerDomain == "" {
				ownerDomain = objectsByID[packet.ObjectID].Domain
			}
			if len(definition.EmittedBy) == 0 {
				issues = append(issues, issue(
					"CONTRACT.ERROR.MISSING_EMISSION_SURFACE",
					definition.SourcePath,
					"error %q must declare emitted_by surfaces",
					definition.Code,
				))
				continue
			}
			hasHTTP := false
			for _, emission := range definition.EmittedBy {
				if _, allowed := allowedSurfaces[emission.Surface]; !allowed {
					issues = append(issues, issue(
						"CONTRACT.ERROR.UNKNOWN_EMISSION_SURFACE",
						definition.SourcePath,
						"error %q uses unknown emitted_by surface %q",
						definition.Code,
						emission.Surface,
					))
					continue
				}
				if emission.Surface != "http" && emission.Surface != "graphql" &&
					emission.Surface != "gateway" {
					continue
				}
				hasHTTP = true
				if emission.Surface == "gateway" {
					if ownerDomain != "gateway" {
						issues = append(issues, issue(
							"CONTRACT.ERROR.GATEWAY_SURFACE_OWNER",
							definition.SourcePath,
							"gateway error %q must be owned by domain gateway",
							definition.Code,
						))
					}
					if len(emission.Operations) != 0 {
						issues = append(issues, issue(
							"CONTRACT.ERROR.GATEWAY_SURFACE_OPERATION",
							definition.SourcePath,
							"gateway error %q applies to generated operations and must not copy an operation list",
							definition.Code,
						))
					}
					continue
				}
				if len(emission.Operations) == 0 {
					issues = append(issues, issue(
						"CONTRACT.ERROR.HTTP_MISSING_OPERATION",
						definition.SourcePath,
						"HTTP/GraphQL error %q must bind at least one canonical operation",
						definition.Code,
					))
				}
				for _, operationRef := range emission.Operations {
					operation, exists := operationsByObject[packet.ObjectID][operationRef]
					if strings.Contains(operationRef, ".") {
						operation, exists = operationsByID[operationRef]
					}
					if !exists {
						issues = append(issues, issue(
							"CONTRACT.ERROR.UNKNOWN_HTTP_OPERATION",
							definition.SourcePath,
							"HTTP error %q references unknown canonical operation %q",
							definition.Code,
							operationRef,
						))
						continue
					}
					if operation.ObjectID != packet.ObjectID &&
						operationRef != operation.ID {
						issues = append(issues, issue(
							"CONTRACT.ERROR.CROSS_OBJECT_OPERATION_REQUIRES_CANONICAL_ID",
							definition.SourcePath,
							"cross-object HTTP error %q must reference canonical operation id %q",
							definition.Code,
							operation.ID,
						))
						continue
					}
					if ownerDomain != "" && operation.Domain != ownerDomain {
						issues = append(issues, issue(
							"CONTRACT.ERROR.CROSS_DOMAIN_OPERATION",
							definition.SourcePath,
							"HTTP error %q owned by domain %q cannot bind operation %q in domain %q",
							definition.Code,
							ownerDomain,
							operation.ID,
							operation.Domain,
						))
						continue
					}
					if emission.Surface == "graphql" && operation.Transport != "graphql" {
						issues = append(issues, issue(
							"CONTRACT.ERROR.OPERATION_BINDING_DRIFT",
							definition.SourcePath,
							"GraphQL error %q names non-GraphQL operation %q",
							definition.Code,
							operation.ID,
						))
						continue
					}
					if emission.Surface == "http" && operation.Transport == "graphql" {
						issues = append(issues, issue(
							"CONTRACT.ERROR.OPERATION_BINDING_DRIFT",
							definition.SourcePath,
							"HTTP error %q must use the graphql surface for operation %q",
							definition.Code,
							operation.ID,
						))
						continue
					}
					if !containsString(operation.ErrorCodes, definition.Code) {
						issues = append(issues, issue(
							"CONTRACT.ERROR.OPERATION_BINDING_DRIFT",
							definition.SourcePath,
							"HTTP error %q names operation %q but the operation does not reference the code",
							definition.Code,
							operation.ID,
						))
					}
				}
			}
			if hasHTTP {
				if definition.HTTPStatus == nil ||
					*definition.HTTPStatus < 400 || *definition.HTTPStatus > 599 {
					issues = append(issues, issue(
						"CONTRACT.ERROR.HTTP_STATUS_REQUIRED",
						definition.SourcePath,
						"HTTP error %q must declare http_status in 400..599",
						definition.Code,
					))
				}
			} else if definition.HTTPStatus != nil {
				issues = append(issues, issue(
					"CONTRACT.ERROR.NON_HTTP_STATUS",
					definition.SourcePath,
					"non-HTTP error %q must not declare http_status",
					definition.Code,
				))
			}
		}
	}
	for _, operation := range contractGraph.Operations {
		for _, code := range operation.ErrorCodes {
			definitions := definitionsByCode[code]
			if len(definitions) == 0 {
				issues = append(issues, issue(
					"CONTRACT.ERROR.UNKNOWN_OPERATION_CODE",
					operation.SourcePath,
					"operation %q references error %q without a canonical errors.yaml definition",
					operation.ID,
					code,
				))
				continue
			}
			if len(definitions) != 1 {
				continue
			}
			owner := definitions[0]
			if owner.domain != operation.Domain {
				issues = append(issues, issue(
					"CONTRACT.ERROR.CROSS_DOMAIN_OPERATION_CODE",
					operation.SourcePath,
					"operation %q in domain %q references error %q owned by domain %q",
					operation.ID,
					operation.Domain,
					code,
					owner.domain,
				))
				continue
			}
			expectedOperation := operation.ID
			if owner.objectID == operation.ObjectID {
				expectedOperation = operation.LocalID
			}
			expectedSurface := "http"
			if operation.Transport == "graphql" {
				expectedSurface = "graphql"
			}
			if !hasOperationErrorEmission(owner.definition, expectedSurface, expectedOperation) {
				issues = append(issues, issue(
					"CONTRACT.ERROR.MISSING_OPERATION_EMISSION",
					operation.SourcePath,
					"operation %q references error %q but its canonical definition does not bind %s producer %q",
					operation.ID,
					code,
					expectedSurface,
					expectedOperation,
				))
			}
		}
	}
	return issues
}

func hasOperationErrorEmission(
	definition ast.ErrorDefinition,
	surface string,
	operation string,
) bool {
	for _, emission := range definition.EmittedBy {
		if emission.Surface == surface && containsString(emission.Operations, operation) {
			return true
		}
	}
	return false
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}
