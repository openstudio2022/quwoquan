package validate

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

const appSurfaceSourcePath = "_shared/ui_surfaces.yaml"

type appSurfaceContractDocument struct {
	Surfaces []appSurfaceContract `json:"surfaces"`
}

type appSurfaceContract struct {
	ID           string   `json:"id"`
	Owner        string   `json:"owner"`
	OperationIDs []string `json:"operation_ids"`
}

// validateAppSurfaceGovernance keeps App exposure on one source-derived ABI.
// Commercial status is deliberately absent from the decision: a blocked
// operation still needs a generated request, response, error mapping and
// decoder before an App surface may reference it.
func validateAppSurfaceGovernance(contractGraph *graph.ContractGraph) []Issue {
	if contractGraph == nil {
		return nil
	}
	document, found, decodeErr := decodeAppSurfaceContractDocument(contractGraph)
	if decodeErr != nil {
		return []Issue{issue(
			"CONTRACT.APP_SURFACE.INVALID_DOCUMENT",
			appSurfaceSourcePath,
			"decode App surface contract: %v",
			decodeErr,
		)}
	}
	if !found {
		// Object-level compiler fixtures do not carry the repository-wide App
		// surface document. When it is present, every reference is validated;
		// repository source/generator gates separately require the document.
		return nil
	}

	byLocalID := map[string][]ast.Operation{}
	for _, operation := range contractGraph.Operations {
		localID := strings.TrimSpace(operation.LocalID)
		if localID == "" {
			continue
		}
		byLocalID[localID] = append(byLocalID[localID], operation)
	}

	var issues []Issue
	surfaceIDs := map[string]struct{}{}
	validatedOperations := map[string]struct{}{}
	for _, surface := range document.Surfaces {
		surfaceID := strings.TrimSpace(surface.ID)
		owner := strings.TrimSpace(surface.Owner)
		if surfaceID == "" {
			issues = append(issues, issue(
				"CONTRACT.APP_SURFACE.INVALID_ID",
				appSurfaceSourcePath,
				"App surface id must not be empty",
			))
			continue
		}
		if _, duplicate := surfaceIDs[surfaceID]; duplicate {
			issues = append(issues, issue(
				"CONTRACT.APP_SURFACE.DUPLICATE_ID",
				appSurfaceSourcePath,
				"App surface %q is declared more than once",
				surfaceID,
			))
			continue
		}
		surfaceIDs[surfaceID] = struct{}{}
		seenLocalIDs := map[string]struct{}{}
		for _, rawLocalID := range surface.OperationIDs {
			localID := strings.TrimSpace(rawLocalID)
			if localID == "" {
				issues = append(issues, issue(
					"CONTRACT.APP_SURFACE.INVALID_OPERATION_ID",
					appSurfaceSourcePath,
					"App surface %q contains an empty operation id",
					surfaceID,
				))
				continue
			}
			if _, duplicate := seenLocalIDs[localID]; duplicate {
				issues = append(issues, issue(
					"CONTRACT.APP_SURFACE.DUPLICATE_OPERATION",
					appSurfaceSourcePath,
					"App surface %q repeats operation %q",
					surfaceID,
					localID,
				))
				continue
			}
			seenLocalIDs[localID] = struct{}{}

			operation, resolutionIssue := resolveAppSurfaceOperation(
				surfaceID,
				owner,
				localID,
				byLocalID[localID],
			)
			if resolutionIssue != nil {
				issues = append(issues, *resolutionIssue)
				continue
			}
			if _, validated := validatedOperations[operation.ID]; validated {
				continue
			}
			validatedOperations[operation.ID] = struct{}{}
			issues = append(
				issues,
				validateAppSurfaceOperation(contractGraph, operation)...,
			)
		}
	}
	return issues
}

func decodeAppSurfaceContractDocument(
	contractGraph *graph.ContractGraph,
) (appSurfaceContractDocument, bool, error) {
	for _, document := range contractGraph.Documents {
		if document.Path != appSurfaceSourcePath {
			continue
		}
		var result appSurfaceContractDocument
		if err := json.Unmarshal(document.Content, &result); err != nil {
			return appSurfaceContractDocument{}, true, err
		}
		return result, true, nil
	}
	return appSurfaceContractDocument{}, false, nil
}

