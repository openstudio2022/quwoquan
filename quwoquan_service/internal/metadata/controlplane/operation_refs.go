package controlplane

import (
	"fmt"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

// HydrateOperationReferences resolves portal-only operation references from the
// canonical ContractGraph. Control-plane presentation metadata may add risk and
// approval semantics, but it must not repeat method, path, or authorization
// scopes owned by object-level operations.yaml.
func HydrateOperationReferences(document map[string]any, contractGraph *graph.ContractGraph) error {
	if contractGraph == nil {
		return fmt.Errorf("control-plane operation references require ContractGraph")
	}
	operationsByID := make(map[string]ast.Operation, len(contractGraph.Operations))
	for _, operation := range contractGraph.Operations {
		operationsByID[operation.ID] = operation
	}

	objects, err := asSlice(document["object_types"])
	if err != nil {
		return fmt.Errorf("control-plane object_types: %w", err)
	}
	for index, rawObject := range objects {
		object, err := asMap(rawObject)
		if err != nil {
			return fmt.Errorf("control-plane object_types[%d]: %w", index, err)
		}
		rawRefs, hasReferences := object["operation_refs"]
		if !hasReferences {
			continue
		}
		if rawOperations, hasOperations := object["operations"]; hasOperations {
			operations, err := asSlice(rawOperations)
			if err != nil || len(operations) > 0 {
				return fmt.Errorf(
					"control-plane object %q cannot declare operations and operation_refs together",
					strings.TrimSpace(fmt.Sprint(object["object_type"])),
				)
			}
		}
		references, err := asSlice(rawRefs)
		if err != nil {
			return fmt.Errorf("control-plane object %q operation_refs: %w", object["object_type"], err)
		}
		resolved := make([]any, 0, len(references))
		for referenceIndex, rawReference := range references {
			reference, err := asMap(rawReference)
			if err != nil {
				return fmt.Errorf("control-plane object %q operation_refs[%d]: %w", object["object_type"], referenceIndex, err)
			}
			operationID := strings.TrimSpace(fmt.Sprint(reference["operation_id"]))
			operation, found := operationsByID[operationID]
			if !found {
				return fmt.Errorf(
					"control-plane object %q references unknown ContractGraph operation %q",
					object["object_type"], operationID,
				)
			}
			binding := map[string]any{
				"operation":             operation.LocalID,
				"contract_operation_id": operation.ID,
				"method":                operation.Method,
				"path":                  operation.PathTemplate,
				"scopes":                append([]string(nil), operation.Scopes...),
			}
			for _, key := range []string{"danger_level", "approval_mode"} {
				if value, exists := reference[key]; exists && strings.TrimSpace(fmt.Sprint(value)) != "" {
					binding[key] = value
				}
			}
			resolved = append(resolved, binding)
		}
		delete(object, "operation_refs")
		object["operations"] = resolved
		objects[index] = object
	}
	document["object_types"] = objects
	return nil
}

func asMap(value any) (map[string]any, error) {
	if typed, ok := value.(map[string]any); ok {
		return typed, nil
	}
	return nil, fmt.Errorf("must be an object")
}

func asSlice(value any) ([]any, error) {
	if typed, ok := value.([]any); ok {
		return typed, nil
	}
	return nil, fmt.Errorf("must be an array")
}
