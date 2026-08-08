package graph

import (
	"encoding/json"
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

// deriveClientContracts binds the App wire ABI to the canonical response
// entity. Operation packets are not allowed to become a second registry of
// Dart imports, response aliases, or decoder names: those values follow the
// response type and the owning domain's generated operation library.
//
// During the repository-wide hard cut, an explicit legacy ClientContract is
// left untouched until that domain is migrated. A missing binding is derived
// only when the response entity can be proven from object-local types, a named
// projection, the aggregate root, or a schema-owned wire contract.
func deriveClientContracts(contractGraph *ContractGraph) {
	if contractGraph == nil {
		return
	}
	appExposed := appExposedOperationIDs(contractGraph)
	projectionTypes := make(map[string]string, len(contractGraph.Projections))
	for _, projection := range contractGraph.Projections {
		responseEntity := strings.TrimSpace(projection.ReadModel)
		dartClass := strings.TrimSpace(projection.DartClass)
		if responseEntity == "" {
			continue
		}
		// A named projection without a custom Dart class already owns its
		// canonical wire identity. Falling back to the read-model name keeps
		// operation packets from restating a response alias solely to satisfy
		// App generation.
		if dartClass == "" {
			dartClass = responseEntity
		}
		projectionTypes[responseEntity] = dartClass
	}
	schemaTypes := clientSchemaTypes(contractGraph.Documents)
	declaredTypes := make(map[string]map[string]struct{})
	uniqueDeclaredTypeOwner := make(map[string]string)
	duplicateDeclaredTypes := make(map[string]struct{})
	for _, definition := range contractGraph.Governance.Types {
		objectID := strings.TrimSpace(definition.ObjectID)
		name := strings.TrimSpace(definition.Name)
		if objectID == "" || name == "" {
			continue
		}
		if declaredTypes[objectID] == nil {
			declaredTypes[objectID] = map[string]struct{}{}
		}
		declaredTypes[objectID][name] = struct{}{}
		if previous, exists := uniqueDeclaredTypeOwner[name]; !exists {
			uniqueDeclaredTypeOwner[name] = objectID
		} else if previous != objectID {
			duplicateDeclaredTypes[name] = struct{}{}
		}
	}
	for index := range contractGraph.Operations {
		operation := &contractGraph.Operations[index]
		if operation.ClientContract != nil {
			continue
		}
		if _, exposed := appExposed[operation.ID]; !exposed {
			continue
		}
		responseEntity := strings.TrimSpace(operation.ResponseEntity)
		responseBodyKind := strings.TrimSpace(operation.ResponseBodyKind)
		if responseEntity == "" &&
			(responseBodyKind == "ack" || responseBodyKind == "upgrade") {
			operation.ClientContract = &ast.ClientContract{
				DartImport: "../" + operation.Domain + "/" + operation.Domain +
					"_operation_contracts.g.dart",
				ResponseType:    "void",
				ResponseDecoder: "decodeEmptyResponse",
			}
			continue
		}
		if responseEntity == "" {
			continue
		}
		responseType := ""
		if candidate := strings.TrimSpace(projectionTypes[responseEntity]); candidate != "" {
			// Generic domain clients are generated from response_entity and must
			// not inherit a second Dart type name from client_projection. The
			// Assistant domain still has one schema-owned specialized generator;
			// keep that bounded mapping until the Assistant owner hard-cuts it.
			if operation.Domain == "assistant" {
				responseType = candidate
			} else {
				responseType = responseEntity
			}
		} else if candidate := strings.TrimSpace(schemaTypes[responseEntity]); candidate != "" {
			responseType = candidate
		} else if _, exists := declaredTypes[operation.ObjectID][responseEntity]; exists {
			responseType = responseEntity
		} else if _, duplicated := duplicateDeclaredTypes[responseEntity]; !duplicated &&
			strings.TrimSpace(uniqueDeclaredTypeOwner[responseEntity]) != "" {
			// A composition operation may return another object packet's named
			// canonical type (for example credential binding returns an
			// AccountSession grant). Accept only a repository-unique declared
			// owner; ambiguity remains fail-closed and must be resolved in source.
			responseType = responseEntity
		} else if responseEntity == objectResponseType(operation.ObjectID) {
			responseType = responseEntity
		}
		if responseType == "" {
			continue
		}
		operation.ClientContract = &ast.ClientContract{
			DartImport: "../" + operation.Domain + "/" + operation.Domain +
				"_operation_contracts.g.dart",
			ResponseType:    responseType,
			ResponseDecoder: "decode" + responseType,
		}
	}
}

func appExposedOperationIDs(contractGraph *ContractGraph) map[string]struct{} {
	result := map[string]struct{}{}
	if contractGraph == nil {
		return result
	}
	var surfaceDocument struct {
		Surfaces []struct {
			Owner        string   `json:"owner"`
			OperationIDs []string `json:"operation_ids"`
		} `json:"surfaces"`
	}
	found := false
	for _, document := range contractGraph.Documents {
		if document.Path != "_shared/ui_surfaces.yaml" {
			continue
		}
		if json.Unmarshal(document.Content, &surfaceDocument) == nil {
			found = true
		}
		break
	}
	if !found {
		return result
	}
	byLocalID := map[string][]*ast.Operation{}
	for index := range contractGraph.Operations {
		operation := &contractGraph.Operations[index]
		localID := strings.TrimSpace(operation.LocalID)
		if localID != "" {
			byLocalID[localID] = append(byLocalID[localID], operation)
		}
	}
	for _, surface := range surfaceDocument.Surfaces {
		owner := strings.TrimSpace(surface.Owner)
		for _, localIDValue := range surface.OperationIDs {
			localID := strings.TrimSpace(localIDValue)
			candidates := byLocalID[localID]
			owned := make([]*ast.Operation, 0, len(candidates))
			for _, candidate := range candidates {
				if candidate.Domain == owner {
					owned = append(owned, candidate)
				}
			}
			selected := candidates
			if len(owned) == 1 {
				selected = owned
			}
			if len(selected) == 1 {
				result[selected[0].ID] = struct{}{}
			}
		}
	}
	return result
}

func clientSchemaTypes(documents []ast.SourceDocument) map[string]string {
	result := map[string]string{}
	for _, document := range documents {
		if !strings.HasSuffix(document.Path, "/schema.yaml") {
			continue
		}
		var header struct {
			Contract  string `json:"contract"`
			DartClass string `json:"dart_class"`
		}
		if err := json.Unmarshal(document.Content, &header); err != nil {
			continue
		}
		dartClass := strings.TrimSpace(header.DartClass)
		if dartClass == "" {
			continue
		}
		result[dartClass] = dartClass
		result[strings.TrimSuffix(strings.TrimSuffix(dartClass, "Wire"), "Dto")] = dartClass
		if contract := upperCamel(strings.TrimSpace(header.Contract)); contract != "" {
			result[contract] = dartClass
		}
	}
	return result
}

func objectResponseType(objectID string) string {
	segments := strings.Split(strings.TrimSpace(objectID), ".")
	return upperCamel(segments[len(segments)-1])
}

func upperCamel(value string) string {
	parts := strings.FieldsFunc(value, func(current rune) bool {
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