func resolveAppSurfaceOperation(
	surfaceID string,
	owner string,
	localID string,
	candidates []ast.Operation,
) (ast.Operation, *Issue) {
	if len(candidates) == 1 {
		return candidates[0], nil
	}
	owned := make([]ast.Operation, 0, len(candidates))
	for _, candidate := range candidates {
		if strings.TrimSpace(candidate.Domain) == owner {
			owned = append(owned, candidate)
		}
	}
	if len(owned) == 1 {
		return owned[0], nil
	}
	if len(candidates) == 0 {
		problem := issue(
			"CONTRACT.APP_SURFACE.UNKNOWN_OPERATION",
			appSurfaceSourcePath,
			"App surface %q references unknown operation %q",
			surfaceID,
			localID,
		)
		return ast.Operation{}, &problem
	}
	candidateIDs := make([]string, 0, len(candidates))
	for _, candidate := range candidates {
		candidateIDs = append(candidateIDs, candidate.ID)
	}
	sort.Strings(candidateIDs)
	problem := issue(
		"CONTRACT.APP_SURFACE.AMBIGUOUS_OPERATION",
		appSurfaceSourcePath,
		"App surface %q operation %q has no unique canonical owner: %s",
		surfaceID,
		localID,
		strings.Join(candidateIDs, ", "),
	)
	return ast.Operation{}, &problem
}

func validateAppSurfaceOperation(
	contractGraph *graph.ContractGraph,
	operation ast.Operation,
) []Issue {
	var issues []Issue
	if operation.ClientContractExplicit {
		issues = append(issues, issue(
			"CONTRACT.APP_SURFACE.CLIENT_CONTRACT_SECOND_TRUTH",
			operation.SourcePath,
			"App operation %q declares client_contract; derive the client ABI from request_entity and response_entity",
			operation.ID,
		))
	}
	if strings.TrimSpace(operation.RequestEntity) == "" {
		issues = append(issues, issue(
			"CONTRACT.APP_SURFACE.REQUEST_ENTITY_REQUIRED",
			operation.SourcePath,
			"App operation %q must declare a canonical request_entity even when its request has no body",
			operation.ID,
		))
	} else {
		issues = append(
			issues,
			validateAppSurfaceRequestEntity(contractGraph, operation)...,
		)
	}
	if operation.RequestBodyKind != "object" && operation.RequestBodyKind != "none" {
		issues = append(issues, issue(
			"CONTRACT.APP_SURFACE.REQUEST_BODY_KIND_REQUIRED",
			operation.SourcePath,
			"App operation %q request_body_kind must be object or none",
			operation.ID,
		))
	}
	responseEntity := strings.TrimSpace(operation.ResponseEntity)
	if responseEntity == "" {
		issues = append(issues, issue(
			"CONTRACT.APP_SURFACE.RESPONSE_ENTITY_REQUIRED",
			operation.SourcePath,
			"App operation %q must declare response_entity; ack/response_body/response_fields cannot own the client ABI",
			operation.ID,
		))
	} else {
		issues = append(
			issues,
			validateAppSurfaceResponseEntity(contractGraph, operation)...,
		)
	}
	if operation.ClientContract == nil {
		issues = append(issues, issue(
			"CONTRACT.APP_SURFACE.CLIENT_ABI_UNRESOLVED",
			operation.SourcePath,
			"App operation %q has no unique source-derived client response owner",
			operation.ID,
		))
	} else if responseEntity != "" {
		expectedDecoder := "decode" + responseEntity
		if operation.ClientContract.ResponseType != responseEntity ||
			operation.ClientContract.ResponseDecoder != expectedDecoder {
			issues = append(issues, issue(
				"CONTRACT.APP_SURFACE.CLIENT_ABI_NOT_DERIVED",
				operation.SourcePath,
				"App operation %q client response must be derived as %s/%s from response_entity, got %s/%s",
				operation.ID,
				responseEntity,
				expectedDecoder,
				operation.ClientContract.ResponseType,
				operation.ClientContract.ResponseDecoder,
			))
		}
	}
	if len(operation.ErrorCodes) == 0 {
		issues = append(issues, issue(
			"CONTRACT.APP_SURFACE.ERROR_CONTRACT_REQUIRED",
			operation.SourcePath,
			"App operation %q must declare canonical error_codes regardless of commercial status",
			operation.ID,
		))
	} else {
		issues = append(
			issues,
			validateAppSurfaceErrorOwners(contractGraph, operation)...,
		)
	}
	return bindIssueSubject(operation.ID, issues)
}

func validateAppSurfaceResponseEntity(
	contractGraph *graph.ContractGraph,
	operation ast.Operation,
) []Issue {
	responseEntity := strings.TrimSpace(operation.ResponseEntity)
	owners := map[string]struct{}{}
	for _, object := range contractGraph.Objects {
		if strings.TrimSpace(object.Name) == responseEntity && object.ID != "" {
			owners[object.ID] = struct{}{}
		}
	}
	for _, definition := range contractGraph.Governance.Types {
		if definition.Name == responseEntity && definition.ObjectID != "" {
			owners[definition.ObjectID] = struct{}{}
		}
	}
	for _, projection := range contractGraph.Projections {
		if projection.ReadModel == responseEntity && projection.ObjectID != "" {
			owners[projection.ObjectID] = struct{}{}
		}
	}
	for ownerID := range schemaResponseEntityOwners(contractGraph, responseEntity) {
		owners[ownerID] = struct{}{}
	}
	if _, local := owners[operation.ObjectID]; local {
		if strings.TrimSpace(operation.ResponseEntityRef) != "" {
			return []Issue{issue(
				"CONTRACT.APP_SURFACE.REDUNDANT_RESPONSE_ENTITY_REF",
				operation.SourcePath,
				"App operation %q response_entity %q is object-local and must not declare response_entity_ref",
				operation.ID,
				responseEntity,
			)}
		}
		return nil
	}
	ownerIDs := make([]string, 0, len(owners))
	for ownerID := range owners {
		ownerIDs = append(ownerIDs, ownerID)
	}
	sort.Strings(ownerIDs)
	if len(ownerIDs) != 1 {
		return []Issue{issue(
			"CONTRACT.APP_SURFACE.RESPONSE_ENTITY_OWNER",
			operation.SourcePath,
			"App operation %q response_entity %q must have one canonical object owner; found %d (%s)",
			operation.ID,
			responseEntity,
			len(ownerIDs),
			strings.Join(ownerIDs, ", "),
		)}
	}
	expectedRef := canonicalObjectReference(contractGraph, ownerIDs[0])
	if expectedRef == "" || strings.TrimSpace(operation.ResponseEntityRef) != expectedRef {
		return []Issue{issue(
			"CONTRACT.APP_SURFACE.CROSS_OBJECT_RESPONSE_REF_REQUIRED",
			operation.SourcePath,
			"App operation %q response_entity %q is owned by %q and requires response_entity_ref %q",
			operation.ID,
			responseEntity,
			ownerIDs[0],
			expectedRef,
		)}
	}
	return nil
}

func schemaResponseEntityOwners(
	contractGraph *graph.ContractGraph,
	responseEntity string,
) map[string]struct{} {
	result := map[string]struct{}{}
	for _, document := range contractGraph.Documents {
		if !strings.HasSuffix(document.Path, "/schema.yaml") {
			continue
		}
		var header struct {
			Contract  string `json:"contract"`
			DartClass string `json:"dart_class"`
		}
		if json.Unmarshal(document.Content, &header) != nil {
			continue
		}
		contractName := upperCamelContractName(header.Contract)
		dartClass := strings.TrimSpace(header.DartClass)
		baseClass := strings.TrimSuffix(
			strings.TrimSuffix(dartClass, "Wire"),
			"Dto",
		)
		if responseEntity != contractName && responseEntity != dartClass &&
			responseEntity != baseClass {
			continue
		}
		schemaDir := strings.TrimSuffix(document.Path, "/schema.yaml")
		for _, object := range contractGraph.Objects {
			objectDir := strings.TrimSuffix(object.SourcePath, "/object.yaml")
			if schemaDir == objectDir {
				result[object.ID] = struct{}{}
			}
		}
	}
	return result
}

func upperCamelContractName(value string) string {
	parts := strings.FieldsFunc(strings.TrimSpace(value), func(current rune) bool {
		return current == '_' || current == '-' || current == '.' || current == '/'
	})
	var result strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		result.WriteString(strings.ToUpper(part[:1]))
		result.WriteString(part[1:])
	}
	return result.String()
}

func canonicalObjectReference(
	contractGraph *graph.ContractGraph,
	objectID string,
) string {
	for _, object := range contractGraph.Objects {
		if object.ID == objectID {
			return object.Domain + "." + object.Name
		}
	}
	return ""
}

func validateAppSurfaceErrorOwners(
	contractGraph *graph.ContractGraph,
	operation ast.Operation,
) []Issue {
	definitionsByCode := map[string][]ast.ErrorDefinition{}
	for _, definition := range contractGraph.Governance.Objects {
		for _, errorDefinition := range definition.Errors {
			definitionsByCode[errorDefinition.Code] = append(
				definitionsByCode[errorDefinition.Code],
				errorDefinition,
			)
		}
	}
	var issues []Issue
	for _, code := range operation.ErrorCodes {
		definitions := definitionsByCode[code]
		if len(definitions) != 1 || definitions[0].ObjectID == "" ||
			!strings.HasSuffix(definitions[0].SourcePath, "/errors.yaml") {
			issues = append(issues, issue(
				"CONTRACT.APP_SURFACE.ERROR_OWNER",
				operation.SourcePath,
				"App operation %q error %q must resolve to exactly one object-local errors.yaml owner; found %d",
				operation.ID,
				code,
				len(definitions),
			))
		}
	}
	return issues
}

func validateAppSurfaceRequestEntity(
	contractGraph *graph.ContractGraph,
	operation ast.Operation,
) []Issue {
	requestEntity := strings.TrimSpace(operation.RequestEntity)
	ownerCount := 0
	fieldNames := map[string]struct{}{}
	for _, definition := range contractGraph.Governance.Types {
		if definition.ObjectID != operation.ObjectID || definition.Name != requestEntity {
			continue
		}
		ownerCount++
	}
	for _, field := range contractGraph.Governance.Fields {
		if field.ObjectID == operation.ObjectID && field.Entity == requestEntity {
			fieldNames[field.Name] = struct{}{}
		}
	}
	var issues []Issue
	if ownerCount != 1 {
		issues = append(issues, issue(
			"CONTRACT.APP_SURFACE.REQUEST_ENTITY_OWNER",
			operation.SourcePath,
			"App operation %q request_entity %q must have exactly one object-local owner; found %d",
			operation.ID,
			requestEntity,
			ownerCount,
		))
		return issues
	}
	if operation.RequestBindings == nil {
		return issues
	}
	for _, group := range []struct {
		name   string
		values []ast.RequestBinding
	}{
		{name: "path", values: operation.RequestBindings.Path},
		{name: "query", values: operation.RequestBindings.Query},
		{name: "header", values: operation.RequestBindings.Header},
		{name: "injected", values: operation.RequestBindings.Injected},
	} {
		for _, binding := range group.values {
			if _, exists := fieldNames[binding.Field]; exists {
				continue
			}
			issues = append(issues, issue(
				"CONTRACT.APP_SURFACE.REQUEST_BINDING_OWNER",
				operation.SourcePath,
				"App operation %q request_bindings.%s field %q is absent from object-local request_entity %q",
				operation.ID,
				group.name,
				binding.Field,
				requestEntity,
			))
		}
	}
	return issues
}

func appSurfaceContractCounts(
	contractGraph *graph.ContractGraph,
) (surfaces int, references int, uniqueOperations int, err error) {
	document, found, decodeErr := decodeAppSurfaceContractDocument(contractGraph)
	if decodeErr != nil {
		return 0, 0, 0, decodeErr
	}
	if !found {
		return 0, 0, 0, fmt.Errorf("%s is missing", appSurfaceSourcePath)
	}
	unique := map[string]struct{}{}
	byLocalID := map[string][]ast.Operation{}
	for _, operation := range contractGraph.Operations {
		byLocalID[operation.LocalID] = append(byLocalID[operation.LocalID], operation)
	}
	for _, surface := range document.Surfaces {
		for _, localID := range surface.OperationIDs {
			references++
			operation, issue := resolveAppSurfaceOperation(
				surface.ID,
				surface.Owner,
				localID,
				byLocalID[localID],
			)
			if issue == nil {
				unique[operation.ID] = struct{}{}
			}
		}
	}
	return len(document.Surfaces), references, len(unique), nil
}
